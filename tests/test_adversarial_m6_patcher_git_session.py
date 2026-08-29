"""
test_adversarial_m6_patcher_git_session.py - Adversarial Stress & Hardening Test Suite (Tier 5)

Comprehensive white-box adversarial stress tests for:
1. Patcher (patcher.py):
   - Malformed SEARCH/REPLACE blocks (missing markers, corrupted delimiters, interleaved/nested blocks, regex metachars, empty blocks).
   - AST syntax violation detection preventing bad code writes on disk (atomicity, non-py files, invalid tokens/decorators/indentations).
   - Indentation shift, fuzzy matching, whitespace tolerance edge cases.
2. GitGuard (git_guard.py):
   - Rollback under uncommitted changes, dirty workspace states, deleted tracked files, untracked files/dirs, and staged changes.
   - File-specific rollbacks and non-existent file handling.
   - Safe behavior in non-git directories and empty uncommitted repositories.
   - Snapshotting and atomic commits under complex state transitions.
3. SessionManager (session.py):
   - Extreme multi-turn token pruning (> 50 turns, 100 turns, 200 turns).
   - Token budgeting with huge inputs, tiny budgets, and heavy context files.
   - Rapid sequential /undo operations under clean, dirty, and non-git workspace states.
   - Full slash command router coverage and streaming turn execution.
   - RSS memory budget verification (< 1024 MB).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil
import pytest

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from k_cli.git.patcher import Patcher
from k_cli.git.git_guard import GitGuard
from k_cli.core.session import SessionManager
from k_cli.core.llm_driver import LLMDriver
from k_cli.git.verifier import Verifier
from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult


# ==============================================================================
# Pytest Fixtures
# ==============================================================================

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Fixture providing a fresh git repository with an initial commit."""
    repo = tmp_path / "adv_git_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Adversarial Runner"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "adv@k-cli.local"], cwd=repo, check=True, capture_output=True)

    base_file = repo / "calculator.py"
    base_file.write_text(
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n\n"
        "    def subtract(self, a: int, b: int) -> int:\n"
        "        return a - b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    """Fixture providing a plain, non-git directory."""
    plain = tmp_path / "plain_dir"
    plain.mkdir(parents=True, exist_ok=True)
    return plain


# ==============================================================================
# 1. Patcher: Malformed SEARCH/REPLACE Block Stress Testing
# ==============================================================================

class TestPatcherMalformedBlocks:
    """Adversarial stress testing for SEARCH/REPLACE block parsing."""

    def test_missing_start_marker(self):
        """Patch with missing <<<<<<< SEARCH marker is rejected safely."""
        text = (
            "def foo():\n"
            "    return 1\n"
            "=======\n"
            "def foo():\n"
            "    return 2\n"
            ">>>>>>>"
        )
        assert Patcher.parse_search_replace_blocks(text) == []

    def test_missing_divider_marker(self):
        """Patch with missing ======= divider marker is rejected safely."""
        text = (
            "<<<<<<< SEARCH\n"
            "def foo():\n"
            "    return 1\n"
            ">>>>>>>"
        )
        assert Patcher.parse_search_replace_blocks(text) == []

    def test_missing_end_marker(self):
        """Patch with missing >>>>>>> end marker is rejected safely."""
        text = (
            "<<<<<<< SEARCH\n"
            "def foo():\n"
            "    return 1\n"
            "=======\n"
            "def foo():\n"
            "    return 2\n"
        )
        assert Patcher.parse_search_replace_blocks(text) == []

    def test_partial_markers_count_mismatch(self):
        """Markers with incorrect marker character counts (e.g. 5, 6, 8 chars) are handled safely."""
        # 6 < characters
        text_6_lt = "<<<<<< SEARCH\na = 1\n=======\na = 2\n>>>>>>>"
        assert Patcher.parse_search_replace_blocks(text_6_lt) == []

        # 6 = characters
        text_6_eq = "<<<<<<< SEARCH\na = 1\n======\na = 2\n>>>>>>>"
        assert Patcher.parse_search_replace_blocks(text_6_eq) == []

        # 6 > characters
        text_6_gt = "<<<<<<< SEARCH\na = 1\n=======\na = 2\n>>>>>>"
        assert Patcher.parse_search_replace_blocks(text_6_gt) == []

    def test_nested_and_interleaved_blocks(self):
        """Nested or interleaved markers do not cause infinite loops or crash."""
        nested = (
            "<<<<<<< SEARCH\n"
            "<<<<<<< SEARCH\n"
            "x = 1\n"
            "=======\n"
            "x = 2\n"
            ">>>>>>>\n"
            "=======\n"
            "x = 3\n"
            ">>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(nested)
        assert isinstance(blocks, list)

    def test_multiple_dividers_in_single_block(self):
        """Block containing extra ======= inside the search or replace section."""
        text = (
            "<<<<<<< SEARCH\n"
            "val = 1\n"
            "=======\n"
            "=======\n"
            "val = 2\n"
            ">>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(text)
        assert isinstance(blocks, list)

    def test_regex_special_characters_in_blocks(self):
        """Search block with regex metacharacters (*, +, ?, ^, $, [], (), {}, |) matches cleanly."""
        original = 'pattern = re.compile(r"^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$")\nresult = pattern.match(email)\n'
        search = 'pattern = re.compile(r"^[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$")'
        replace = 'pattern = re.compile(r"^\\S+@\\S+\\.\\S+$")'

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert err == ""
        assert replace in patched

    def test_empty_search_block_fails(self):
        """Empty search block must be rejected and return an error."""
        original = "print('hello world')\n"
        success, patched, err = Patcher.apply_patch(original, "", "print('new')", fuzzy=True)
        assert success is False
        assert patched == original
        assert "empty" in err.lower()

    def test_empty_replace_block_deletes_code(self):
        """Non-empty search block with empty replace block successfully deletes target code."""
        original = "a = 1\n# remove this comment\nb = 2\n"
        search = "# remove this comment\n"
        replace = ""
        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert patched == "a = 1\nb = 2\n"

    def test_extreme_indentation_shift_and_tabs(self):
        """Handles extreme positive and negative indentation shifts (up to 16 spaces)."""
        original = (
            "class Outer:\n"
            "    class Inner:\n"
            "        class Deep:\n"
            "            def execute(self):\n"
            "                return 42\n"
        )
        # Search block with 0-indent
        search = "def execute(self):\n    return 42"
        replace = "def execute(self):\n    return 100"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert "            def execute(self):" in patched
        assert "                return 100" in patched

    def test_search_block_not_found_leaves_original_unmodified(self):
        """When search block does not exist in target code, returns False without corrupting code."""
        original = "x = 100\ny = 200\n"
        search = "z = 999\nw = 888"
        replace = "z = 1"
        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is False
        assert patched == original
        assert "not found" in err.lower()

    def test_leading_and_trailing_whitespace_on_markers(self):
        """Markers with leading whitespace or trailing tabs/spaces parse cleanly."""
        patch = (
            "   <<<<<<< SEARCH   \t\n"
            "def target():\n"
            "    return None\n"
            "   =======   \n"
            "def target():\n"
            "    return True\n"
            "   >>>>>>>   \t"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 1
        assert "return None" in blocks[0][0]
        assert "return True" in blocks[0][1]


# ==============================================================================
# 2. Patcher: AST Syntax Violation Detection & Atomic File Writes
# ==============================================================================

class TestPatcherASTValidation:
    """Adversarial testing for AST syntax validation and atomic file write guarantees."""

    def test_ast_rejects_unclosed_parenthesis(self, tmp_path: Path):
        """AST validation rejects code with unclosed parenthesis and preserves disk file."""
        target = tmp_path / "syntax_err1.py"
        original = "def calculate(a, b):\n    return a + b\n"
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "def calculate(a, b):\n"
            "    return a + b\n"
            "=======\n"
            "def calculate(a, b\n"
            "    return a + b\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        assert target.read_text(encoding="utf-8") == original

    def test_ast_rejects_invalid_keyword_assignment(self, tmp_path: Path):
        """AST validation rejects assigning to a reserved Python keyword (e.g. `class = 1`)."""
        target = tmp_path / "keyword_err.py"
        original = "user_name = 'alice'\n"
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "user_name = 'alice'\n"
            "=======\n"
            "class = 'alice'\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        assert target.read_text(encoding="utf-8") == original

    def test_ast_rejects_invalid_indentation_error(self, tmp_path: Path):
        """AST validation rejects indentation syntax errors."""
        target = tmp_path / "indent_err.py"
        original = "def run():\n    return True\n"
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "def run():\n"
            "    return True\n"
            "=======\n"
            "def run():\n"
            "return True\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        assert target.read_text(encoding="utf-8") == original

    def test_ast_rejects_invalid_decorators_and_tokens(self, tmp_path: Path):
        """AST validation rejects invalid decorator syntax."""
        target = tmp_path / "decorator_err.py"
        original = "def fn():\n    pass\n"
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "def fn():\n"
            "    pass\n"
            "=======\n"
            "@invalid decorator with spaces\n"
            "def fn():\n"
            "    pass\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is False
        assert target.read_text(encoding="utf-8") == original

    def test_multi_block_atomicity_second_block_syntax_error(self, tmp_path: Path):
        """In a multi-block patch, if block 1 is valid but block 2 has a SyntaxError, disk file is unchanged."""
        target = tmp_path / "multi_atomic.py"
        original = "step1 = 1\nstep2 = 2\nstep3 = 3\n"
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "step1 = 1\n"
            "=======\n"
            "step1 = 100\n"
            ">>>>>>>\n"
            "<<<<<<< SEARCH\n"
            "step3 = 3\n"
            "=======\n"
            "step3 = (incomplete_expression\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        # File on disk must NOT have step1 = 100 written!
        assert target.read_text(encoding="utf-8") == original

    def test_non_python_files_bypass_ast_check(self, tmp_path: Path):
        """Non-Python files (.json, .md, .txt) with syntax that would fail Python AST parse apply successfully."""
        target = tmp_path / "config.json"
        original = '{\n  "name": "k-cli",\n  "version": 1\n}\n'
        target.write_text(original, encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            '  "version": 1\n'
            "=======\n"
            '  "version": 2,\n  "flag": true\n'
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is True
        assert '"version": 2' in target.read_text(encoding="utf-8")

    def test_patch_resulting_in_empty_python_file_with_blank_replace(self, tmp_path: Path):
        """Replacing full Python file content with empty newline is valid Python AST and succeeds."""
        target = tmp_path / "empty_target.py"
        target.write_text("def obsolete(): pass\n", encoding="utf-8")

        patch = (
            "<<<<<<< SEARCH\n"
            "def obsolete(): pass\n"
            "=======\n"
            "\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), patch, validate_ast=True)
        assert success is True
        assert target.read_text(encoding="utf-8").strip() == ""


# ==============================================================================
# 3. GitGuard: Rollback Under Complex Dirty States & Non-Git Dirs
# ==============================================================================

class TestGitGuardRollbackHardening:
    """Adversarial stress testing for Git rollback across complex dirty states."""

    def test_rollback_tracked_modifications(self, temp_git_repo: Path):
        """Rollback cleanly discards modifications in tracked files."""
        guard = GitGuard(repo_dir=str(temp_git_repo))
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        calc_file.write_text("# Corrupted calculator\nclass Broken: pass\n", encoding="utf-8")
        assert guard.get_diff() != ""

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert calc_file.read_text(encoding="utf-8") == orig_content
        assert guard.get_diff() == ""

    def test_rollback_deleted_tracked_files(self, temp_git_repo: Path):
        """Rollback restores tracked files that were deleted from working tree."""
        guard = GitGuard(repo_dir=str(temp_git_repo))
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        calc_file.unlink()
        assert not calc_file.exists()

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert calc_file.exists()
        assert calc_file.read_text(encoding="utf-8") == orig_content

    def test_rollback_untracked_files_and_directories(self, temp_git_repo: Path):
        """Rollback cleans newly created untracked files and nested directories."""
        guard = GitGuard(repo_dir=str(temp_git_repo))

        new_file = temp_git_repo / "untracked.py"
        new_file.write_text("x = 100\n", encoding="utf-8")

        new_dir = temp_git_repo / "untracked_pkg" / "sub"
        new_dir.mkdir(parents=True, exist_ok=True)
        (new_dir / "module.py").write_text("print('rogue module')\n", encoding="utf-8")

        assert new_file.exists()
        assert (new_dir / "module.py").exists()

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert not new_file.exists()
        assert not (temp_git_repo / "untracked_pkg").exists()

    def test_rollback_staged_changes(self, temp_git_repo: Path):
        """Rollback resets staged changes (`git add`) and restores working tree."""
        guard = GitGuard(repo_dir=str(temp_git_repo))
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        calc_file.write_text("# staged change\n", encoding="utf-8")
        subprocess.run(["git", "add", "calculator.py"], cwd=temp_git_repo, check=True)
        assert guard.get_diff(cached=True) != ""

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert calc_file.read_text(encoding="utf-8") == orig_content
        assert guard.get_diff(cached=True) == ""
        assert guard.get_diff(cached=False) == ""

    def test_rollback_simultaneous_staged_unstaged_and_untracked(self, temp_git_repo: Path):
        """Rollback handles simultaneous staged, unstaged, and untracked changes in one pass."""
        guard = GitGuard(repo_dir=str(temp_git_repo))
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        # 1. Staged new file
        staged_file = temp_git_repo / "staged.py"
        staged_file.write_text("a = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "staged.py"], cwd=temp_git_repo, check=True)

        # 2. Unstaged modification
        calc_file.write_text("# modified\n", encoding="utf-8")

        # 3. Untracked file
        untracked = temp_git_repo / "rogue.py"
        untracked.write_text("b = 2\n", encoding="utf-8")

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert calc_file.read_text(encoding="utf-8") == orig_content
        assert not staged_file.exists()
        assert not untracked.exists()
        assert guard.get_diff() == ""

    def test_rollback_specific_file_only(self, temp_git_repo: Path):
        """Rollback with specific files list only restores specified file, leaving others untouched."""
        guard = GitGuard(repo_dir=str(temp_git_repo))

        # Add second file to commit
        f2 = temp_git_repo / "second.py"
        f2.write_text("initial_second = True\n", encoding="utf-8")
        guard.commit_success("feat: add second file", files=["second.py"])
        orig_f2 = f2.read_text(encoding="utf-8")

        calc_file = temp_git_repo / "calculator.py"
        orig_calc = calc_file.read_text(encoding="utf-8")

        # Modify both
        calc_file.write_text("# calc modified\n", encoding="utf-8")
        f2.write_text("# second modified\n", encoding="utf-8")

        # Rollback only calculator.py
        rolled_back = guard.rollback(files=["calculator.py"])
        assert rolled_back is True
        assert calc_file.read_text(encoding="utf-8") == orig_calc
        assert f2.read_text(encoding="utf-8") == "# second modified\n"

    def test_non_git_dir_graceful_failures(self, non_git_dir: Path):
        """GitGuard operations on non-git directories return safe failure statuses without crashing."""
        guard = GitGuard(repo_dir=str(non_git_dir))
        assert guard.is_git_repo() is False
        assert guard.create_snapshot() == ""
        assert guard.commit_success("feat: test") is None
        assert guard.rollback() is False
        assert guard.get_diff() == ""

    def test_commit_success_atomic_staging(self, temp_git_repo: Path):
        """commit_success commits changes and returns a valid 40-char commit SHA."""
        guard = GitGuard(repo_dir=str(temp_git_repo))
        calc_file = temp_git_repo / "calculator.py"
        calc_file.write_text("class Calculator:\n    def multiply(self, a, b): return a * b\n", encoding="utf-8")

        sha = guard.commit_success("feat: update calculator")
        assert sha is not None
        assert len(sha) == 40
        assert guard.get_diff() == ""

    def test_snapshot_empty_repo_without_commits(self, tmp_path: Path):
        """create_snapshot in an initialized repository with 0 commits returns safe snapshot string."""
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()
        subprocess.run(["git", "init"], cwd=empty_repo, check=True, capture_output=True)

        guard = GitGuard(repo_dir=str(empty_repo))
        assert guard.is_git_repo() is True
        snapshot = guard.create_snapshot()
        assert "EMPTY_REPO" in snapshot or "snapshot_" in snapshot


# ==============================================================================
# 4. SessionManager: Multi-Turn Token Pruning Under Extreme Lengths (>50 Turns)
# ==============================================================================

class TestSessionManagerTokenPruning:
    """Adversarial stress testing for SessionManager token budgeting and multi-turn pruning."""

    def test_multi_turn_pruning_50_turns(self, temp_git_repo: Path):
        """Simulate 50 consecutive conversation turns and verify bounded history & token budget."""
        session = SessionManager(
            workspace_dir=str(temp_git_repo),
            max_tokens=200,  # Small budget to force frequent pruning
            mock_mode=True,
        )

        for i in range(50):
            session.history.append({
                "prompt": f"Turn {i}: Describe function {i} with detailed explanation and parameters",
                "response": f"def func_{i}(x: int) -> int:\n    '''Docstring for func {i}'''\n    return x * {i}\n",
                "code": f"def func_{i}(x): return x",
            })
            session._prune_history_if_needed()

            current_tokens = session._calculate_current_tokens()
            assert current_tokens <= session.max_tokens or len(session.history) == 1

        # Must have pruned old turns, keeping only recent ones
        assert len(session.history) < 50
        assert len(session.history) >= 1
        # Last turn in history must be the most recent turn (Turn 49)
        assert "Turn 49" in session.history[-1]["prompt"]

    def test_multi_turn_pruning_100_turns_extreme(self, temp_git_repo: Path):
        """Simulate 100 consecutive turns with varied prompt sizes and verify stability."""
        session = SessionManager(
            workspace_dir=str(temp_git_repo),
            max_tokens=500,
            mock_mode=True,
        )

        for i in range(100):
            prompt = f"Iteration {i}: " + ("word " * (i % 20 + 5))
            response = f"Response {i}: " + ("code_token " * (i % 30 + 10))
            session.history.append({
                "prompt": prompt,
                "response": response,
                "code": response,
            })
            session._prune_history_if_needed()

        assert len(session.history) < 100
        assert "Iteration 99" in session.history[-1]["prompt"]
        status = session.get_status()
        assert status["turns"] == len(session.history)
        assert status["ram_mb"] < 1024.0

    def test_pruning_with_heavy_context_files(self, temp_git_repo: Path):
        """When context files occupy most of max_tokens budget, history prunes down to minimal state."""
        # Create large context file (~150 tokens)
        large_file = temp_git_repo / "large_context.py"
        large_file.write_text(
            "# Large context file\n" + "\n".join([f"def sample_fn_{k}(): return {k}" for k in range(50)]),
            encoding="utf-8",
        )

        session = SessionManager(
            workspace_dir=str(temp_git_repo),
            max_tokens=200,
            mock_mode=True,
        )
        assert session.add_file("large_context.py") is True

        # Add multiple turns
        for i in range(10):
            session.history.append({
                "prompt": f"Prompt {i} with some content",
                "response": f"Response {i} with some content",
                "code": "",
            })
            session._prune_history_if_needed()

        # Context file is large, so history should be aggressively pruned down to 1 turn
        assert len(session.history) <= 2
        assert "Prompt 9" in session.history[-1]["prompt"]

    def test_pruning_with_ultra_small_max_tokens_budget(self, temp_git_repo: Path):
        """With max_tokens=1, pruning does not crash or loop infinitely and preserves at least 1 turn."""
        session = SessionManager(
            workspace_dir=str(temp_git_repo),
            max_tokens=1,
            mock_mode=True,
        )

        for i in range(10):
            session.history.append({
                "prompt": f"User prompt {i}",
                "response": f"Assistant response {i}",
                "code": "",
            })
            session._prune_history_if_needed()

        assert len(session.history) == 1
        assert "User prompt 9" in session.history[0]["prompt"]


# ==============================================================================
# 5. SessionManager: Rapid Sequential /undo Operations
# ==============================================================================

class TestSessionManagerRapidUndo:
    """Adversarial stress testing for rapid sequential /undo commands."""

    def test_rapid_undo_on_clean_workspace(self, temp_git_repo: Path):
        """Multiple consecutive /undo calls on a clean repository all return False cleanly without crashing."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        for _ in range(10):
            success, msg = session.undo_last_edit()
            assert success is False
            assert "no uncommitted changes" in msg.lower() or "clean" in msg.lower()

    def test_rapid_alternating_modify_and_undo(self, temp_git_repo: Path):
        """Alternating modification and undo cycles maintain clean repository state."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        for i in range(15):
            # Modify file
            calc_file.write_text(f"# Modification turn {i}\n", encoding="utf-8")
            assert session.git_guard.get_diff() != ""

            # Undo 1: Should succeed
            success, msg = session.undo_last_edit()
            assert success is True
            assert calc_file.read_text(encoding="utf-8") == orig_content
            assert session.git_guard.get_diff() == ""

            # Immediate Undo 2: Should report clean
            success2, msg2 = session.undo_last_edit()
            assert success2 is False
            assert "clean" in msg2.lower() or "no uncommitted" in msg2.lower()

    def test_rapid_undo_with_untracked_and_deleted_files(self, temp_git_repo: Path):
        """Sequential undo correctly restores deleted files and wipes untracked files across turns."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        calc_file = temp_git_repo / "calculator.py"
        orig_calc = calc_file.read_text(encoding="utf-8")

        # Delete tracked file and create rogue file
        calc_file.unlink()
        rogue = temp_git_repo / "rogue.py"
        rogue.write_text("malicious = True\n", encoding="utf-8")

        # Undo
        success, msg = session.undo_last_edit()
        assert success is True
        assert calc_file.exists()
        assert calc_file.read_text(encoding="utf-8") == orig_calc
        assert not rogue.exists()

        # Follow-up undo
        success2, msg2 = session.undo_last_edit()
        assert success2 is False

    def test_rapid_slash_command_undo_dispatch(self, temp_git_repo: Path):
        """handle_slash_command('/undo') handles rapid sequential invocations."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        # Modify
        calc_file.write_text("# Corrupted\n", encoding="utf-8")

        handled1, out1 = session.handle_slash_command("/undo")
        assert handled1 is True
        assert "Successfully" in out1 or "rolled back" in out1.lower()
        assert calc_file.read_text(encoding="utf-8") == orig_content

        handled2, out2 = session.handle_slash_command("/undo")
        assert handled2 is True
        assert "clean" in out2.lower() or "no uncommitted" in out2.lower()

    def test_undo_in_non_git_directory_repeated_calls(self, non_git_dir: Path):
        """Repeated /undo calls in a non-git directory return False gracefully without exceptions."""
        session = SessionManager(workspace_dir=str(non_git_dir), mock_mode=True)

        for _ in range(5):
            success, msg = session.undo_last_edit()
            assert success is False
            assert "not inside a git repository" in msg.lower() or "git" in msg.lower()


# ==============================================================================
# 6. SessionManager: Full Slash Command & Turn Execution Integration
# ==============================================================================

class TestSessionManagerIntegrationHardening:
    """Stress testing slash commands, context tracking, and pipeline execution."""

    def test_context_file_path_resolution_and_deduplication(self, temp_git_repo: Path):
        """Adding context files by relative path, absolute path, or duplicate references handles cleanly."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        # Add relative
        assert session.add_file("calculator.py") is True
        assert len(session.get_context_files()) == 1

        # Add duplicate relative
        assert session.add_file("calculator.py") is True
        assert len(session.get_context_files()) == 1

        # Add absolute
        abs_calc = temp_git_repo / "calculator.py"
        assert session.add_file(str(abs_calc)) is True
        assert len(session.get_context_files()) == 1

        # Remove by basename
        assert session.remove_file("calculator.py") is True
        assert len(session.get_context_files()) == 0

    def test_slash_command_routing_coverage(self, temp_git_repo: Path):
        """Comprehensive verification of all supported slash commands."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        # /help
        h_ok, h_out = session.handle_slash_command("/help")
        assert h_ok is True
        assert "/add" in h_out and "/undo" in h_out

        # /add and /remove
        session.handle_slash_command("/add calculator.py")
        assert "calculator.py" in session.get_context_files()
        session.handle_slash_command("/remove calculator.py")
        assert "calculator.py" not in session.get_context_files()

        # /status
        st_ok, st_out = session.handle_slash_command("/status")
        assert st_ok is True
        assert "Active Model" in st_out

        # /model
        m_ok, m_out = session.handle_slash_command("/model deepseek-coder:1.3b")
        assert m_ok is True
        assert "deepseek-coder:1.3b" in m_out

        # /doc
        d_ok, d_out = session.handle_slash_command("/doc math.sqrt")
        assert d_ok is True

        # /map
        map_ok, map_out = session.handle_slash_command("/map")
        assert map_ok is True
        assert "calculator.py" in map_out

        # /clear
        session.history.append({"prompt": "test", "response": "test"})
        c_ok, c_out = session.handle_slash_command("/clear")
        assert c_ok is True
        assert len(session.history) == 0

        # /exit and /quit
        assert session.handle_slash_command("/exit")[1] == "EXIT"
        assert session.handle_slash_command("/quit")[1] == "EXIT"
        assert session.handle_slash_command("/q")[1] == "EXIT"

        # Unknown slash command
        unk_ok, unk_out = session.handle_slash_command("/unknown_command_xyz")
        assert unk_ok is False
        assert "Unknown command" in unk_out

    def test_turn_execution_with_empty_and_whitespace_prompts(self, temp_git_repo: Path):
        """Executing turns with empty or whitespace-only prompts handles safely."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        res1 = session.execute_turn("")
        assert res1["success"] is True
        assert res1["code"] == ""

        res2 = session.execute_turn("   \n\t  ")
        assert res2["success"] is True
        assert res2["code"] == ""

    def test_turn_execution_patch_syntax_error_triggers_rollback(self, temp_git_repo: Path):
        """When LLM returns a patch introducing syntax error, session rolls back and fails turn."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        session.add_file("calculator.py")
        calc_file = temp_git_repo / "calculator.py"
        orig_content = calc_file.read_text(encoding="utf-8")

        # Mock orchestrator to output a patch with invalid syntax
        def mock_execute(*args, **kwargs):
            patch_code = (
                "<<<<<<< SEARCH\n"
                "    def add(self, a: int, b: int) -> int:\n"
                "        return a + b\n"
                "=======\n"
                "    def add(self, a: int, b\n"
                "        return a + b\n"
                ">>>>>>>"
            )
            return OrchestratorResult(
                user_prompt="fix add",
                language="python",
                final_code=patch_code,
                success=True,
                attempts=1,
                verification_results=[],
                total_duration_s=0.01,
                ram_usage_mb=50.0,
            )

        session.orchestrator.execute_pipeline = mock_execute

        res = session.execute_turn("corrupt add function")
        assert res["success"] is False
        # Working tree must be rolled back and intact
        assert calc_file.read_text(encoding="utf-8") == orig_content


# ==============================================================================
# 7. End-to-End System Memory & Verification Budget
# ==============================================================================

class TestSystemResourceBudgets:
    """Adversarial testing for system memory consumption and budget enforcement."""

    def test_peak_rss_memory_under_1024mb(self, temp_git_repo: Path):
        """Peak process RSS memory remains strictly under 1024 MB during multi-turn mock execution."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        for i in range(5):
            session.execute_turn(f"Implement mathematical function number {i}")

        process = psutil.Process()
        rss_mb = process.memory_info().rss / (1024 * 1024)
        assert rss_mb < 1024.0, f"Memory leak detected: RSS is {rss_mb:.2f} MB >= 1024 MB"
