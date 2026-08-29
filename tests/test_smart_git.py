"""
test_smart_git.py - Comprehensive Unit & Integration Test Suite for SmartGitEngine
Project Bankai Engine v1.0.0

Tests:
1. AST Symbol Extraction: classes, member methods, standalone functions, async functions.
2. Conventional Commit Classification: feat, fix, refactor, test, docs, perf, chore, security.
3. Scope extraction heuristics.
4. Smart Commit Generation:
   - Clean working tree detection
   - Feature addition with new AST symbols
   - Bug fix detection
   - Documentation & test changes
   - Security hardening changes
   - Atomic commit grouping for multi-file changesets
5. Auto-Stage & Commit execution.
6. Pull Request Markdown Description generation (Architecture Impact, Key Changes, Verification Checklist, Diff Stats).
7. Typer CLI `k-cli commit` command execution and JSON output.
"""

import ast
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from k_cli.git.smart_git import (
    AtomicCommitGroup,
    CommitType,
    FileChangeAnalysis,
    PRDescriptionProposal,
    SmartCommitProposal,
    SmartGitEngine,
)
from k_cli.cli import app

runner = CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path):
    """Creates a temporary initialized git repository fixture."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"

    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, env=env)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True, env=env)

    # Create initial commit
    init_file = repo_dir / "README.md"
    init_file.write_text("# Test Repo\nInitial readme", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo_dir), check=True, env=env)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=str(repo_dir), check=True, env=env)

    return repo_dir


def test_ast_symbol_extraction():
    """Tests extraction of functions, async functions, classes, and methods."""
    sample_code = '''
"""Module docstring."""

def regular_func(a: int, b: str = "default") -> bool:
    """Helper function."""
    return True

async def async_fetch_data(url: str):
    """Async fetcher."""
    pass

class DataProcessor:
    """Class for data processing."""
    def __init__(self, name: str):
        self.name = name

    def process(self, items: list) -> int:
        """Process items."""
        return len(items)

    async def async_flush(self):
        pass
'''
    symbols = SmartGitEngine._extract_ast_symbols(sample_code)

    assert "regular_func" in symbols
    assert symbols["regular_func"]["type"] == "function"
    assert symbols["regular_func"]["args"] == ["a", "b"]

    assert "async_fetch_data" in symbols
    assert symbols["async_fetch_data"]["type"] == "async_function"

    assert "DataProcessor" in symbols
    assert symbols["DataProcessor"]["type"] == "class"
    assert "process" in symbols["DataProcessor"]["methods"]

    assert "DataProcessor.process" in symbols
    assert symbols["DataProcessor.process"]["type"] == "method"
    assert symbols["DataProcessor.process"]["args"] == ["self", "items"]


def test_conventional_commit_type_inference():
    """Tests inference of Conventional Commit types based on file paths and AST diff signals."""
    # Test file
    t_test = SmartGitEngine._infer_commit_type("tests/test_auth.py", "+ def test_login(): pass", [], [], [])
    assert t_test == CommitType.TEST.value

    # Docs file
    t_docs = SmartGitEngine._infer_commit_type("docs/architecture.md", "+ # Architecture Overview", [], [], [])
    assert t_docs == CommitType.DOCS.value

    # Security file
    t_sec = SmartGitEngine._infer_commit_type("src/security.py", "+ def sanitize_sql_input(): pass", [], [], [])
    assert t_sec == CommitType.SECURITY.value

    # Chore file
    t_chore = SmartGitEngine._infer_commit_type("pyproject.toml", "+ pytest >= 8.0", [], [], [])
    assert t_chore == CommitType.CHORE.value

    # Perf keyword
    t_perf = SmartGitEngine._infer_commit_type("src/cache.py", "+ # Add LRU cache optimize speedup", [], [], [])
    assert t_perf == CommitType.PERF.value

    # Bug fix keyword
    t_fix = SmartGitEngine._infer_commit_type("src/engine.py", "+ # Fix crash bug when handling NoneType", [], [], [])
    assert t_fix == CommitType.FIX.value

    # Feature addition
    t_feat = SmartGitEngine._infer_commit_type("src/api.py", "+ def new_endpoint(): pass", ["new_endpoint"], [], [])
    assert t_feat == CommitType.FEAT.value

    # Refactor
    t_refactor = SmartGitEngine._infer_commit_type("src/api.py", "- def old(): pass\n+ def new(): pass", [], ["update_api"], ["old_api"])
    assert t_refactor == CommitType.REFACTOR.value


def test_scope_inference():
    """Tests scope extraction from directory and file paths."""
    assert SmartGitEngine._infer_scope("k_cli/smart_git.py") == "smart_git"
    assert SmartGitEngine._infer_scope("src/auth/jwt.py") == "auth"
    assert SmartGitEngine._infer_scope("tests/test_verifier.py") == "test"
    assert SmartGitEngine._infer_scope("security_healer.py") == "security_healer"


def test_generate_smart_commit_clean_workspace(temp_git_repo):
    """Tests proposal generation when working tree is completely clean."""
    engine = SmartGitEngine(repo_path=str(temp_git_repo))
    proposal = engine.generate_smart_commit()

    assert isinstance(proposal, SmartCommitProposal)
    assert proposal.files_changed == []
    assert "clean" in proposal.body.lower() or "no uncommitted" in proposal.subject.lower()


def test_generate_smart_commit_feature_addition(temp_git_repo):
    """Tests proposal generation when a new feature with functions/classes is added."""
    engine = SmartGitEngine(repo_path=str(temp_git_repo))

    feature_file = temp_git_repo / "analytics.py"
    feature_file.write_text(
        '''
class MetricCollector:
    """Collects real-time system metrics."""
    def record(self, metric_name: str, value: float):
        pass

def compute_percentiles(values: list) -> dict:
    """Computes p50, p90, p99."""
    return {"p50": 0, "p90": 0, "p99": 0}
''',
        encoding="utf-8",
    )

    proposal = engine.generate_smart_commit()

    assert proposal.commit_type == "feat"
    assert "analytics.py" in proposal.files_changed
    assert len(proposal.file_analyses) == 1
    assert "MetricCollector" in proposal.file_analyses[0].symbols_added
    assert "compute_percentiles" in proposal.file_analyses[0].symbols_added
    assert "Why:" in proposal.body
    assert "What:" in proposal.body
    assert "analytics.py" in proposal.body


def test_generate_smart_commit_multi_file_atomic_grouping(temp_git_repo):
    """Tests atomic commit grouping across mixed domain changes (source, test, docs)."""
    engine = SmartGitEngine(repo_path=str(temp_git_repo))

    # 1. Source feature
    (temp_git_repo / "calc.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    # 2. Test file
    (temp_git_repo / "tests").mkdir()
    (temp_git_repo / "tests" / "test_calc.py").write_text("def test_add(): assert add(1, 2) == 3\n", encoding="utf-8")
    # 3. Docs file
    (temp_git_repo / "docs.md").write_text("# Math API Documentation\n", encoding="utf-8")

    proposal = engine.generate_smart_commit()

    assert len(proposal.files_changed) == 3
    assert len(proposal.atomic_groups) >= 2

    group_types = {g.commit_type for g in proposal.atomic_groups}
    assert "feat" in group_types or "chore" in group_types
    assert "test" in group_types
    assert "docs" in group_types


def test_auto_stage_and_commit(temp_git_repo):
    """Tests staging and committing changes via SmartGitEngine."""
    engine = SmartGitEngine(repo_path=str(temp_git_repo))

    new_file = temp_git_repo / "engine.py"
    new_file.write_text("def run_engine(): pass\n", encoding="utf-8")

    proposal = engine.generate_smart_commit()
    success = engine.auto_stage_and_commit(message=proposal.full_message, push=False)
    assert success is True

    # Confirm clean working tree after commit
    status_files = engine.get_status_files()
    assert len(status_files) == 0


def test_generate_pr_description(temp_git_repo):
    """Tests PR title and Markdown description synthesis."""
    engine = SmartGitEngine(repo_path=str(temp_git_repo))

    # Create new branch
    subprocess.run(["git", "checkout", "-b", "feature/smart-git"], cwd=str(temp_git_repo), check=True)

    # Add changes and commit
    (temp_git_repo / "auth.py").write_text(
        '''
def verify_jwt_signature(token: str) -> bool:
    """Verifies JWT token signature."""
    return True
''',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(temp_git_repo), check=True)
    subprocess.run(["git", "commit", "-m", "feat(auth): implement JWT token verification"], cwd=str(temp_git_repo), check=True)

    pr = engine.generate_pr_description(branch="feature/smart-git", base="master" if "master" in engine.get_current_branch() else "main")

    assert isinstance(pr, PRDescriptionProposal)
    assert "feat" in pr.title.lower() or "auth" in pr.title.lower()
    assert "## 📌 Summary of Changes" in pr.body
    assert "## 🏗️ Architecture & System Impact" in pr.body
    assert "## 🔍 Key Modifications" in pr.body
    assert "## ✅ Verification & Testing Checklist" in pr.body
    assert "## 📊 Diff Statistics" in pr.body
    assert "auth.py" in pr.files_changed


def test_cli_commit_command(temp_git_repo):
    """Tests running `k-cli commit` via Typer CLI runner."""
    # Modify a file
    (temp_git_repo / "service.py").write_text("def serve_traffic(): pass\n", encoding="utf-8")

    # Run JSON mode
    result_json = runner.invoke(app, ["commit", "--repo", str(temp_git_repo), "--json"])
    assert result_json.exit_code == 0
    data = json.loads(result_json.stdout)
    assert data["commit_type"] == "feat"
    assert "service.py" in data["files_changed"]

    # Run actual commit
    result_commit = runner.invoke(app, ["commit", "--repo", str(temp_git_repo), "--all"])
    assert result_commit.exit_code == 0
    assert "Changes committed successfully" in result_commit.stdout
