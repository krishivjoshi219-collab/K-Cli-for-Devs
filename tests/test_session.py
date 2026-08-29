"""
test_session.py - Unit and Integration Tests for SessionManager (Milestone 5)

Tests SessionManager context management, token budgeting, slash command routing,
undo workflows, multi-turn conversation state, DevDocs/RepoMap injection, and streaming execution.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import pytest

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from k_cli.core.session import SessionManager
from k_cli.tools.doc_retriever import DocRetriever
from k_cli.git.repo_map import RepoMap
from k_cli.git.patcher import Patcher
from k_cli.git.git_guard import GitGuard
from k_cli.git.verifier import Verifier
from k_cli.core.llm_driver import LLMDriver
from k_cli.agents.orchestrator import Orchestrator


@pytest.fixture
def temp_git_workspace(tmp_path: Path):
    """Initializes a fresh git repository in a temporary directory with initial commit."""
    workspace = tmp_path / "session_git_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@k-cli.local"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "K-CLI Test Runner"], cwd=workspace, check=True, capture_output=True)

    init_file = workspace / "main.py"
    init_file.write_text(
        'def add(a: int, b: int) -> int:\n    """Adds two integers."""\n    return a + b\n',
        encoding="utf-8",
    )
    helper_file = workspace / "helper.py"
    helper_file.write_text(
        'def multiply(a: int, b: int) -> int:\n    return a * b\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=workspace, check=True, capture_output=True)
    return workspace


# ==============================================================================
# 1. Initialization and Context File Management Tests
# ==============================================================================

def test_session_manager_default_init(tmp_path: Path):
    """Verify SessionManager initializes with proper defaults."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    assert session.workspace_dir == tmp_path.resolve()
    assert session.model_name == "qwen2.5-coder:1.5b"
    assert session.max_tokens == 4096
    assert session.context_files == []
    assert session.history == []
    assert session.doc_retriever is not None
    assert session.repo_map is not None
    assert session.patcher is not None
    assert session.git_guard is not None
    assert session.verifier is not None


def test_session_add_and_remove_file(temp_git_workspace: Path):
    """Verify add_file and remove_file behavior."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    # Adding valid relative path
    assert session.add_file("main.py") is True
    assert "main.py" in session.get_context_files()

    # Adding duplicate is idempotent
    assert session.add_file("main.py") is True
    assert len(session.get_context_files()) == 1

    # Adding valid absolute path
    abs_helper = temp_git_workspace / "helper.py"
    assert session.add_file(str(abs_helper)) is True
    assert len(session.get_context_files()) == 2

    # Adding non-existent file returns False
    assert session.add_file("non_existent.py") is False

    # Adding directory returns False
    sub_dir = temp_git_workspace / "subdir"
    sub_dir.mkdir()
    assert session.add_file(str(sub_dir)) is False

    # Removing file
    assert session.remove_file("main.py") is True
    assert "main.py" not in session.get_context_files()
    assert len(session.get_context_files()) == 1

    # Removing non-tracked file returns False
    assert session.remove_file("never_tracked.py") is False


def test_session_status_and_set_model(temp_git_workspace: Path):
    """Verify get_status output and model switching."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), model_name="qwen2.5-coder:1.5b", mock_mode=True)
    session.add_file("main.py")

    status = session.get_status()
    assert isinstance(status, dict)
    assert status["model"] == "qwen2.5-coder:1.5b"
    assert "main.py" in status["context_files"]
    assert status["turns"] == 0
    assert status["ram_mb"] > 0
    assert status["is_git_repo"] is True

    session.set_model("llama3:8b")
    assert session.model_name == "llama3:8b"
    assert session.get_status()["model"] == "llama3:8b"


# ==============================================================================
# 2. History, Reset & Token Budget Pruning Tests
# ==============================================================================

def test_session_clear_and_reset(temp_git_workspace: Path):
    """Verify clear_history and reset_context."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)
    session.add_file("main.py")
    session.history.append({"prompt": "Hello", "response": "World"})

    assert len(session.get_context_files()) == 1
    assert len(session.history) == 1

    session.clear_history()
    assert len(session.history) == 0
    assert len(session.get_context_files()) == 1

    session.history.append({"prompt": "Hello again", "response": "World again"})
    session.reset_context()
    assert len(session.history) == 0
    assert len(session.get_context_files()) == 0


def test_session_rolling_token_budget_pruning(temp_git_workspace: Path):
    """Verify that history is pruned when token count exceeds max_tokens."""
    # Set extremely small token budget
    session = SessionManager(workspace_dir=str(temp_git_workspace), max_tokens=20, mock_mode=True)

    # Add multiple long turns
    for i in range(5):
        session.history.append({
            "prompt": f"This is user turn number {i} with lots of descriptive words to consume tokens",
            "response": f"This is assistant response number {i} with even more descriptive code words",
        })
        session._prune_history_if_needed()

    # Oldest turns should have been pruned
    assert len(session.history) < 5


# ==============================================================================
# 3. Git Undo & Diff Integration Tests
# ==============================================================================

def test_session_undo_and_diff(temp_git_workspace: Path):
    """Verify undo_last_edit and /diff handling."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    # Clean working tree: undo returns False
    success, msg = session.undo_last_edit()
    assert success is False
    assert "no" in msg.lower() or "clean" in msg.lower()

    # Modify file
    main_file = temp_git_workspace / "main.py"
    orig_text = main_file.read_text(encoding="utf-8")
    main_file.write_text("# Corrupted edit\n", encoding="utf-8")

    # Undo should restore file
    success, msg = session.undo_last_edit()
    assert success is True
    assert main_file.read_text(encoding="utf-8") == orig_text


def test_session_undo_non_git_workspace(tmp_path: Path):
    """Verify undo_last_edit in non-git directory returns False gracefully."""
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    session = SessionManager(workspace_dir=str(plain_dir), mock_mode=True)
    success, msg = session.undo_last_edit()
    assert success is False
    assert "git" in msg.lower()


# ==============================================================================
# 4. Slash Commands Routing Tests
# ==============================================================================

def test_slash_command_help(temp_git_workspace: Path):
    """Verify /help returns command listing."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)
    handled, out = session.handle_slash_command("/help")
    assert handled is True
    assert "/add" in out
    assert "/undo" in out
    assert "/diff" in out
    assert "/clear" in out
    assert "/status" in out


def test_slash_command_add_and_remove(temp_git_workspace: Path):
    """Verify /add and /remove slash commands."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    handled, out = session.handle_slash_command("/add main.py")
    assert handled is True
    assert "Added" in out
    assert "main.py" in session.get_context_files()

    handled, out = session.handle_slash_command("/add missing.py")
    assert handled is True
    assert "not found" in out.lower() or "Error" in out

    handled, out = session.handle_slash_command("/remove main.py")
    assert handled is True
    assert "Removed" in out
    assert "main.py" not in session.get_context_files()


def test_slash_command_diff_and_undo(temp_git_workspace: Path):
    """Verify /diff and /undo slash commands."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    handled, out = session.handle_slash_command("/diff")
    assert handled is True
    assert "clean" in out.lower() or "no uncommitted" in out.lower()

    # Modify file
    (temp_git_workspace / "main.py").write_text("# new change\n", encoding="utf-8")

    handled, out = session.handle_slash_command("/diff")
    assert handled is True
    assert "main.py" in out or "# new change" in out

    handled, out = session.handle_slash_command("/undo")
    assert handled is True
    assert "Successfully" in out or "rolled back" in out.lower()


def test_slash_command_status_and_model(temp_git_workspace: Path):
    """Verify /status and /model slash commands."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    handled, out = session.handle_slash_command("/status")
    assert handled is True
    assert "Active Model" in out
    assert "Memory RSS" in out

    handled, out = session.handle_slash_command("/model")
    assert handled is True
    assert "qwen2.5-coder" in out

    handled, out = session.handle_slash_command("/model deepseek-coder:1.3b")
    assert handled is True
    assert "deepseek-coder:1.3b" in out
    assert session.model_name == "deepseek-coder:1.3b"


def test_slash_command_doc_and_map(temp_git_workspace: Path):
    """Verify /doc and /map slash commands."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    handled, out = session.handle_slash_command("/doc os.path.join")
    assert handled is True

    handled, out = session.handle_slash_command("/map")
    assert handled is True
    assert "main.py" in out or "helper.py" in out


def test_slash_command_exit_and_unknown(temp_git_workspace: Path):
    """Verify /exit, /quit, and unknown command handling."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)

    handled, out = session.handle_slash_command("/exit")
    assert handled is True
    assert out == "EXIT"

    handled, out = session.handle_slash_command("/quit")
    assert handled is True
    assert out == "EXIT"

    handled, out = session.handle_slash_command("/invalid_command")
    assert handled is False
    assert "Unknown command" in out

    handled, out = session.handle_slash_command("Normal prompt without slash")
    assert handled is False


# ==============================================================================
# 5. Turn Execution & Streaming Tests
# ==============================================================================

def test_session_process_turn_empty_prompt(temp_git_workspace: Path):
    """Verify process_turn with empty prompt returns safely."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)
    gen = session.process_turn("")
    tokens = list(gen)
    assert tokens == []
    assert session.last_result["success"] is True


def test_session_process_turn_mock_generation(temp_git_workspace: Path):
    """Verify process_turn generates tokens and updates history."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)
    session.add_file("main.py")

    gen = session.process_turn("Write a function to compute fibonacci numbers")
    tokens = list(gen)
    assert len(tokens) > 0

    res = session.last_result
    assert res is not None
    assert res["success"] is True
    assert len(session.history) == 1
    assert session.history[0]["prompt"] == "Write a function to compute fibonacci numbers"


def test_session_execute_turn_synchronous(temp_git_workspace: Path):
    """Verify execute_turn synchronous wrapper."""
    session = SessionManager(workspace_dir=str(temp_git_workspace), mock_mode=True)
    res = session.execute_turn("Write a greeting function")
    assert isinstance(res, dict)
    assert res.get("success") is True
    assert res.get("ram_mb", 0) > 0
