"""
test_cli_github_conflict_mcp.py - Unit and integration tests for:
1. Typer CLI command groups: conflict, pr, mcp, dedup (with --json and Rich formatting).
2. Subagent roles: CONFLICT_RESOLVER, PR_REVIEWER, MCP_OPERATOR and MCP tool execution in workers.
3. Orchestrator & workflow plan generation Deduplication engine warning integration.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add root package path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.git.conflict_resolver import ConflictResolver, ConflictBlock, FileResolutionResult
from k_cli.github.github_client import GitHubClient, MockGitHubClient, PRLifecycleManager, PullRequest
from k_cli.tools.mcp_client import MCPManager, MCPServerConfig, MCPTool, MCPToolResult
from k_cli.github.dedup_engine import DedupEngine, DedupMatch
from k_cli.agents.orchestrator import Orchestrator, Persona
from k_cli.agents.subagents import (
    SubagentDispatcher,
    SubagentWorker,
    SubagentTask,
    SubagentRole,
    SubagentStatus,
    TaskDecomposer,
)
from k_cli.core.sdk import create_plan
from k_cli.git.verifier import Verifier
from k_cli.core.llm_driver import LLMDriver

runner = CliRunner()


# ==============================================================================
# 1. CLI Conflict Command Tests
# ==============================================================================

def test_cli_conflict_list_clean(tmp_path):
    """Test 'k-cli conflict list' on a clean directory without conflict markers."""
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    # Human-readable output
    res = runner.invoke(app, ["conflict", "list", "--dir", str(tmp_path)])
    assert res.exit_code == 0
    assert "Clean: No git merge conflicts" in res.output

    # JSON output
    res_json = runner.invoke(app, ["conflict", "list", "--dir", str(tmp_path), "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["total_conflicts"] == 0
    assert data["conflicted_files_count"] == 0
    assert data["conflicts"] == []


def test_cli_conflict_list_with_conflicts(tmp_path):
    """Test 'k-cli conflict list' on a workspace containing 2-way and 3-way conflicts."""
    conflicted = tmp_path / "app.py"
    conflicted.write_text(
        "def compute(a, b):\n"
        "<<<<<<< HEAD\n"
        "    return a + b\n"
        "=======\n"
        "    return a * b\n"
        ">>>>>>> feature-branch\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["conflict", "list", "--dir", str(tmp_path)])
    assert res.exit_code == 0
    assert "app.py" in res.output
    assert "Git Merge Conflicts Detected" in res.output

    res_json = runner.invoke(app, ["conflict", "list", "--dir", str(tmp_path), "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["total_conflicts"] == 1
    assert data["conflicted_files_count"] == 1
    assert data["conflicts"][0]["ours_label"] == "HEAD"
    assert data["conflicts"][0]["theirs_label"] == "feature-branch"


def test_cli_conflict_resolve_single_file(tmp_path):
    """Test 'k-cli conflict resolve --file <path> --mock --auto-accept'."""
    conflicted = tmp_path / "calc.py"
    conflicted.write_text(
        "<<<<<<< HEAD\n"
        "def add(x, y):\n"
        "    return x + y\n"
        "=======\n"
        "def add(x, y):\n"
        "    return int(x) + int(y)\n"
        ">>>>>>> branch-b\n",
        encoding="utf-8",
    )

    res = runner.invoke(
        app,
        [
            "conflict",
            "resolve",
            "--file",
            str(conflicted),
            "--mock",
            "--auto-accept",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["success"] is True
    assert data["resolved_conflicts"] == 1

    # Verify conflict markers removed from file
    content = conflicted.read_text(encoding="utf-8")
    assert "<<<<<<<" not in content
    assert ">>>>>>>" not in content


def test_cli_conflict_resolve_all(tmp_path):
    """Test 'k-cli conflict resolve --dir <path> --mock' resolving all files."""
    f1 = tmp_path / "m1.py"
    f1.write_text(
        "<<<<<<< HEAD\n"
        "val = 1\n"
        "=======\n"
        "val = 2\n"
        ">>>>>>> branch\n",
        encoding="utf-8",
    )

    res = runner.invoke(
        app,
        [
            "conflict",
            "resolve",
            "--dir",
            str(tmp_path),
            "--mock",
            "--auto-accept",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["success"] is True
    assert data["resolved_files"] == 1


# ==============================================================================
# 2. CLI GitHub Pull Request Command Tests
# ==============================================================================

def test_cli_pr_list_mock(tmp_path):
    """Test 'k-cli pr list --mock' with human and JSON output."""
    res = runner.invoke(app, ["pr", "list", "--dir", str(tmp_path), "--mock"])
    assert res.exit_code == 0
    assert "Pull Requests" in res.output

    res_json = runner.invoke(app, ["pr", "list", "--dir", str(tmp_path), "--mock", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["number"] == 1


def test_cli_pr_view_mock(tmp_path):
    """Test 'k-cli pr view <pr_num> --mock' with human and JSON output."""
    res = runner.invoke(app, ["pr", "view", "1", "--dir", str(tmp_path), "--mock"])
    assert res.exit_code == 0
    assert "Pull Request #1" in res.output

    res_json = runner.invoke(app, ["pr", "view", "1", "--dir", str(tmp_path), "--mock", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["number"] == 1
    assert "diff" in data
    assert "ci_status" in data


def test_cli_pr_review_mock(tmp_path):
    """Test 'k-cli pr review <pr_num> --mock' with JSON output."""
    res = runner.invoke(app, ["pr", "review", "1", "--dir", str(tmp_path), "--mock"])
    assert res.exit_code == 0
    assert "AI Code Review: PR #1" in res.output

    res_json = runner.invoke(app, ["pr", "review", "1", "--dir", str(tmp_path), "--mock", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert "verdict" in data
    assert data["pr_number"] == 1


def test_cli_pr_fix_mock(tmp_path):
    """Test 'k-cli pr fix <pr_num> --mock'."""
    res = runner.invoke(app, ["pr", "fix", "1", "--dir", str(tmp_path), "--mock"])
    assert res.exit_code == 0
    assert "Fixed PR #1 successfully" in res.output

    res_json = runner.invoke(app, ["pr", "fix", "1", "--dir", str(tmp_path), "--mock", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["success"] is True
    assert data["pr_number"] == 1


def test_cli_pr_merge_mock(tmp_path):
    """Test 'k-cli pr merge <pr_num> --mock'."""
    res = runner.invoke(app, ["pr", "merge", "1", "--dir", str(tmp_path), "--mock"])
    assert res.exit_code == 0
    assert "Successfully merged PR #1" in res.output

    res_json = runner.invoke(app, ["pr", "merge", "1", "--dir", str(tmp_path), "--mock", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["merged"] is True
    assert data["pr_number"] == 1


# ==============================================================================
# 3. CLI Model Context Protocol (MCP) Command Tests
# ==============================================================================

def test_cli_mcp_lifecycle(tmp_path):
    """Test full MCP CLI lifecycle: list, add, tools, call, test, remove."""
    config_file = tmp_path / "mcp.json"

    # 1. Initial list (empty)
    res = runner.invoke(app, ["mcp", "list", "--config", str(config_file), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert isinstance(data, list)
    assert len(data) == 0

    # 2. Add server
    res_add = runner.invoke(
        app,
        [
            "mcp",
            "add",
            "test-server",
            "python",
            "--args",
            "-m http.server",
            "--config",
            str(config_file),
            "--json",
        ],
    )
    assert res_add.exit_code == 0
    add_data = json.loads(res_add.output)
    assert add_data["success"] is True
    assert add_data["name"] == "test-server"

    # 3. List servers after add
    res_list = runner.invoke(app, ["mcp", "list", "--config", str(config_file), "--json"])
    assert res_list.exit_code == 0
    servers = json.loads(res_list.output)
    assert len(servers) == 1
    assert servers[0]["name"] == "test-server"

    # 4. Remove server
    res_remove = runner.invoke(
        app,
        [
            "mcp",
            "remove",
            "test-server",
            "--config",
            str(config_file),
            "--json",
        ],
    )
    assert res_remove.exit_code == 0
    rem_data = json.loads(res_remove.output)
    assert rem_data["success"] is True


def test_cli_mcp_tools_and_call(tmp_path):
    """Test 'k-cli mcp tools' and 'k-cli mcp call'."""
    config_file = tmp_path / "mcp.json"
    config_data = {
        "mcpServers": {
            "mock-server": {
                "command": "echo",
                "args": ["mock"],
                "transport": "stdio",
            }
        }
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    res = runner.invoke(app, ["mcp", "tools", "--config", str(config_file), "--json"])
    assert res.exit_code == 0
    tools = json.loads(res.output)
    assert isinstance(tools, list)


# ==============================================================================
# 4. CLI Dedup Command Tests
# ==============================================================================

def test_cli_dedup_check_clean(tmp_path):
    """Test 'k-cli dedup check' for a non-duplicate query."""
    res = runner.invoke(app, ["dedup", "check", "implement quantum entanglement engine", "--dir", str(tmp_path)])
    assert res.exit_code == 0
    assert "Unique: No duplicate" in res.output

    res_json = runner.invoke(app, ["dedup", "check", "implement quantum entanglement engine", "--dir", str(tmp_path), "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["is_duplicate"] is False


def test_cli_dedup_check_detected(tmp_path):
    """Test 'k-cli dedup check' identifying symbol duplicate."""
    code_file = tmp_path / "auth.py"
    code_file.write_text(
        "def validate_user_login_credentials(username, password):\n"
        "    return username == 'admin' and password == 'secret'\n",
        encoding="utf-8",
    )

    res = runner.invoke(
        app,
        [
            "dedup",
            "check",
            "validate user login credentials",
            "--dir",
            str(tmp_path),
            "--threshold",
            "0.5",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["is_duplicate"] is True
    assert "auth.py" in (data.get("file_path") or "")


# ==============================================================================
# 5. Subagent Swarm Roles & MCP Context Tests
# ==============================================================================

def test_subagent_conflict_resolver_worker(tmp_path):
    """Test SubagentWorker executing CONFLICT_RESOLVER role."""
    conflicted = tmp_path / "merge.py"
    conflicted.write_text(
        "<<<<<<< HEAD\n"
        "def greet():\n"
        "    return 'hello'\n"
        "=======\n"
        "def greet():\n"
        "    return 'hi'\n"
        ">>>>>>> branch\n",
        encoding="utf-8",
    )

    task = SubagentTask(
        task_id="task_conflict",
        name="Resolve Merge",
        role=SubagentRole.CONFLICT_RESOLVER,
        prompt="Resolve merge.py conflicts",
        context={"file_path": str(conflicted), "auto_accept": True},
    )

    worker = SubagentWorker(
        task=task,
        workspace_dir=tmp_path,
        driver=LLMDriver(mock_mode=True),
        verifier=Verifier(),
    )
    res_task = worker.execute()
    assert res_task.status == SubagentStatus.COMPLETED
    assert "Resolved" in res_task.output_text


def test_subagent_pr_reviewer_worker(tmp_path):
    """Test SubagentWorker executing PR_REVIEWER role."""
    task = SubagentTask(
        task_id="task_pr_review",
        name="Review PR #1",
        role=SubagentRole.PR_REVIEWER,
        prompt="Review PR #1 diff",
        context={"pr_number": 1},
    )

    worker = SubagentWorker(
        task=task,
        workspace_dir=tmp_path,
        driver=LLMDriver(mock_mode=True),
        pr_manager=PRLifecycleManager(client=MockGitHubClient(), repo_dir=tmp_path),
    )
    res_task = worker.execute()
    assert res_task.status == SubagentStatus.COMPLETED
    assert "VERDICT" in res_task.output_text or "Review" in res_task.output_text


def test_subagent_mcp_operator_and_tool_invocation(tmp_path):
    """Test SubagentWorker executing MCP_OPERATOR role and invoking MCP tools."""
    cfg = tmp_path / "mcp.json"
    mgr = MCPManager(config_path=str(cfg), auto_load=True)

    task = SubagentTask(
        task_id="task_mcp",
        name="List MCP Tools",
        role=SubagentRole.MCP_OPERATOR,
        prompt="Discover available MCP tools",
    )

    worker = SubagentWorker(
        task=task,
        workspace_dir=tmp_path,
        mcp_manager=mgr,
    )

    # Test list_mcp_tools and invoke_mcp_tool helpers on worker
    tools = worker.list_mcp_tools()
    assert isinstance(tools, list)

    res_task = worker.execute()
    assert res_task.status == SubagentStatus.COMPLETED
    assert "MCP tools" in res_task.output_text


def test_subagent_dispatcher_with_dedup_warning(tmp_path):
    """Test SubagentDispatcher checking DedupEngine before running prompt."""
    code_file = tmp_path / "service.py"
    code_file.write_text("def fetch_user_profile(user_id):\n    return {'id': user_id}\n", encoding="utf-8")

    dedup = DedupEngine(repo_path=str(tmp_path), duplicate_threshold=0.5)
    dispatcher = SubagentDispatcher(
        driver=LLMDriver(mock_mode=True),
        workspace_dir=tmp_path,
        dedup_engine=dedup,
    )

    result = dispatcher.run_prompt("fetch user profile")
    assert result.dedup_warning is not None
    assert result.dedup_match is not None
    assert result.dedup_match["is_duplicate"] is True


def test_task_decomposer_routes_new_roles():
    """Test TaskDecomposer routes deterministic pipelines for conflict, pr, and mcp."""
    decomposer = TaskDecomposer(driver=LLMDriver(mock_mode=True))

    tasks_conflict = decomposer._decompose_deterministic("Resolve git merge conflict in repo")
    assert any(t.role == SubagentRole.CONFLICT_RESOLVER for t in tasks_conflict)

    tasks_pr = decomposer._decompose_deterministic("Review PR #42 pull request")
    assert any(t.role == SubagentRole.PR_REVIEWER for t in tasks_pr)

    tasks_mcp = decomposer._decompose_deterministic("Call mcp tool for diagnostics")
    assert any(t.role == SubagentRole.MCP_OPERATOR for t in tasks_mcp)


# ==============================================================================
# 6. Orchestrator & Plan Deduplication Integration Tests
# ==============================================================================

def test_orchestrator_dedup_warning_in_result(tmp_path):
    """Test Orchestrator.execute_pipeline captures deduplication warning."""
    code_file = tmp_path / "math_utils.py"
    code_file.write_text("def calculate_fibonacci(n):\n    return n if n <= 1 else calculate_fibonacci(n-1) + calculate_fibonacci(n-2)\n", encoding="utf-8")

    engine = DedupEngine(repo_path=str(tmp_path), duplicate_threshold=0.5)
    orch = Orchestrator(
        driver=LLMDriver(mock_mode=True),
        verifier=Verifier(),
        dedup_engine=engine,
    )

    result = orch.execute_pipeline(
        user_prompt="calculate fibonacci number",
        language="python",
    )
    assert result.dedup_warning is not None
    assert result.dedup_match is not None
    assert result.dedup_match["is_duplicate"] is True


def test_workflow_create_plan_dedup_warning(tmp_path):
    """Test workflow.create_plan includes deduplication warning in PlanResult and rendered markdown."""
    f = tmp_path / "storage.py"
    f.write_text("def save_blob_to_disk(data, path):\n    with open(path, 'w') as fh: fh.write(data)\n", encoding="utf-8")

    plan = create_plan(
        goal="save blob to disk",
        workspace_dir=tmp_path,
    )
    assert plan.dedup_warning is not None
    assert "Deduplication warning" in plan.render_markdown()
