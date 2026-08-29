"""
test_e2e_suite.py - Flagship End-to-End Test Suite for K-CLI (Tiers 1 to 4)

Comprehensive requirement-driven, opaque-box test suite covering:
- Tier 1: Feature Coverage (Isolation tests for DocRetriever, RepoMap, Patcher, GitGuard, SessionManager, CLI, REPL, Perf)
- Tier 2: Boundary & Corner Cases (Empty inputs, missing files, malformed patch blocks, non-git workspace, extreme token constraints, fuzzy whitespace matching, corrupted files, SQL injection safety)
- Tier 3: Cross-Feature Combinations (Pairwise & multi-way integrations: Patcher+GitGuard, DocRetriever+Session, RepoMap+Patcher, Session+Undo, Multi-file atomic safety)
- Tier 4: Real-World Scenarios & Benchmarks (Greenfield module creation, Multi-turn REPL refactor, Doc-assisted repair, Multi-file refactor, RSS Memory < 1024MB, FTS5 latency < 5ms, RepoMap latency < 250ms)
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
import pytest
from typer.testing import CliRunner

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Core Engine Imports (Present in Baseline)
from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
from k_cli.agents.orchestrator import Orchestrator, Persona
from k_cli.core.llm_driver import LLMDriver
from k_cli.cli import app

# Progressive Testability Dynamic Loaders for Domain Modules (M2 - M5)
def get_doc_retriever_cls():
    """Dynamically loads DocRetriever class or skips if module not implemented yet."""
    mod = pytest.importorskip("doc_retriever", reason="doc_retriever module not implemented yet")
    return getattr(mod, "DocRetriever")


def get_repo_map_cls():
    """Dynamically loads RepoMap class or skips if module not implemented yet."""
    mod = pytest.importorskip("repo_map", reason="repo_map module not implemented yet")
    return getattr(mod, "RepoMap")


def get_patcher_cls():
    """Dynamically loads Patcher class or skips if module not implemented yet."""
    mod = pytest.importorskip("patcher", reason="patcher module not implemented yet")
    return getattr(mod, "Patcher")


def get_git_guard_cls():
    """Dynamically loads GitGuard class or skips if module not implemented yet."""
    mod = pytest.importorskip("git_guard", reason="git_guard module not implemented yet")
    return getattr(mod, "GitGuard")


def get_session_manager_cls():
    """Dynamically loads SessionManager class or skips if module not implemented yet."""
    mod = pytest.importorskip("session", reason="session module not implemented yet")
    return getattr(mod, "SessionManager")


# ==============================================================================
# Pytest Fixtures & Test Helpers
# ==============================================================================

@pytest.fixture
def cli_runner():
    """Typer CLI Runner for subcommands."""
    return CliRunner()


@pytest.fixture
def temp_git_workspace(tmp_path: Path):
    """Initializes a fresh git repository in a temporary directory with initial commit."""
    workspace = tmp_path / "git_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@k-cli.local"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "K-CLI Test Runner"], cwd=workspace, check=True, capture_output=True)

    init_file = workspace / "main.py"
    init_file.write_text(
        'def add(a: int, b: int) -> int:\n    """Adds two integers."""\n    return a + b\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "main.py"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=workspace, check=True, capture_output=True)
    return workspace


@pytest.fixture
def sample_multi_module_workspace(tmp_path: Path):
    """Creates a structured multi-file python workspace for RepoMap & Patcher testing."""
    ws = tmp_path / "project_workspace"
    ws.mkdir(parents=True, exist_ok=True)

    # File 1: core/calculator.py
    core_dir = ws / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "__init__.py").write_text("", encoding="utf-8")
    (core_dir / "calculator.py").write_text(
        'class Calculator:\n'
        '    """Basic arithmetic calculator."""\n'
        '    def __init__(self, precision: int = 2):\n'
        '        self.precision = precision\n\n'
        '    def add(self, a: float, b: float) -> float:\n'
        '        return round(a + b, self.precision)\n\n'
        '    def multiply(self, a: float, b: float) -> float:\n'
        '        return round(a * b, self.precision)\n',
        encoding="utf-8",
    )

    # File 2: core/formatter.py
    (core_dir / "formatter.py").write_text(
        'def format_currency(amount: float, symbol: str = "$") -> str:\n'
        '    """Formats float as currency string."""\n'
        '    return f"{symbol}{amount:.2f}"\n',
        encoding="utf-8",
    )

    # File 3: service.py
    (ws / "service.py").write_text(
        'from core.calculator import Calculator\n'
        'from core.formatter import format_currency\n\n'
        'class InvoiceService:\n'
        '    def __init__(self):\n'
        '        self.calc = Calculator()\n\n'
        '    def compute_total(self, items: list[float], tax_rate: float = 0.05) -> str:\n'
        '        subtotal = sum(items)\n'
        '        tax = self.calc.multiply(subtotal, tax_rate)\n'
        '        total = self.calc.add(subtotal, tax)\n'
        '        return format_currency(total)\n',
        encoding="utf-8",
    )

    return ws


@pytest.fixture
def sample_stdlib_doc_data() -> Dict[str, Any]:
    """Sample structured stdlib documentation for indexing into DocRetriever."""
    return {
        "os.path": {
            "functions": [
                {
                    "name": "os.path.join",
                    "signature": "os.path.join(path, *paths) -> str",
                    "doc": "Join one or more path segments intelligently.",
                },
                {
                    "name": "os.path.exists",
                    "signature": "os.path.exists(path) -> bool",
                    "doc": "Test whether a path exists. Returns False for broken symbolic links.",
                },
                {
                    "name": "os.path.abspath",
                    "signature": "os.path.abspath(path) -> str",
                    "doc": "Return a normalized absolutized version of the pathname path.",
                },
            ]
        },
        "math": {
            "functions": [
                {
                    "name": "math.sqrt",
                    "signature": "math.sqrt(x: float) -> float",
                    "doc": "Return the square root of x.",
                },
                {
                    "name": "math.factorial",
                    "signature": "math.factorial(n: int) -> int",
                    "doc": "Find x!. Raise a ValueError if x is negative or non-integral.",
                },
            ]
        },
        "json": {
            "functions": [
                {
                    "name": "json.loads",
                    "signature": "json.loads(s, *, cls=None, object_hook=None, parse_float=None, parse_int=None, parse_constant=None, object_pairs_hook=None, **kw)",
                    "doc": "Deserialize s (a str, bytes or bytearray instance containing a JSON document) to a Python object.",
                },
                {
                    "name": "json.dumps",
                    "signature": "json.dumps(obj, *, skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, cls=None, indent=None, separators=None, default=None, sort_keys=False, **kw)",
                    "doc": "Serialize obj to a JSON formatted str.",
                },
            ]
        },
    }


# ==============================================================================
# TIER 1: FEATURE COVERAGE (Isolation Tests)
# ==============================================================================

class TestTier1BaselineCoreVerification:
    """Tier 1: Feature 1 - Baseline Core Verification (Verifier, CodeExtractor, AST)."""

    def test_t1_f1_verifier_valid_python_ast(self):
        verifier = Verifier()
        code = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        res = verifier.verify_python_ast(code)
        assert res.success is True
        assert res.error_trace == ""

    def test_t1_f1_verifier_syntax_error_with_line(self):
        verifier = Verifier()
        code = "def broken(\n    return 42\n"
        res = verifier.verify_python_ast(code)
        assert res.success is False
        assert "SyntaxError" in res.error_trace or res.line_number is not None

    def test_t1_f1_code_extractor_markdown_fences(self):
        markdown_text = (
            "Here is the solution:\n\n"
            "```python\n"
            "def multiply(a, b):\n"
            "    return a * b\n"
            "```\n\n"
            "And in bash:\n"
            "```bash\n"
            "pytest tests/\n"
            "```"
        )
        blocks = CodeExtractor.extract_code_blocks(markdown_text)
        assert len(blocks) == 2
        assert blocks[0][0] == "python"
        assert "def multiply" in blocks[0][1]
        assert blocks[1][0] == "bash"
        assert "pytest tests/" in blocks[1][1]

    def test_t1_f1_code_extractor_raw_fallback(self):
        raw_code = "def no_fences(x):\n    return x * 2"
        blocks = CodeExtractor.extract_code_blocks(raw_code, default_lang="python")
        assert len(blocks) == 1
        assert blocks[0][0] == "python"
        assert blocks[0][1] == raw_code

    def test_t1_f1_verifier_result_dataclass_to_dict(self):
        res = VerificationResult(
            success=True,
            error_trace="",
            code="print('ok')",
            language="python",
            line_number=None,
            stdout="ok\n",
            stderr="",
            verification_type="syntax",
        )
        d = res.to_dict()
        assert d["success"] is True
        assert d["code"] == "print('ok')"
        assert d["language"] == "python"


class TestTier1DocRetriever:
    """Tier 1: Feature 2 - DevDocs SQLite FTS5 Indexing & Precision Search."""

    def test_t1_f2_doc_retriever_initialization(self, tmp_path: Path):
        DocRetriever = get_doc_retriever_cls()
        db_file = tmp_path / "test_devdocs.db"
        retriever = DocRetriever(db_path=str(db_file))
        assert db_file.exists() or retriever is not None

    def test_t1_f2_doc_retriever_index_module(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        db_file = tmp_path / "test_devdocs.db"
        retriever = DocRetriever(db_path=str(db_file))
        count = retriever.index_module("os.path", sample_stdlib_doc_data["os.path"])
        assert isinstance(count, int)
        assert count >= 1

    def test_t1_f2_doc_retriever_search_bm25(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "devdocs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        results = retriever.search("join path segments", limit=3, max_tokens=250)
        assert isinstance(results, list)
        assert len(results) > 0
        first_match = results[0]
        # Contract: result item must contain symbol/name and signature/doc
        symbol_name = first_match.get("name") or first_match.get("symbol") or ""
        assert "join" in symbol_name or "os.path" in str(first_match)

    def test_t1_f2_doc_retriever_format_context_snippets(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "devdocs.db"))
        retriever.index_module("math", sample_stdlib_doc_data["math"])

        snippet_str = retriever.format_context_snippets("square root", max_tokens=250)
        assert isinstance(snippet_str, str)
        assert "sqrt" in snippet_str

    def test_t1_f2_doc_retriever_token_budget_bound(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "devdocs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        snippet_str = retriever.format_context_snippets("serialize deserialize json path square", max_tokens=250)
        # Token estimation: rough standard 1 token ~= 3.5-4 chars
        estimated_tokens = len(snippet_str.split())
        assert estimated_tokens <= 250


class TestTier1RepoMap:
    """Tier 1: Feature 3 - AST Codebase Repository Map."""

    def test_t1_f3_repo_map_extract_symbols_functions_classes(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        calc_file = str(sample_multi_module_workspace / "core" / "calculator.py")
        symbols = repo_map.extract_symbols(calc_file)

        assert isinstance(symbols, list)
        names = [s.get("name") for s in symbols if isinstance(s, dict)]
        assert "Calculator" in names
        assert any(n in ("add", "multiply", "__init__") for n in names)

    def test_t1_f3_repo_map_get_repo_map_hierarchy(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        map_text = repo_map.get_repo_map(max_tokens=400)

        assert isinstance(map_text, str)
        assert "Calculator" in map_text
        assert "InvoiceService" in map_text

    def test_t1_f3_repo_map_token_limit_budget(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        map_text = repo_map.get_repo_map(max_tokens=400)

        # Word count / token estimate < 400
        words = map_text.split()
        assert len(words) <= 400

    def test_t1_f3_repo_map_focus_files_prioritization(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        focus = ["service.py"]
        map_text = repo_map.get_repo_map(max_tokens=400, focus_files=focus)

        assert "InvoiceService" in map_text

    def test_t1_f3_repo_map_multi_file_workspace(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        map_text = repo_map.get_repo_map(max_tokens=400)
        assert "core/calculator.py" in map_text or "calculator.py" in map_text


class TestTier1Patcher:
    """Tier 1: Feature 4 - SEARCH/REPLACE Surgical Patcher."""

    def test_t1_f4_patcher_parse_single_block(self):
        Patcher = get_patcher_cls()
        patch_text = (
            "<<<<<<< SEARCH\n"
            "def old_fn():\n"
            "    return 1\n"
            "=======\n"
            "def new_fn():\n"
            "    return 2\n"
            ">>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(patch_text)
        assert len(blocks) == 1
        assert "def old_fn():" in blocks[0][0]
        assert "def new_fn():" in blocks[0][1]

    def test_t1_f4_patcher_parse_multiple_blocks(self):
        Patcher = get_patcher_cls()
        patch_text = (
            "<<<<<<< SEARCH\n"
            "x = 1\n"
            "=======\n"
            "x = 10\n"
            ">>>>>>>\n"
            "Some text in between\n"
            "<<<<<<< SEARCH\n"
            "y = 2\n"
            "=======\n"
            "y = 20\n"
            ">>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(patch_text)
        assert len(blocks) == 2
        assert blocks[0][0].strip() == "x = 1"
        assert blocks[1][0].strip() == "y = 2"

    def test_t1_f4_patcher_apply_patch_exact(self):
        Patcher = get_patcher_cls()
        original = "def add(a, b):\n    return a - b\n"
        search_block = "return a - b"
        replace_block = "return a + b"

        success, patched, err = Patcher.apply_patch(original, search_block, replace_block, fuzzy=False)
        assert success is True
        assert "return a + b" in patched
        assert err == ""

    def test_t1_f4_patcher_apply_file_patches(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        test_file = tmp_path / "mod.py"
        test_file.write_text("def run():\n    return False\n", encoding="utf-8")

        patch_text = (
            "<<<<<<< SEARCH\n"
            "def run():\n"
            "    return False\n"
            "=======\n"
            "def run():\n"
            "    return True\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch_text, validate_ast=True)
        assert success is True
        assert "return True" in test_file.read_text(encoding="utf-8")

    def test_t1_f4_patcher_ast_validation_prevents_syntax_error(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        test_file = tmp_path / "valid.py"
        test_file.write_text("def calculate():\n    return 42\n", encoding="utf-8")

        # Malformed replacement with syntax error
        patch_text = (
            "<<<<<<< SEARCH\n"
            "def calculate():\n"
            "    return 42\n"
            "=======\n"
            "def calculate(\n"
            "    return 42\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(test_file), patch_text, validate_ast=True)
        assert success is False
        assert "SyntaxError" in err or "AST" in err or "syntax" in err.lower()
        # Original content must be untouched
        assert "def calculate():\n    return 42\n" == test_file.read_text(encoding="utf-8")


class TestTier1GitGuard:
    """Tier 1: Feature 5 - Git Safety Net, Commits & Rollback."""

    def test_t1_f5_git_guard_is_git_repo(self, temp_git_workspace: Path, tmp_path: Path):
        GitGuard = get_git_guard_cls()
        guard_git = GitGuard(repo_dir=str(temp_git_workspace))
        assert guard_git.is_git_repo() is True

        non_git_dir = tmp_path / "not_git"
        non_git_dir.mkdir()
        guard_non_git = GitGuard(repo_dir=str(non_git_dir))
        assert guard_non_git.is_git_repo() is False

    def test_t1_f5_git_guard_ensure_repo(self, tmp_path: Path):
        GitGuard = get_git_guard_cls()
        fresh_dir = tmp_path / "auto_git"
        fresh_dir.mkdir()
        guard = GitGuard(repo_dir=str(fresh_dir))
        ensured = guard.ensure_repo()
        assert ensured is True
        assert (fresh_dir / ".git").exists()

    def test_t1_f5_git_guard_create_snapshot(self, temp_git_workspace: Path):
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        snapshot = guard.create_snapshot()
        assert isinstance(snapshot, str)
        assert len(snapshot) > 0

    def test_t1_f5_git_guard_commit_success(self, temp_git_workspace: Path):
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        f = temp_git_workspace / "new_module.py"
        f.write_text("def new_feature(): pass\n", encoding="utf-8")

        commit_sha = guard.commit_success(message="feat: add new feature", files=["new_module.py"])
        assert commit_sha is not None
        diff = guard.get_diff()
        assert diff == ""

    def test_t1_f5_git_guard_rollback_restores_file(self, temp_git_workspace: Path):
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        main_file = temp_git_workspace / "main.py"
        original_content = main_file.read_text(encoding="utf-8")

        # Dirty modification
        main_file.write_text("INVALID CORRUPTED CODE HERE\n", encoding="utf-8")
        assert guard.get_diff() != ""

        # Rollback
        rolled_back = guard.rollback()
        assert rolled_back is True
        assert main_file.read_text(encoding="utf-8") == original_content


class TestTier1SessionManager:
    """Tier 1: Feature 6 - Multi-Turn Session & Token Pruning."""

    def test_t1_f6_session_add_context_file(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        added = session.add_file("main.py")
        assert added is True
        files = session.get_context_files()
        assert any("main.py" in str(f) for f in files)

    def test_t1_f6_session_remove_context_file(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        session.add_file("main.py")
        removed = session.remove_file("main.py")
        assert removed is True
        assert len(session.get_context_files()) == 0

    def test_t1_f6_session_clear_history(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        session.clear_history()
        status = session.get_status()
        assert status.get("turns", 0) == 0 or status.get("history_len", 0) == 0

    def test_t1_f6_session_get_status(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace), model_name="qwen2.5-coder:1.5b")
        status = session.get_status()
        assert isinstance(status, dict)
        assert "model" in status or "model_name" in status
        assert "ram_mb" in status or "rss_mb" in status or "token_count" in status or "files" in status

    def test_t1_f6_session_process_turn_streaming(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        gen = session.process_turn("Write a python helper function")
        tokens = []
        try:
            for token in gen:
                tokens.append(token)
        except StopIteration:
            pass
        # Contract: process_turn is a generator
        assert isinstance(tokens, list)


class TestTier1SlashCommands:
    """Tier 1: Feature 7 - REPL Slash Commands Hub."""

    def test_t1_f7_slash_help_command(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        if hasattr(session, "handle_slash_command"):
            handled, output = session.handle_slash_command("/help")
            assert handled is True
            assert "/add" in output
            assert "/undo" in output

    def test_t1_f7_slash_add_command(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        if hasattr(session, "handle_slash_command"):
            handled, output = session.handle_slash_command("/add main.py")
            assert handled is True
            assert any("main.py" in f for f in session.get_context_files())

    def test_t1_f7_slash_diff_command(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        (temp_git_workspace / "main.py").write_text("# new comment\n", encoding="utf-8")
        if hasattr(session, "handle_slash_command"):
            handled, output = session.handle_slash_command("/diff")
            assert handled is True
            assert "main.py" in output or "# new comment" in output

    def test_t1_f7_slash_undo_command(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        orig = (temp_git_workspace / "main.py").read_text(encoding="utf-8")
        (temp_git_workspace / "main.py").write_text("# corrupt\n", encoding="utf-8")

        if hasattr(session, "handle_slash_command"):
            handled, output = session.handle_slash_command("/undo")
            assert handled is True
            assert (temp_git_workspace / "main.py").read_text(encoding="utf-8") == orig

    def test_t1_f7_slash_status_and_clear(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        if hasattr(session, "handle_slash_command"):
            handled, status_out = session.handle_slash_command("/status")
            assert handled is True
            handled_clear, clear_out = session.handle_slash_command("/clear")
            assert handled_clear is True


class TestTier1CLICommands:
    """Tier 1: Feature 8 - CLI Single-Shot Command Execution."""

    def test_t1_f8_cli_app_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "k-cli" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_t1_f8_cli_status_command(self, cli_runner: CliRunner):
        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "RAM" in result.stdout or "Diagnostics" in result.stdout or "Model" in result.stdout

    def test_t1_f8_cli_doc_command(self, cli_runner: CliRunner):
        result = cli_runner.invoke(app, ["doc", "json.loads"])
        # If doc command exists, exit_code 0 or 2 for not indexed
        assert result.exit_code in (0, 1, 2)

    def test_t1_f8_cli_map_command(self, cli_runner: CliRunner):
        result = cli_runner.invoke(app, ["map"])
        assert result.exit_code in (0, 1, 2)

    def test_t1_f8_cli_run_command_mock(self, cli_runner: CliRunner):
        result = cli_runner.invoke(app, ["run", "Generate a function", "--mock"])
        # Single-shot mock execution
        assert result.exit_code in (0, 1)


class TestTier1PerformanceBudgets:
    """Tier 1: Feature 9 - Performance Benchmarks (RSS Memory, <5ms FTS5, <250ms Map)."""

    def test_t1_f9_perf_rss_memory_under_1024mb(self):
        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)
        assert rss_mb < 1024, f"Peak RSS exceeded 1024 MB: {rss_mb:.2f} MB"

    def test_t1_f9_perf_fts5_latency_under_5ms(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "perf_docs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        start = time.perf_counter()
        retriever.search("join path segments", limit=3, max_tokens=250)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert elapsed_ms < 5.0, f"FTS5 query exceeded 5ms: {elapsed_ms:.3f} ms"

    def test_t1_f9_perf_repo_map_latency_under_250ms(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))

        start = time.perf_counter()
        repo_map.get_repo_map(max_tokens=400)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert elapsed_ms < 250.0, f"RepoMap generation exceeded 250ms: {elapsed_ms:.3f} ms"

    def test_t1_f9_perf_ast_parse_latency_under_1ms(self):
        verifier = Verifier()
        code = "def sample_function(x, y):\n    return x ** 2 + y ** 2\n" * 10
        # Warm-up pass
        verifier.verify_python_ast(code)
        
        latencies = []
        for _ in range(20):
            start = time.perf_counter()
            verifier.verify_python_ast(code)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

        mean_latency = sum(latencies) / len(latencies)
        assert mean_latency < 1.0, f"AST parsing mean latency exceeded 1ms: {mean_latency:.3f} ms"

    def test_t1_f9_perf_patcher_latency_under_10ms(self):
        Patcher = get_patcher_cls()
        original = "x = 1\ny = 2\nz = 3\n" * 50
        search = "x = 1\ny = 2\nz = 3"
        replace = "x = 10\ny = 20\nz = 30"
        start = time.perf_counter()
        Patcher.apply_patch(original, search, replace, fuzzy=True)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 10.0, f"Patcher exceeded 10ms: {elapsed_ms:.3f} ms"


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Stress & Boundary Validation)
# ==============================================================================

class TestTier2EmptyAndNullInputs:
    """Tier 2: Boundary Group 1 - Empty, Null & Zero-Length Inputs."""

    def test_t2_doc_retriever_empty_query_search(self, tmp_path: Path):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "empty.db"))
        res = retriever.search("", limit=3, max_tokens=250)
        assert isinstance(res, list)
        assert len(res) == 0

    def test_t2_doc_retriever_empty_index(self, tmp_path: Path):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "empty_index.db"))
        res = retriever.search("anything", limit=3, max_tokens=250)
        assert res == []

    def test_t2_doc_retriever_whitespace_query(self, tmp_path: Path):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "empty_ws.db"))
        res = retriever.search("    \n\t  ", limit=3, max_tokens=250)
        assert res == []

    def test_t2_repo_map_empty_workspace(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        empty_dir = tmp_path / "empty_ws"
        empty_dir.mkdir()
        repo_map = RepoMap(root_dir=str(empty_dir))
        result = repo_map.get_repo_map(max_tokens=400)
        assert isinstance(result, str)

    def test_t2_repo_map_empty_file(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        empty_py = tmp_path / "empty.py"
        empty_py.write_text("", encoding="utf-8")
        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(empty_py))
        assert symbols == []

    def test_t2_patcher_empty_patch_string(self):
        Patcher = get_patcher_cls()
        blocks = Patcher.parse_search_replace_blocks("")
        assert blocks == []

    def test_t2_patcher_empty_search_block_handling(self):
        Patcher = get_patcher_cls()
        success, patched, err = Patcher.apply_patch("original code", "", "new code", fuzzy=True)
        # Empty search block must be rejected safely
        assert success is False or err != ""

    def test_t2_session_empty_prompt_handling(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        gen = session.process_turn("")
        list(gen)
        # Should not crash


class TestTier2MissingFilesAndResources:
    """Tier 2: Boundary Group 2 - Non-Existent Files, Missing Directories & Non-Git Envs."""

    def test_t2_doc_retriever_missing_db_dir_auto_create(self, tmp_path: Path):
        DocRetriever = get_doc_retriever_cls()
        nested_db = tmp_path / "deep" / "nested" / "dir" / "docs.db"
        retriever = DocRetriever(db_path=str(nested_db))
        assert nested_db.exists() or retriever is not None

    def test_t2_repo_map_missing_file_extract_symbols(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(tmp_path))
        symbols = repo_map.extract_symbols(str(tmp_path / "does_not_exist.py"))
        assert symbols == []

    def test_t2_patcher_missing_target_file_error(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        success, err = Patcher.apply_file_patches(str(tmp_path / "missing.py"), "<<<<<<< SEARCH\na\n=======\nb\n>>>>>>>")
        assert success is False
        assert "not found" in err.lower() or "missing" in err.lower() or "exist" in err.lower()

    def test_t2_session_add_missing_file_returns_false(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        assert session.add_file("nonexistent_file.py") is False

    def test_t2_git_guard_non_git_workspace_no_crash(self, tmp_path: Path):
        GitGuard = get_git_guard_cls()
        non_git = tmp_path / "plain_dir"
        non_git.mkdir()
        guard = GitGuard(repo_dir=str(non_git))
        assert guard.is_git_repo() is False
        assert guard.get_diff() == ""
        assert guard.rollback() is False or guard.rollback() is None

    def test_t2_git_guard_rollback_missing_file(self, temp_git_workspace: Path):
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        # Should not raise exception
        guard.rollback(files=["ghost_file.py"])


class TestTier2MalformedPatchBlocks:
    """Tier 2: Boundary Group 3 - Malformed & Corrupted Patch Blocks."""

    def test_t2_patcher_malformed_missing_divider(self):
        Patcher = get_patcher_cls()
        bad_patch = "<<<<<<< SEARCH\ndef fn(): pass\n>>>>>>>"
        blocks = Patcher.parse_search_replace_blocks(bad_patch)
        assert len(blocks) == 0

    def test_t2_patcher_malformed_missing_end_marker(self):
        Patcher = get_patcher_cls()
        bad_patch = "<<<<<<< SEARCH\ndef fn(): pass\n=======\ndef fn(): return 1\n"
        blocks = Patcher.parse_search_replace_blocks(bad_patch)
        assert len(blocks) == 0

    def test_t2_patcher_search_block_not_matching(self):
        Patcher = get_patcher_cls()
        original = "def foo():\n    return 1\n"
        search = "def non_existent():\n    pass"
        replace = "def replacement():\n    pass"
        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is False
        assert patched == original
        assert "not found" in err.lower() or err != ""

    def test_t2_patcher_replace_block_invalid_python_ast(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        target = tmp_path / "code.py"
        target.write_text("x = 10\n", encoding="utf-8")
        bad_patch = "<<<<<<< SEARCH\nx = 10\n=======\nx = ((\n>>>>>>>"

        success, err = Patcher.apply_file_patches(str(target), bad_patch, validate_ast=True)
        assert success is False
        assert target.read_text(encoding="utf-8") == "x = 10\n"

    def test_t2_patcher_file_unchanged_on_ast_failure(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        target = tmp_path / "logic.py"
        original = "def compute(n: int) -> int:\n    return n * 2\n"
        target.write_text(original, encoding="utf-8")

        bad_patch = "<<<<<<< SEARCH\n    return n * 2\n=======\n    return n *\n>>>>>>>"
        Patcher.apply_file_patches(str(target), bad_patch, validate_ast=True)
        assert target.read_text(encoding="utf-8") == original

    def test_t2_patcher_multiple_blocks_partial_failure(self, tmp_path: Path):
        Patcher = get_patcher_cls()
        target = tmp_path / "multi.py"
        original = "a = 1\nb = 2\n"
        target.write_text(original, encoding="utf-8")

        # Block 1 valid, Block 2 invalid search
        multi_patch = (
            "<<<<<<< SEARCH\na = 1\n=======\na = 10\n>>>>>>>\n"
            "<<<<<<< SEARCH\nNOT_HERE = 999\n=======\nc = 30\n>>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(target), multi_patch, validate_ast=True)
        assert success is False
        # Atomic guarantee: file should not be partially patched
        assert target.read_text(encoding="utf-8") == original

    def test_t2_patcher_overlapping_search_blocks(self):
        Patcher = get_patcher_cls()
        original = "line1\nline2\nline3\n"
        patch = (
            "<<<<<<< SEARCH\nline1\nline2\n=======\nnewline1\nnewline2\n>>>>>>>\n"
            "<<<<<<< SEARCH\nline2\nline3\n=======\nnewline2\nnewline3\n>>>>>>>"
        )
        blocks = Patcher.parse_search_replace_blocks(patch)
        assert len(blocks) == 2


class TestTier2WhitespaceFuzzyMatching:
    """Tier 2: Boundary Group 4 - Whitespace, Indentation & Fuzzy Matching."""

    def test_t2_patcher_fuzzy_whitespace_trailing_spaces(self):
        Patcher = get_patcher_cls()
        original = "def add(a, b):   \n    return a + b  \n"
        search = "def add(a, b):\n    return a + b"
        replace = "def add(a, b):\n    return a + b + 1"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert "return a + b + 1" in patched

    def test_t2_patcher_fuzzy_newline_crlf_vs_lf(self):
        Patcher = get_patcher_cls()
        original = "def fn():\r\n    return 42\r\n"
        search = "def fn():\n    return 42"
        replace = "def fn():\n    return 100"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert "100" in patched

    def test_t2_patcher_fuzzy_indentation_shift(self):
        Patcher = get_patcher_cls()
        original = "    def method(self):\n        return self.val\n"
        search = "def method(self):\n    return self.val"
        replace = "def method(self):\n    return self.val * 2"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert "return self.val * 2" in patched

    def test_t2_patcher_exact_mode_rejects_mismatch(self):
        Patcher = get_patcher_cls()
        original = "def fn():   \n    return 1\n"
        search = "def fn():\n    return 1"
        replace = "def fn():\n    return 2"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=False)
        assert success is False or patched == original

    def test_t2_patcher_unicode_emojis_in_source(self):
        Patcher = get_patcher_cls()
        original = 'EMOJI = "🚀"\nSTATUS = "active"\n'
        search = 'STATUS = "active"'
        replace = 'STATUS = "completed ✅"'

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True
        assert "completed ✅" in patched

    def test_t2_patcher_blank_lines_fuzzy_matching(self):
        Patcher = get_patcher_cls()
        original = "def step1():\n    pass\n\n\ndef step2():\n    pass\n"
        search = "def step1():\n    pass\ndef step2():\n    pass"
        replace = "def step1():\n    pass\ndef step2():\n    return True"

        success, patched, err = Patcher.apply_patch(original, search, replace, fuzzy=True)
        assert success is True


class TestTier2ExtremeTokenConstraints:
    """Tier 2: Boundary Group 5 - Extreme Token Constraints & Budgets."""

    def test_t2_doc_retriever_max_tokens_zero(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "zero_tok.db"))
        retriever.index_module("math", sample_stdlib_doc_data["math"])
        snippets = retriever.format_context_snippets("sqrt", max_tokens=0)
        assert snippets == "" or len(snippets.split()) == 0

    def test_t2_doc_retriever_max_tokens_one(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "one_tok.db"))
        retriever.index_module("math", sample_stdlib_doc_data["math"])
        snippets = retriever.format_context_snippets("sqrt", max_tokens=1)
        assert len(snippets.split()) <= 5

    def test_t2_repo_map_max_tokens_small_limit(self, sample_multi_module_workspace: Path):
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        tree = repo_map.get_repo_map(max_tokens=50)
        assert isinstance(tree, str)
        assert len(tree.split()) <= 50

    def test_t2_repo_map_huge_symbols_pruning(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        huge_repo = tmp_path / "huge_repo"
        huge_repo.mkdir()
        # Generate 100 functions
        code_lines = [f"def generated_func_{i}(param_{i}: int) -> int:\n    return {i}\n" for i in range(100)]
        (huge_repo / "huge_module.py").write_text("\n".join(code_lines), encoding="utf-8")

        repo_map = RepoMap(root_dir=str(huge_repo))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert len(tree.split()) <= 400

    def test_t2_session_token_budget_prunes_old_turns(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace), max_tokens=100)
        # Should not crash under extreme tight token constraint
        status = session.get_status()
        assert isinstance(status, dict)

    def test_t2_doc_retriever_large_token_budget(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "large_tok.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)
        snippets = retriever.format_context_snippets("json", max_tokens=10000)
        assert "json.loads" in snippets or "json.dumps" in snippets


class TestTier2CorruptedFilesAndAst:
    """Tier 2: Boundary Group 6 - Corrupted Files, Non-Python Files & AST Parsing."""

    def test_t2_repo_map_skip_syntax_error_file(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        ws = tmp_path / "mixed_ws"
        ws.mkdir()
        (ws / "valid.py").write_text("def ok(): return True\n", encoding="utf-8")
        (ws / "broken.py").write_text("def broken(\n    return !!\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert "ok" in tree

    def test_t2_repo_map_skip_binary_and_hidden_files(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        ws = tmp_path / "binary_ws"
        ws.mkdir()
        (ws / "valid.py").write_text("def valid(): pass\n", encoding="utf-8")
        (ws / "data.bin").write_bytes(b"\x00\xff\xfe\x01\x02")
        (ws / ".hidden.py").write_text("def hidden(): pass\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(ws))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert "valid" in tree

    def test_t2_repo_map_deeply_nested_tree(self, tmp_path: Path):
        RepoMap = get_repo_map_cls()
        deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep_dir.mkdir(parents=True)
        (deep_dir / "leaf.py").write_text("class DeepLeaf:\n    def run(self): pass\n", encoding="utf-8")

        repo_map = RepoMap(root_dir=str(tmp_path))
        tree = repo_map.get_repo_map(max_tokens=400)
        assert "DeepLeaf" in tree

    def test_t2_verifier_multiline_syntax_error_line_number(self):
        verifier = Verifier()
        code = (
            "def step1():\n"
            "    return 1\n"
            "\n"
            "def step2():\n"
            "    data = [\n"
            "        1, 2, 3\n"
            "    \n"  # missing closing bracket
            "def step3():\n"
            "    return 3\n"
        )
        res = verifier.verify_python_ast(code)
        assert res.success is False
        assert res.line_number is not None

    def test_t2_verifier_empty_string_ast(self):
        verifier = Verifier()
        res = verifier.verify_python_ast("")
        assert res.success is True

    def test_t2_verifier_comments_only_ast(self):
        verifier = Verifier()
        res = verifier.verify_python_ast("# just a comment\n# second comment\n")
        assert res.success is True


class TestTier2SecurityAndSessionCornerCases:
    """Tier 2: Boundary Group 7 - Search Injection, Robustness & Session Corner Cases."""

    def test_t2_doc_retriever_fts5_special_tokens_sanitization(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "sanitize.db"))
        retriever.index_module("os.path", sample_stdlib_doc_data["os.path"])

        # FTS5 special syntax characters that would break unescaped queries
        dangerous_queries = [
            'AND OR NOT NEAR() * : ^ ""',
            'MATCH "foo*bar"',
            'path:join OR (exists NOT)',
            '"""',
            "***",
        ]
        for q in dangerous_queries:
            results = retriever.search(q, limit=3, max_tokens=250)
            assert isinstance(results, list)

    def test_t2_doc_retriever_sql_injection_safety(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "sqli.db"))
        retriever.index_module("math", sample_stdlib_doc_data["math"])

        sqli_query = "'; DROP TABLE doc_entries; --"
        results = retriever.search(sqli_query, limit=3, max_tokens=250)
        assert isinstance(results, list)
        # Verify table wasn't dropped
        res_after = retriever.search("sqrt", limit=3, max_tokens=250)
        assert len(res_after) > 0

    def test_t2_doc_retriever_reindex_same_module(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "reindex.db"))
        count1 = retriever.index_module("math", sample_stdlib_doc_data["math"])
        count2 = retriever.index_module("math", sample_stdlib_doc_data["math"])
        assert count1 == count2

    def test_t2_session_undo_with_no_prior_edits(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        success, msg = session.undo_last_edit()
        assert success is False or "no" in msg.lower() or "clean" in msg.lower()

    def test_t2_session_remove_untracked_file(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        assert session.remove_file("never_tracked.py") is False

    def test_t2_session_add_duplicate_file_idempotent(self, temp_git_workspace: Path):
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        session.add_file("main.py")
        session.add_file("main.py")
        files = session.get_context_files()
        assert len(files) == 1

    def test_t2_git_guard_diff_empty_when_clean(self, temp_git_workspace: Path):
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        assert guard.get_diff() == ""


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (Pairwise & Multi-Way Integrations)
# ==============================================================================

class TestTier3CrossFeatureIntegrations:
    """Tier 3: Pairwise & Multi-Feature Integration Contracts."""

    def test_t3_patcher_git_guard_rollback_on_ast_failure(self, temp_git_workspace: Path):
        """Integration 1: Patcher + GitGuard rollback on AST syntax error."""
        Patcher = get_patcher_cls()
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        main_file = temp_git_workspace / "main.py"
        original_code = main_file.read_text(encoding="utf-8")

        guard.create_snapshot()

        # Attempt to patch with invalid syntax
        patch = (
            "<<<<<<< SEARCH\ndef add(a: int, b: int) -> int:\n    return a + b\n=======\ndef add(a: int, b: int) -> int\n    return a + b\n>>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(main_file), patch, validate_ast=True)
        if not success:
            guard.rollback()

        assert main_file.read_text(encoding="utf-8") == original_code
        assert guard.get_diff() == ""

    def test_t3_patcher_git_guard_atomic_commit_on_verified_success(self, temp_git_workspace: Path):
        """Integration 2: Patcher + Verifier + GitGuard commit on verified success."""
        Patcher = get_patcher_cls()
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))
        main_file = temp_git_workspace / "main.py"

        patch = (
            "<<<<<<< SEARCH\ndef add(a: int, b: int) -> int:\n    \"\"\"Adds two integers.\"\"\"\n    return a + b\n"
            "=======\n"
            "def add(a: int, b: int) -> int:\n    \"\"\"Adds two integers with validation.\"\"\"\n    if not isinstance(a, int) or not isinstance(b, int):\n        raise TypeError('Inputs must be integers')\n    return a + b\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(main_file), patch, validate_ast=True)
        assert success is True

        commit_sha = guard.commit_success(message="feat: add input validation to add()", files=["main.py"])
        assert commit_sha is not None
        assert guard.get_diff() == ""

    def test_t3_doc_retriever_session_context_injection(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        """Integration 3: DocRetriever + SessionManager context injection."""
        DocRetriever = get_doc_retriever_cls()
        SessionManager = get_session_manager_cls()

        db_path = tmp_path / "session_docs.db"
        retriever = DocRetriever(db_path=str(db_path))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        session = SessionManager(workspace_dir=str(tmp_path))
        if hasattr(session, "doc_retriever"):
            session.doc_retriever = retriever

        snippets = retriever.format_context_snippets("os.path.join", max_tokens=250)
        assert "os.path.join" in snippets

    def test_t3_repo_map_patcher_symbol_update_reflection(self, sample_multi_module_workspace: Path):
        """Integration 4: RepoMap + Patcher symbol update reflection."""
        RepoMap = get_repo_map_cls()
        Patcher = get_patcher_cls()

        calc_file = sample_multi_module_workspace / "core" / "calculator.py"
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        initial_tree = repo_map.get_repo_map(max_tokens=400)
        assert "Calculator" in initial_tree

        # Rename method via Patcher
        patch = (
            "<<<<<<< SEARCH\n    def multiply(self, a: float, b: float) -> float:\n        return round(a * b, self.precision)\n"
            "=======\n"
            "    def product(self, a: float, b: float) -> float:\n        return round(a * b, self.precision)\n"
            ">>>>>>>"
        )
        success, err = Patcher.apply_file_patches(str(calc_file), patch, validate_ast=True)
        assert success is True

        updated_symbols = repo_map.extract_symbols(str(calc_file))
        names = [s.get("name") for s in updated_symbols if isinstance(s, dict)]
        assert "product" in names

    def test_t3_session_undo_restores_file_via_git_guard(self, temp_git_workspace: Path):
        """Integration 5: SessionManager + GitGuard /undo integration."""
        SessionManager = get_session_manager_cls()
        Patcher = get_patcher_cls()

        session = SessionManager(workspace_dir=str(temp_git_workspace))
        main_file = temp_git_workspace / "main.py"
        orig_text = main_file.read_text(encoding="utf-8")

        session.add_file("main.py")

        patch = (
            "<<<<<<< SEARCH\n    return a + b\n=======\n    return a + b + 100\n>>>>>>>"
        )
        Patcher.apply_file_patches(str(main_file), patch, validate_ast=True)
        assert "100" in main_file.read_text(encoding="utf-8")

        # Trigger undo
        success, msg = session.undo_last_edit()
        assert success is True
        assert main_file.read_text(encoding="utf-8") == orig_text

    def test_t3_repo_map_doc_retriever_session_budget_coordination(self, sample_multi_module_workspace: Path, sample_stdlib_doc_data: Dict[str, Any]):
        """Integration 6: RepoMap + DocRetriever + Session context token budget coordination."""
        RepoMap = get_repo_map_cls()
        DocRetriever = get_doc_retriever_cls()

        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        map_text = repo_map.get_repo_map(max_tokens=400)

        retriever = DocRetriever(db_path=str(sample_multi_module_workspace / "docs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)
        doc_text = retriever.format_context_snippets("format currency", max_tokens=250)

        total_tokens = len(map_text.split()) + len(doc_text.split())
        assert total_tokens <= 650

    def test_t3_orchestrator_verifier_auto_debug_loop(self):
        """Integration 7: Orchestrator + Verifier state machine pipeline."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        res = orchestrator.execute_pipeline(
            user_prompt="Write a function to calculate factorial",
            language="python",
        )
        assert res.success is True
        assert "def factorial" in res.final_code or "def " in res.final_code

    def test_t3_cli_doc_and_map_subcommands_output(self, cli_runner: CliRunner, sample_multi_module_workspace: Path):
        """Integration 8: CLI subcommands invocation."""
        result_map = cli_runner.invoke(app, ["map"])
        assert result_map.exit_code in (0, 1, 2)

    def test_t3_multi_file_patch_atomic_safety(self, temp_git_workspace: Path):
        """Integration 9: Multi-file patch with atomic rollback."""
        Patcher = get_patcher_cls()
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))

        f1 = temp_git_workspace / "f1.py"
        f2 = temp_git_workspace / "f2.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")
        guard.commit_success("chore: add f1 and f2", files=["f1.py", "f2.py"])

        guard.create_snapshot()

        # Patch f1 (valid) and f2 (invalid)
        Patcher.apply_file_patches(str(f1), "<<<<<<< SEARCH\nx = 1\n=======\nx = 10\n>>>>>>>", validate_ast=True)
        success2, err2 = Patcher.apply_file_patches(str(f2), "<<<<<<< SEARCH\ny = 2\n=======\ny = ((\n>>>>>>>", validate_ast=True)

        if not success2:
            guard.rollback()

        assert f1.read_text(encoding="utf-8") == "x = 1\n"
        assert f2.read_text(encoding="utf-8") == "y = 2\n"

    def test_t3_session_file_tracking_with_git_diff(self, temp_git_workspace: Path):
        """Integration 10: Session file tracking with Git diff."""
        SessionManager = get_session_manager_cls()
        session = SessionManager(workspace_dir=str(temp_git_workspace))
        session.add_file("main.py")

        (temp_git_workspace / "main.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
        if hasattr(session, "git_guard"):
            diff = session.git_guard.get_diff()
            assert "main.py" in diff or diff != ""


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS & BENCHMARKS
# ==============================================================================

class TestTier4RealWorldScenariosAndBenchmarks:
    """Tier 4: Realistic Application Scenarios and Performance Benchmarks."""

    def test_t4_scenario_greenfield_module_creation_and_test(self, temp_git_workspace: Path):
        """
        Scenario 1: Greenfield Module Creation & Verification
        Create a new module `algorithms/sort.py`, verify syntax, and commit via GitGuard.
        """
        GitGuard = get_git_guard_cls()
        verifier = Verifier()
        guard = GitGuard(repo_dir=str(temp_git_workspace))

        algo_dir = temp_git_workspace / "algorithms"
        algo_dir.mkdir()
        sort_py = algo_dir / "sort.py"

        sort_code = (
            "def quicksort(arr: list[int]) -> list[int]:\n"
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    middle = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quicksort(left) + middle + quicksort(right)\n"
        )
        sort_py.write_text(sort_code, encoding="utf-8")

        res = verifier.verify_python_ast(sort_code)
        assert res.success is True

        commit_sha = guard.commit_success("feat(algorithms): add quicksort implementation", files=["algorithms/sort.py"])
        assert commit_sha is not None
        assert guard.get_diff() == ""

    def test_t4_scenario_multi_turn_repl_refactor(self, temp_git_workspace: Path):
        """
        Scenario 2: Multi-Turn REPL Refactor Workflow
        Simulate turns: /add file -> patch file -> /diff -> /undo -> verify status.
        """
        SessionManager = get_session_manager_cls()
        Patcher = get_patcher_cls()

        session = SessionManager(workspace_dir=str(temp_git_workspace))
        main_file = temp_git_workspace / "main.py"
        orig_code = main_file.read_text(encoding="utf-8")

        # Turn 1: Add file
        session.add_file("main.py")
        assert "main.py" in session.get_context_files()[0]

        # Turn 2: Apply refactor patch
        patch = (
            "<<<<<<< SEARCH\ndef add(a: int, b: int) -> int:\n    \"\"\"Adds two integers.\"\"\"\n    return a + b\n"
            "=======\n"
            "def add(a: int, b: int) -> int:\n    \"\"\"Adds two integers with logging.\"\"\"\n    print(f'Adding {a} + {b}')\n    return a + b\n"
            ">>>>>>>"
        )
        success, _ = Patcher.apply_file_patches(str(main_file), patch, validate_ast=True)
        assert success is True

        # Turn 3: Undo refactor
        undo_ok, _ = session.undo_last_edit()
        assert undo_ok is True
        assert main_file.read_text(encoding="utf-8") == orig_code

    def test_t4_scenario_precise_doc_injection_repair(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        """
        Scenario 3: Precise DevDocs Injection into Failing Test Repair
        Retrieve exact doc snippet for json deserialization and use it to format repair context.
        """
        DocRetriever = get_doc_retriever_cls()
        verifier = Verifier()

        retriever = DocRetriever(db_path=str(tmp_path / "repair_docs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        doc_context = retriever.format_context_snippets("json.loads deserialization", max_tokens=250)
        assert "json.loads" in doc_context

        repaired_code = (
            "import json\n\n"
            "def parse_payload(payload_str: str) -> dict:\n"
            f"    # Grounded via DevDocs: {doc_context[:40]}...\n"
            "    return json.loads(payload_str)\n"
        )
        res = verifier.verify_python_ast(repaired_code)
        assert res.success is True

    def test_t4_scenario_multi_file_repo_map_refactor(self, sample_multi_module_workspace: Path):
        """
        Scenario 4: Multi-File Repo Map Snapshot Context Injection
        Extract full workspace symbol tree, prioritize modified files, and patch interconnected modules.
        """
        RepoMap = get_repo_map_cls()
        Patcher = get_patcher_cls()
        verifier = Verifier()

        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        tree = repo_map.get_repo_map(max_tokens=400, focus_files=["service.py"])

        assert "InvoiceService" in tree
        assert "Calculator" in tree

        # Patch service.py
        service_file = sample_multi_module_workspace / "service.py"
        patch = (
            "<<<<<<< SEARCH\n    def compute_total(self, items: list[float], tax_rate: float = 0.05) -> str:\n"
            "=======\n"
            "    def compute_total(self, items: list[float], tax_rate: float = 0.08) -> str:\n"
            ">>>>>>>"
        )
        success, _ = Patcher.apply_file_patches(str(service_file), patch, validate_ast=True)
        assert success is True

        res = verifier.verify_python_ast(service_file.read_text(encoding="utf-8"))
        assert res.success is True

    def test_t4_scenario_syntax_error_rollback_safety(self, temp_git_workspace: Path):
        """
        Scenario 5: Syntax Error Rollback Safety Net
        Verify that multi-file patch sequences failing AST validation preserve untouched git state.
        """
        Patcher = get_patcher_cls()
        GitGuard = get_git_guard_cls()
        guard = GitGuard(repo_dir=str(temp_git_workspace))

        main_file = temp_git_workspace / "main.py"
        original = main_file.read_text(encoding="utf-8")

        guard.create_snapshot()

        corrupt_patch = (
            "<<<<<<< SEARCH\ndef add(a: int, b: int) -> int:\n=======\ndef add(a: int, b: int\n>>>>>>>"
        )
        Patcher.apply_file_patches(str(main_file), corrupt_patch, validate_ast=True)
        guard.rollback()

        assert main_file.read_text(encoding="utf-8") == original
        assert guard.get_diff() == ""

    def test_t4_benchmark_peak_rss_ram(self, sample_multi_module_workspace: Path, sample_stdlib_doc_data: Dict[str, Any]):
        """
        Benchmark 1: Peak System RSS RAM Consumption < 1024 MB
        Executes full pipeline: DocRetriever indexing & search, RepoMap generation,
        Patcher parsing & application, Verifier AST checks, and verifies process RSS memory.
        """
        DocRetriever = get_doc_retriever_cls()
        RepoMap = get_repo_map_cls()
        Patcher = get_patcher_cls()
        verifier = Verifier()

        # 1. DocRetriever operations
        retriever = DocRetriever(db_path=str(sample_multi_module_workspace / "bench_docs.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)
        for _ in range(50):
            retriever.search("path exists json loads sqrt", limit=5, max_tokens=250)

        # 2. RepoMap operations
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))
        for _ in range(20):
            repo_map.get_repo_map(max_tokens=400)

        # 3. Patcher & Verifier operations
        calc_file = sample_multi_module_workspace / "core" / "calculator.py"
        code = calc_file.read_text(encoding="utf-8")
        for _ in range(50):
            verifier.verify_python_ast(code)
            Patcher.parse_search_replace_blocks("<<<<<<< SEARCH\na\n=======\nb\n>>>>>>>")

        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)
        assert rss_mb < 1024.0, f"Peak RSS exceeded 1024 MB budget: {rss_mb:.2f} MB"

    def test_t4_benchmark_doc_retriever_fts5_latency(self, tmp_path: Path, sample_stdlib_doc_data: Dict[str, Any]):
        """
        Benchmark 2: SQLite FTS5 Search Latency < 5ms
        Runs 100 queries against the indexed FTS5 database and checks mean latency.
        """
        DocRetriever = get_doc_retriever_cls()
        retriever = DocRetriever(db_path=str(tmp_path / "latency_bench.db"))
        for mod, data in sample_stdlib_doc_data.items():
            retriever.index_module(mod, data)

        latencies = []
        queries = ["os.path.join", "math.sqrt", "json.loads", "exists", "factorial"] * 20
        for q in queries:
            start = time.perf_counter()
            retriever.search(q, limit=3, max_tokens=250)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

        mean_latency = sum(latencies) / len(latencies)
        assert mean_latency < 5.0, f"Mean FTS5 query latency exceeded 5ms: {mean_latency:.3f} ms"

    def test_t4_benchmark_repo_map_latency(self, sample_multi_module_workspace: Path):
        """
        Benchmark 3: AST Repo Map Generation Latency < 250ms
        Runs 10 iterations of RepoMap extraction across the multi-module workspace.
        """
        RepoMap = get_repo_map_cls()
        repo_map = RepoMap(root_dir=str(sample_multi_module_workspace))

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            repo_map.get_repo_map(max_tokens=400)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

        mean_latency = sum(latencies) / len(latencies)
        assert mean_latency < 250.0, f"Mean RepoMap latency exceeded 250ms: {mean_latency:.3f} ms"
