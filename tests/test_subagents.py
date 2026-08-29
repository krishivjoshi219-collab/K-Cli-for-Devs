"""
test_subagents.py - Comprehensive Unit & Integration Tests for Native Subagent Task Spawner
Tests:
  - Structured JSON message serialization & parsing
  - Subagent task lifecycle and DAG decomposition
  - Parallel background execution of Explorer, Researcher, Refactorer, Tester
  - PatchAggregator merging of SEARCH/REPLACE surgical blocks
  - Rich CLI tree visualization and live dashboard rendering
  - Integration with Orchestrator, CLI commands, and session commands
"""

import json
import os
import sys
import queue
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root paths are in sys.path
_root_dir = Path(__file__).parent.parent
_parent_dir = _root_dir.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

import pytest
from typer.testing import CliRunner
from rich.console import Console

from k_cli.agents.subagents import (
    SubagentRole,
    SubagentStatus,
    SubagentMessageType,
    SubagentMessage,
    SubagentTask,
    SubagentRunResult,
    TaskDecomposer,
    SubagentWorker,
    PatchAggregator,
    SubagentDispatcher,
    SubagentVisualizer,
    execute_subagents,
)
from k_cli.agents.orchestrator import Orchestrator
from k_cli.core.llm_driver import LLMDriver
from k_cli.git.verifier import Verifier, VerificationResult
from k_cli.git.patcher import Patcher
from k_cli.git.repo_map import RepoMap
from k_cli.tools.doc_retriever import DocRetriever
from k_cli.cli import app


runner = CliRunner()


# ==============================================================================
# 1. Enums & Data Structure Tests
# ==============================================================================

def test_subagent_role_from_str():
    assert SubagentRole.from_str("explorer") == SubagentRole.EXPLORER
    assert SubagentRole.from_str("RESEARCH") == SubagentRole.RESEARCHER
    assert SubagentRole.from_str("refactor") == SubagentRole.REFACTORER
    assert SubagentRole.from_str("TEST") == SubagentRole.TESTER
    assert SubagentRole.from_str("coder") == SubagentRole.CODER
    assert SubagentRole.from_str("critic") == SubagentRole.CRITIC
    assert SubagentRole.from_str("architect") == SubagentRole.ARCHITECT
    assert SubagentRole.from_str("unknown_xyz") == SubagentRole.CODER


def test_subagent_message_json_roundtrip():
    msg = SubagentMessage(
        sender_id="task_1",
        recipient_id="orchestrator",
        msg_type=SubagentMessageType.PROGRESS,
        payload={"progress": 0.5, "status_message": "Analyzing..."},
    )
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert "task_1" in json_str

    parsed = SubagentMessage.from_json(json_str)
    assert parsed.sender_id == "task_1"
    assert parsed.msg_type == SubagentMessageType.PROGRESS
    assert parsed.payload.get("progress") == 0.5


def test_subagent_task_dict_roundtrip():
    task = SubagentTask(
        task_id="test_id_1",
        name="Test Refactoring Task",
        role=SubagentRole.REFACTORER,
        prompt="Refactor auth token function",
        dependencies=["dep_0"],
        progress=0.75,
        status=SubagentStatus.RUNNING,
        status_message="Generating patches",
    )
    d = task.to_dict()
    assert d["task_id"] == "test_id_1"
    assert d["role"] == "REFACTORER"
    assert d["status"] == "RUNNING"
    assert d["progress"] == 0.75

    restored = SubagentTask.from_dict(d)
    assert restored.task_id == "test_id_1"
    assert restored.role == SubagentRole.REFACTORER
    assert restored.status == SubagentStatus.RUNNING
    assert restored.progress == 0.75


# ==============================================================================
# 2. Task Decomposer Tests
# ==============================================================================

def test_task_decomposer_deterministic():
    decomposer = TaskDecomposer()
    tasks = decomposer.decompose(
        prompt="Build JWT token validation with expiry checks",
        context_files=["auth.py"],
    )

    assert len(tasks) == 4
    roles = [t.role for t in tasks]
    assert SubagentRole.EXPLORER in roles
    assert SubagentRole.RESEARCHER in roles
    assert SubagentRole.REFACTORER in roles
    assert SubagentRole.TESTER in roles

    # Verify DAG dependencies
    explorer = next(t for t in tasks if t.role == SubagentRole.EXPLORER)
    researcher = next(t for t in tasks if t.role == SubagentRole.RESEARCHER)
    refactorer = next(t for t in tasks if t.role == SubagentRole.REFACTORER)
    tester = next(t for t in tasks if t.role == SubagentRole.TESTER)

    assert explorer.dependencies == []
    assert researcher.dependencies == []
    assert explorer.task_id in refactorer.dependencies
    assert researcher.task_id in refactorer.dependencies
    assert refactorer.task_id in tester.dependencies


def test_task_decomposer_explicit_roles():
    decomposer = TaskDecomposer()
    tasks = decomposer.decompose(
        prompt="Inspect security boundaries",
        target_roles=[SubagentRole.EXPLORER, SubagentRole.CRITIC],
    )
    assert len(tasks) == 2
    assert tasks[0].role == SubagentRole.EXPLORER
    assert tasks[1].role == SubagentRole.CRITIC


class MockLLMDecomposerDriver(LLMDriver):
    """Driver that returns custom JSON array for decomposition."""
    def __init__(self):
        super().__init__(mock_mode=True)

    def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        if system_prompt and "TASK_DECOMPOSER" in system_prompt:
            return json.dumps([
                {"id": "t1", "name": "Custom Explorer", "role": "EXPLORER", "prompt": "Scan repo", "dependencies": []},
                {"id": "t2", "name": "Custom Tester", "role": "TESTER", "prompt": "Run tests", "dependencies": ["t1"]},
            ])
        return super().generate(prompt, system_prompt, temperature, stream_callback)


def test_task_decomposer_with_llm():
    driver = MockLLMDecomposerDriver()
    decomposer = TaskDecomposer(driver=driver)
    tasks = decomposer.decompose("Custom prompt task", use_llm=True)
    assert len(tasks) == 2
    assert tasks[0].task_id == "t1"
    assert tasks[0].role == SubagentRole.EXPLORER
    assert tasks[1].task_id == "t2"
    assert tasks[1].role == SubagentRole.TESTER
    assert tasks[1].dependencies == ["t1"]


# ==============================================================================
# 3. Subagent Worker Tests
# ==============================================================================

def test_explorer_worker_execution(tmp_path):
    sample_file = tmp_path / "calc.py"
    sample_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    task = SubagentTask(
        task_id="t_exp",
        name="Explore",
        role=SubagentRole.EXPLORER,
        prompt="Explore calc.py functions",
        context={"context_files": ["calc.py"]},
    )
    msg_q = queue.Queue()
    driver = LLMDriver(mock_mode=True)
    worker = SubagentWorker(task=task, message_queue=msg_q, driver=driver, workspace_dir=tmp_path)
    res_task = worker.execute()

    assert res_task.status == SubagentStatus.COMPLETED
    assert res_task.progress == 1.0
    assert "calc.py" in res_task.output_text or "AST" in res_task.output_text
    assert res_task.duration_seconds >= 0.0

    # Verify message queue events
    events = []
    while not msg_q.empty():
        events.append(msg_q.get())
    msg_types = [e.msg_type for e in events]
    assert SubagentMessageType.TASK_INIT in msg_types
    assert SubagentMessageType.EXPLORATION_MAP in msg_types
    assert SubagentMessageType.TASK_COMPLETE in msg_types


def test_researcher_worker_execution():
    task = SubagentTask(
        task_id="t_res",
        name="Research",
        role=SubagentRole.RESEARCHER,
        prompt="Research json.dumps formatting and speed",
    )
    msg_q = queue.Queue()
    driver = LLMDriver(mock_mode=True)
    worker = SubagentWorker(task=task, message_queue=msg_q, driver=driver)
    res_task = worker.execute()

    assert res_task.status == SubagentStatus.COMPLETED
    assert res_task.output_text != ""
    assert res_task.progress == 1.0


def test_refactorer_worker_execution():
    task = SubagentTask(
        task_id="t_refac",
        name="Refactor",
        role=SubagentRole.REFACTORER,
        prompt="Write a memory monitor function",
    )
    msg_q = queue.Queue()
    driver = LLMDriver(mock_mode=True)
    worker = SubagentWorker(task=task, message_queue=msg_q, driver=driver)
    res_task = worker.execute()

    assert res_task.status == SubagentStatus.COMPLETED
    assert "def " in res_task.output_text or "import " in res_task.output_text


def test_tester_worker_execution():
    dep_task = SubagentTask(
        task_id="t_refac",
        name="Refactor",
        role=SubagentRole.REFACTORER,
        prompt="Write code",
        output_text="```python\ndef square(x):\n    return x * x\n```",
    )
    task = SubagentTask(
        task_id="t_test",
        name="Tester",
        role=SubagentRole.TESTER,
        prompt="Verify square function",
        dependencies=["t_refac"],
    )
    msg_q = queue.Queue()
    driver = LLMDriver(mock_mode=True)
    worker = SubagentWorker(task=task, message_queue=msg_q, driver=driver)
    res_task = worker.execute(dependency_results={"t_refac": dep_task})

    assert res_task.status == SubagentStatus.COMPLETED
    assert res_task.verification_result is not None
    assert res_task.verification_result.success is True


def test_worker_error_handling():
    task = SubagentTask(
        task_id="t_err",
        name="Error Task",
        role=SubagentRole.CODER,
        prompt="Cause failure",
    )
    failing_driver = MagicMock()
    failing_driver.generate.side_effect = RuntimeError("Fatal LLM generation crash")

    msg_q = queue.Queue()
    worker = SubagentWorker(task=task, message_queue=msg_q, driver=failing_driver)
    res_task = worker.execute()

    assert res_task.status == SubagentStatus.FAILED
    assert "Fatal LLM generation crash" in res_task.error_trace


# ==============================================================================
# 4. Patch Aggregator Tests
# ==============================================================================

def test_patch_aggregator_with_code_output():
    aggregator = PatchAggregator()
    tasks = [
        SubagentTask(
            task_id="t1",
            name="Explorer",
            role=SubagentRole.EXPLORER,
            prompt="Scan",
            status=SubagentStatus.COMPLETED,
            output_text="Found files: app.py",
        ),
        SubagentTask(
            task_id="t2",
            name="Refactorer",
            role=SubagentRole.REFACTORER,
            prompt="Code",
            status=SubagentStatus.COMPLETED,
            output_text="```python\ndef hello_subagents():\n    return 'success'\n```",
        ),
    ]

    result = aggregator.aggregate(tasks=tasks, total_duration=1.25)
    assert result.success is True
    assert "hello_subagents" in result.final_code
    assert result.verification is not None
    assert result.verification.success is True
    assert result.total_duration_sec == 1.25


def test_patch_aggregator_with_search_replace_blocks():
    aggregator = PatchAggregator()
    patch_text = (
        "<<<<<<< SEARCH\ndef old_func():\n    pass\n=======\ndef new_func():\n    return 100\n>>>>>>>"
    )
    tasks = [
        SubagentTask(
            task_id="t1",
            name="Refactorer",
            role=SubagentRole.REFACTORER,
            prompt="Patch",
            status=SubagentStatus.COMPLETED,
            patch_blocks=[("def old_func():\n    pass", "def new_func():\n    return 100")],
            raw_patch=patch_text,
        )
    ]

    result = aggregator.aggregate(tasks=tasks, total_duration=0.5)
    assert result.success is True
    assert "def old_func():" in result.aggregated_patch
    assert "def new_func():" in result.aggregated_patch


# ==============================================================================
# 5. Subagent Dispatcher & Parallel Execution Tests
# ==============================================================================

def test_subagent_dispatcher_parallel_dag():
    driver = LLMDriver(mock_mode=True)
    verifier = Verifier()
    dispatcher = SubagentDispatcher(driver=driver, verifier=verifier, max_workers=4)

    tasks = [
        SubagentTask(task_id="exp", name="Explorer", role=SubagentRole.EXPLORER, prompt="Find files", dependencies=[]),
        SubagentTask(task_id="res", name="Researcher", role=SubagentRole.RESEARCHER, prompt="Check docs", dependencies=[]),
        SubagentTask(task_id="ref", name="Refactorer", role=SubagentRole.REFACTORER, prompt="Implement code", dependencies=["exp", "res"]),
        SubagentTask(task_id="tst", name="Tester", role=SubagentRole.TESTER, prompt="Verify code", dependencies=["ref"]),
    ]

    captured_events = []
    def on_event(msg):
        captured_events.append(msg)

    result = dispatcher.dispatch(tasks=tasks, event_callback=on_event)

    assert result.success is True
    assert len(result.tasks) == 4
    for t in result.tasks:
        assert t.status == SubagentStatus.COMPLETED

    assert len(captured_events) > 0
    assert result.total_duration_sec > 0.0
    assert result.total_ram_mb > 0.0
    assert result.total_ram_mb < 1024.0


def test_subagent_dispatcher_run_prompt():
    driver = LLMDriver(mock_mode=True)
    dispatcher = SubagentDispatcher(driver=driver, max_workers=4)

    result = dispatcher.run_prompt("Create a high performance Fibonacci calculator")
    assert result.success is True
    assert len(result.tasks) == 4
    assert result.final_code != ""


def test_subagent_dispatcher_upstream_cancellation():
    """Verify that if an upstream task fails, downstream dependent tasks are cancelled."""
    driver = MagicMock()
    # Explorer passes, Researcher fails
    def mock_generate(prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        if "researcher" in (system_prompt or "").lower():
            raise ValueError("Upstream network failure")
        return "```python\ndef stub(): pass\n```"

    driver.generate.side_effect = mock_generate
    dispatcher = SubagentDispatcher(driver=driver, max_workers=2)

    tasks = [
        SubagentTask(task_id="exp", name="Explorer", role=SubagentRole.EXPLORER, prompt="Scan", dependencies=[]),
        SubagentTask(task_id="res", name="Researcher", role=SubagentRole.RESEARCHER, prompt="Docs", dependencies=[]),
        SubagentTask(task_id="ref", name="Refactorer", role=SubagentRole.REFACTORER, prompt="Code", dependencies=["res"]),
    ]

    result = dispatcher.dispatch(tasks=tasks)
    assert result.success is False

    res_task = next(t for t in result.tasks if t.task_id == "res")
    ref_task = next(t for t in result.tasks if t.task_id == "ref")

    assert res_task.status == SubagentStatus.FAILED
    assert ref_task.status == SubagentStatus.CANCELLED


# ==============================================================================
# 6. Visualization Tests
# ==============================================================================

def test_visualizer_render_tree():
    tasks = [
        SubagentTask(task_id="t1", name="Explorer", role=SubagentRole.EXPLORER, prompt="p1", status=SubagentStatus.COMPLETED, duration_seconds=0.2),
        SubagentTask(task_id="t2", name="Refactorer", role=SubagentRole.REFACTORER, prompt="p2", dependencies=["t1"], status=SubagentStatus.RUNNING),
    ]
    tree = SubagentVisualizer.render_tree(tasks, title="Test Tree")
    assert tree is not None
    assert "EXPLORER" in str(tree.label) or len(tree.children) == 2


def test_visualizer_render_dashboard():
    tasks = [
        SubagentTask(task_id="t1", name="Explorer", role=SubagentRole.EXPLORER, prompt="p1", status=SubagentStatus.COMPLETED, progress=1.0, status_message="Done"),
        SubagentTask(task_id="t2", name="Tester", role=SubagentRole.TESTER, prompt="p2", status=SubagentStatus.RUNNING, progress=0.45, status_message="Testing"),
    ]
    panel = SubagentVisualizer.render_dashboard(tasks, current_ram_mb=42.5)
    assert panel is not None
    assert "Subagent" in str(panel.title)


def test_visualizer_live_cli_execution():
    driver = LLMDriver(mock_mode=True)
    dispatcher = SubagentDispatcher(driver=driver, max_workers=2)
    tasks = [
        SubagentTask(task_id="t1", name="Task 1", role=SubagentRole.EXPLORER, prompt="p1"),
        SubagentTask(task_id="t2", name="Task 2", role=SubagentRole.CODER, prompt="p2", dependencies=["t1"]),
    ]
    test_console = Console(record=True, width=100)
    result = SubagentVisualizer.execute_with_live_cli(
        dispatcher=dispatcher,
        tasks=tasks,
        console=test_console,
    )
    assert result.success is True
    assert len(result.tasks) == 2


# ==============================================================================
# 7. Orchestrator & CLI Integration Tests
# ==============================================================================

def test_orchestrator_execute_subagents_integration():
    driver = LLMDriver(mock_mode=True)
    orchestrator = Orchestrator(driver=driver)

    result = orchestrator.execute_subagents(
        user_prompt="Build a thread-safe task queue",
        max_workers=2,
        show_ui=False,
    )

    assert result.success is True
    assert len(result.tasks) == 4
    assert result.final_code != ""
    assert result.total_ram_mb < 1024.0


def test_cli_subagents_command_mock():
    result = runner.invoke(app, ["subagents", "Refactor queue worker", "--mock", "--no-ui"])
    assert result.exit_code == 0
    assert "MULTI-AGENT TASK COMPLETED SUCCESSFULLY" in result.output or "Verified" in result.output


def test_cli_spawn_command_alias_mock():
    result = runner.invoke(app, ["spawn", "Build token serializer", "--mock", "--no-ui"])
    assert result.exit_code == 0
    assert "MULTI-AGENT TASK COMPLETED SUCCESSFULLY" in result.output or "Verified" in result.output


def test_cli_subagents_with_save_to(tmp_path):
    save_file = tmp_path / "subagent_output.py"
    result = runner.invoke(app, [
        "subagents",
        "Implement binary search",
        "--mock",
        "--no-ui",
        "--save-to", str(save_file),
    ])
    assert result.exit_code == 0
    assert save_file.exists()
    assert len(save_file.read_text(encoding="utf-8").strip()) > 0


def test_top_level_execute_subagents_helper():
    driver = LLMDriver(mock_mode=True)
    res = execute_subagents(
        prompt="Design rate limiter",
        driver=driver,
        show_ui=False,
        max_workers=2,
    )
    assert isinstance(res, SubagentRunResult)
    assert res.success is True
    assert len(res.tasks) == 4
