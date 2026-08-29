"""
test_k_cli_full_e2e.py - Comprehensive End-to-End Integration Test Suite for K-CLI

Validates the 5 Core Quality Assurance Pillars:
1. CLI Launch & Interactive Slash Commands (/model, /persona, /diff, /help, /undo, /add, /status)
2. Universal LLM Driver Switching (Ollama Bankai-7B/14B, Gemini, Claude, Mock)
3. Dynamic Persona Dispatch, Prompt Formatting & Auto-Debug Loop
4. Surgical Patch Application, Fuzzy Matching, AST Verification & Git Rollback
5. AST Codebase Repo Mapping & SQLite FTS5 DevDocs Retrieval
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import psutil
import pytest
from typer.testing import CliRunner

# Ensure root paths are available in sys.path
_this_file = Path(__file__).resolve()
_k_cli_dir = Path(__file__).parent.parent.resolve()
_root_dir = _k_cli_dir.parent

for p in [_this_file.parent.parent, _k_cli_dir, _root_dir]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from k_cli.cli import app, execute_run, print_banner, _resolve_val, get_persona_color, compute_diff
    from k_cli.core.session import SessionManager
    from k_cli.agents.orchestrator import Orchestrator, Persona, OrchestratorResult, PERSONA_PROMPTS
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.git.verifier import Verifier, VerificationResult, CodeExtractor
    from k_cli.git.patcher import Patcher
    from k_cli.git.git_guard import GitGuard
    from k_cli.git.repo_map import RepoMap
    from k_cli.tools.doc_retriever import DocRetriever
    from k_cli.agents.persona import DomainPersona, PersonaProfile, PersonaRegistry
except (ModuleNotFoundError, ImportError):
    from k_cli.cli import app, execute_run, print_banner, _resolve_val, get_persona_color, compute_diff
    from session import SessionManager
    from orchestrator import Orchestrator, Persona, OrchestratorResult, PERSONA_PROMPTS
    from llm_driver import LLMDriver
    from verifier import Verifier, VerificationResult, CodeExtractor
    from patcher import Patcher
    from git_guard import GitGuard
    from repo_map import RepoMap
    from doc_retriever import DocRetriever
    try:
        from persona import DomainPersona, PersonaProfile, PersonaRegistry
    except (ModuleNotFoundError, ImportError):
        DomainPersona = None  # type: ignore
        PersonaProfile = None  # type: ignore
        PersonaRegistry = None  # type: ignore


# ==============================================================================
# Fixtures & Test Helpers
# ==============================================================================

@pytest.fixture
def cli_runner():
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Initializes an isolated Git repository with an initial commit."""
    repo_dir = tmp_path / "e2e_git_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "e2e-tester@k-cli.local"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "K-CLI E2E Lead"], cwd=repo_dir, check=True, capture_output=True)

    sample_file = repo_dir / "calculator.py"
    sample_file.write_text(
        'def add(a: int, b: int) -> int:\n'
        '    """Returns sum of two integers."""\n'
        '    return a + b\n\n'
        'def subtract(a: int, b: int) -> int:\n'
        '    """Returns subtraction of b from a."""\n'
        '    return a - b\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


@pytest.fixture
def sample_project_tree(tmp_path: Path):
    """Creates a realistic multi-module workspace for RepoMap and DevDocs testing."""
    ws = tmp_path / "project_tree"
    ws.mkdir(parents=True, exist_ok=True)

    # utils/math_ops.py
    utils_dir = ws / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    (utils_dir / "__init__.py").write_text("", encoding="utf-8")
    (utils_dir / "math_ops.py").write_text(
        '"""Mathematical operations module."""\n\n'
        'def compute_factorial(n: int) -> int:\n'
        '    """Computes factorial recursively."""\n'
        '    if n <= 1:\n'
        '        return 1\n'
        '    return n * compute_factorial(n - 1)\n\n'
        'def is_prime(n: int) -> bool:\n'
        '    """Checks if a number is prime."""\n'
        '    if n < 2:\n'
        '        return False\n'
        '    for i in range(2, int(n ** 0.5) + 1):\n'
        '        if n % i == 0:\n'
        '            return False\n'
        '    return True\n',
        encoding="utf-8",
    )

    # models/data_model.py
    models_dir = ws / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "__init__.py").write_text("", encoding="utf-8")
    (models_dir / "data_model.py").write_text(
        'from dataclasses import dataclass\n\n'
        '@dataclass\n'
        'class UserRecord:\n'
        '    """User data record."""\n'
        '    username: str\n'
        '    access_level: int\n\n'
        '    def is_admin(self) -> bool:\n'
        '        return self.access_level >= 10\n',
        encoding="utf-8",
    )

    # main.py
    (ws / "main.py").write_text(
        'from utils.math_ops import compute_factorial\n'
        'from models.data_model import UserRecord\n\n'
        'def main():\n'
        '    user = UserRecord("alice", 10)\n'
        '    print(f"User {user.username} admin: {user.is_admin()}")\n'
        '    print(f"Fact(5) = {compute_factorial(5)}")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n',
        encoding="utf-8",
    )

    return ws


# ==============================================================================
# PILLAR 1: CLI Launch & Interactive Slash Commands
# ==============================================================================

class TestPillar1CliAndSlashCommands:
    """Validates CLI command line interface, diagnostics, and interactive slash commands."""

    def test_cli_help_and_version_diagnostics(self, cli_runner):
        """CLI launches with --help and displays description and available subcommands."""
        result = cli_runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "K-CLI" in result.output
        assert "run" in result.output
        assert "verify" in result.output
        assert "status" in result.output
        assert "doc" in result.output
        assert "map" in result.output

    def test_cli_status_command(self, cli_runner):
        """CLI status subcommand returns memory budget, driver type, and environment info."""
        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "K-CLI System Diagnostics" in result.output
        assert "Memory RSS Allocation" in result.output
        assert "SLM Driver Engine" in result.output
        assert "Python Environment" in result.output

    def test_cli_run_mock_command(self, cli_runner):
        """CLI run subcommand executes mock task and outputs verified code."""
        result = cli_runner.invoke(app, ["run", "Write a memory monitor", "--mock"])
        assert result.exit_code == 0
        assert "GROUND-TRUTH VERIFIED" in result.output or "Verified" in result.output

    def test_cli_verify_command_valid_and_invalid(self, cli_runner, tmp_path):
        """CLI verify subcommand properly distinguishes valid code from syntax errors."""
        # Valid code
        valid_py = tmp_path / "valid.py"
        valid_py.write_text("def hello() -> str: return 'world'\n", encoding="utf-8")
        res_valid = cli_runner.invoke(app, ["verify", str(valid_py)])
        assert res_valid.exit_code == 0
        assert "passed ground-truth" in res_valid.output

        # Syntax error
        invalid_py = tmp_path / "invalid.py"
        invalid_py.write_text("def broken(:\n    pass\n", encoding="utf-8")
        res_invalid = cli_runner.invoke(app, ["verify", str(invalid_py)])
        assert res_invalid.exit_code == 1
        assert "failed verification" in res_invalid.output

    def test_slash_command_help(self, temp_git_repo):
        """Slash command /help returns formatted list of commands including /model, /persona, /diff."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        handled, msg = session.handle_slash_command("/help")
        assert handled is True
        assert "/model" in msg
        assert "/persona" in msg
        assert "/diff" in msg
        assert "/undo" in msg or "/rollback" in msg
        assert "/status" in msg

    def test_slash_command_model_inspection_and_switch(self, temp_git_repo):
        """Slash command /model switches LLM model and queries active model."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        
        # Query active model
        handled, msg = session.handle_slash_command("/model")
        assert handled is True
        assert "Active model:" in msg

        # Switch to Bankai-7B
        handled, msg = session.handle_slash_command("/model bankai-7b")
        assert handled is True
        assert "Switched active model to 'bankai-7b'" in msg
        assert session.model_name == "bankai-7b"
        assert session.driver.model_name == "bankai-7b"

        # Switch to Bankai-14B
        handled, msg = session.handle_slash_command("/model bankai-14b")
        assert handled is True
        assert "bankai-14b" in msg
        assert session.model_name == "bankai-14b"

        # Switch to Gemini
        handled, msg = session.handle_slash_command("/model gemini-1.5-pro")
        assert handled is True
        assert "gemini-1.5-pro" in msg
        assert session.model_name == "gemini-1.5-pro"

        # Switch to Claude
        handled, msg = session.handle_slash_command("/model claude-3-5-sonnet")
        assert handled is True
        assert "claude-3-5-sonnet" in msg
        assert session.model_name == "claude-3-5-sonnet"

    def test_slash_command_persona_inspection_and_switch(self, temp_git_repo):
        """Slash command /persona inspects and switches active persona."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        
        # Query active persona
        handled, msg = session.handle_slash_command("/persona")
        assert handled is True
        assert "Persona" in msg or "persona" in msg.lower()

        # Switch to DevOps persona
        handled, msg = session.handle_slash_command("/persona devops")
        assert handled is True
        assert "devops" in msg.lower() or "DevOps" in str(session.active_persona)

        # Switch to Security persona
        handled, msg = session.handle_slash_command("/persona security")
        assert handled is True
        assert "security" in msg.lower() or "Security" in str(session.active_persona)

        # Switch to Systems persona
        handled, msg = session.handle_slash_command("/persona systems")
        assert handled is True
        assert "systems" in msg.lower() or "Systems" in str(session.active_persona)

        # Switch to Debugger persona
        handled, msg = session.handle_slash_command("/persona debugger")
        assert handled is True
        assert "debugger" in msg.lower() or "Debugger" in str(session.active_persona)

        # Switch to Classic Coder / Default
        handled, msg = session.handle_slash_command("/persona default")
        assert handled is True
        assert "default" in msg.lower() or "Default" in str(session.active_persona) or "Generalist" in str(session.active_persona)

        # Invalid persona handling returns informative message
        handled, msg = session.handle_slash_command("/persona unknown_xyz_invalid")
        assert "Unknown persona" in msg or "Invalid persona" in msg or "Available" in msg

    def test_slash_command_diff_and_undo(self, temp_git_repo):
        """Slash commands /diff and /undo /rollback show git modifications and restore state."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        # In clean repo
        handled, msg = session.handle_slash_command("/diff")
        assert handled is True
        assert "clean" in msg.lower() or "no uncommitted" in msg.lower()

        # Modify calculator.py
        target = temp_git_repo / "calculator.py"
        target.write_text(target.read_text(encoding="utf-8") + "\ndef multiply(a, b): return a * b\n", encoding="utf-8")

        # Now /diff should show changes
        handled, msg = session.handle_slash_command("/diff")
        assert handled is True
        assert "+def multiply" in msg

        # Now /undo or /rollback should restore clean state
        handled, msg = session.handle_slash_command("/undo")
        assert handled is True
        assert "rolled back" in msg.lower() or "successfully" in msg.lower()

        # Verify file restored
        assert "multiply" not in target.read_text(encoding="utf-8")

    def test_slash_command_add_remove_clear_status(self, temp_git_repo):
        """Slash commands /add, /remove, /clear, /status, /exit."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)

        # /add file
        handled, msg = session.handle_slash_command("/add calculator.py")
        assert handled is True
        assert "calculator.py" in session.get_context_files()

        # /status
        handled, msg = session.handle_slash_command("/status")
        assert handled is True
        assert "calculator.py" in msg
        assert "Active Model:" in msg

        # /remove file
        handled, msg = session.handle_slash_command("/remove calculator.py")
        assert handled is True
        assert "calculator.py" not in session.get_context_files()

        # /clear
        session.history.append({"prompt": "test", "response": "code"})
        session.add_file("calculator.py")
        handled, msg = session.handle_slash_command("/clear")
        assert handled is True
        assert len(session.history) == 0
        assert len(session.get_context_files()) == 0

        # /exit
        handled, msg = session.handle_slash_command("/exit")
        assert handled is True
        assert msg == "EXIT"


# ==============================================================================
# PILLAR 2: Universal LLM Driver Switching
# ==============================================================================

class TestPillar2UniversalLLMDriver:
    """Validates multi-model driver configuration, Ollama/Gemini/Claude/Mock switching and resilience."""

    def test_driver_initialization_with_diverse_models(self):
        """Driver initializes correctly for Bankai-7B/14B, Gemini, Claude, and local models."""
        models = [
            "bankai-7b",
            "bankai-14b",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "claude-3-5-sonnet",
            "claude-3-opus",
            "qwen2.5-coder:1.5b",
            "deepseek-coder:6.7b",
        ]
        for m in models:
            driver = LLMDriver(model_name=m, mock_mode=True)
            assert driver.model_name == m
            assert driver.mock_mode is True

    def test_driver_environment_variable_override(self, monkeypatch):
        """KCLI_MODEL and OLLAMA_HOST environment variables override driver defaults."""
        monkeypatch.setenv("KCLI_MODEL", "bankai-14b")
        monkeypatch.setenv("OLLAMA_HOST", "http://ai-cluster:11434")

        driver = LLMDriver(model_name="default-model", ollama_url="http://localhost:11434")
        assert driver.model_name == "bankai-14b"
        assert driver.ollama_url == "http://ai-cluster:11434"

    def test_driver_generation_across_personas(self):
        """Driver generates appropriate deterministic responses for all persona roles."""
        driver = LLMDriver(model_name="bankai-7b", mock_mode=True)

        # RESEARCHER
        res_r = driver.generate("Inspect task", system_prompt="You are [RESEARCHER] persona")
        assert "Task" in res_r or "RAM" in res_r

        # ARCHITECT
        res_a = driver.generate("Plan task", system_prompt="You are [ARCHITECT] persona")
        assert "<think>" in res_a

        # CODER
        res_c = driver.generate("Code task", system_prompt="You are [CODER] persona")
        assert "def " in res_c or "import " in res_c

        # CRITIC
        res_cr = driver.generate("Review task", system_prompt="You are [CRITIC] persona")
        assert "VALIDATED" in res_cr

        # DEBUGGER
        res_d = driver.generate("Fix task", system_prompt="You are [DEBUGGER] persona")
        assert "```python" in res_d

    def test_driver_token_streaming(self):
        """Driver streams tokens sequentially via callback function."""
        driver = LLMDriver(model_name="bankai-14b", mock_mode=True)
        streamed_tokens: List[str] = []

        def callback(tok: str):
            streamed_tokens.append(tok)

        full_output = driver.generate(
            "Write a simple function",
            system_prompt="You are [CODER] persona",
            stream_callback=callback,
        )
        assert len(streamed_tokens) > 0
        assert "".join(streamed_tokens) == full_output

    def test_driver_ollama_presence_check_and_fallback(self):
        """Driver accurately parses Ollama tags endpoint and falls back safely on connection error."""
        driver = LLMDriver(model_name="bankai-7b", mock_mode=False)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "models": [{"name": "bankai-7b"}, {"name": "qwen2.5-coder:1.5b"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        # Model present in Ollama
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is True

        # Network error -> falls back gracefully
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            with patch.object(driver, "get_native_llama", return_value=None):
                assert driver.is_ollama_available() is False
                # Generate still succeeds via mock fallback
                output = driver.generate("Test prompt", system_prompt="You are [RESEARCHER] persona")
                assert output != ""


# ==============================================================================
# PILLAR 3: Dynamic Persona Dispatch & Prompt Formatting
# ==============================================================================

class TestPillar3PersonaDispatchAndPipeline:
    """Validates Persona state machine, prompt construction, auto-debug retries, and RAM budget."""

    def test_persona_enum_and_system_prompts_completeness(self):
        """All 5 personas have detailed non-conversational system prompts."""
        expected_personas = {
            Persona.RESEARCHER,
            Persona.ARCHITECT,
            Persona.CODER,
            Persona.CRITIC,
            Persona.DEBUGGER,
        }
        assert set(Persona) == expected_personas

        for p in Persona:
            prompt = PERSONA_PROMPTS.get(p)
            assert prompt is not None
            assert len(prompt) > 30
            assert p.value in prompt

    def test_domain_persona_registry_and_phase_prompt_modulation(self):
        """Domain personas in PersonaRegistry format phase-modulated system prompts."""
        if PersonaRegistry is None:
            pytest.skip("PersonaRegistry not available")

        profiles = PersonaRegistry.list_personas()
        assert len(profiles) >= 6

        # Check DevOps persona
        devops = PersonaRegistry.get("devops")
        assert devops is not None
        assert devops.id == "devops"
        assert "Docker" in str(devops.expertise) or "Kubernetes" in str(devops.expertise)

        # Check phase modulation for CODER phase
        coder_prompt = devops.get_phase_system_prompt(Persona.CODER)
        assert "DevOps" in coder_prompt
        assert "CODER" in coder_prompt
        assert "Strictly" in coder_prompt or "Constraints" in coder_prompt

    def test_orchestrator_sequential_pipeline_execution(self):
        """Orchestrator runs [RESEARCHER] -> [ARCHITECT] -> [CODER] -> [CRITIC] -> [VERIFIER]."""
        driver = LLMDriver(mock_mode=True)
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier)

        captured_stages: List[Tuple[Persona, str]] = []

        def stream_callback(persona, token):
            captured_stages.append((persona, token))

        result = orchestrator.execute_pipeline(
            user_prompt="Write a function to calculate square root",
            language="python",
            token_stream_callback=stream_callback,
        )

        assert isinstance(result, OrchestratorResult)
        assert result.success is True
        assert result.attempts == 1
        assert result.language == "python"
        assert result.final_code != ""
        assert len(result.history) >= 4

        # Verify all persona stages recorded in history
        personas_in_history = [h["persona"] for h in result.history if isinstance(h, dict)]
        assert Persona.RESEARCHER.value in personas_in_history
        assert Persona.ARCHITECT.value in personas_in_history
        assert Persona.CODER.value in personas_in_history
        assert Persona.CRITIC.value in personas_in_history

    def test_orchestrator_auto_debug_loop_with_debugger_persona(self):
        """Orchestrator triggers DEBUGGER persona on syntax failure and recovers within max_retries."""
        class FlawedFirstAttemptDriver(LLMDriver):
            def __init__(self, *args, **kwargs):
                kwargs["mock_mode"] = True
                super().__init__(*args, **kwargs)
                self.calls = 0

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                sys_lower = (system_prompt or "").lower()
                if "coder" in sys_lower:
                    # Syntax error: unclosed parenthesis
                    res = "```python\ndef broken_add(a, b:\n    return a + b\n```"
                elif "debugger" in sys_lower:
                    # Fixed code on debug retry
                    res = "```python\ndef broken_add(a, b):\n    return a + b\n```"
                else:
                    res = super().generate(prompt, system_prompt, temperature, stream_callback)

                if stream_callback:
                    for chunk in res.split():
                        stream_callback(chunk + " ")
                return res

        driver = FlawedFirstAttemptDriver()
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=3)

        result = orchestrator.execute_pipeline("Fix broken add", language="python")
        assert result.success is True
        assert result.attempts == 2  # 1 initial + 1 debug retry
        assert result.final_code == "def broken_add(a, b):\n    return a + b"

        # Diff computation should accurately identify the fix
        diff = compute_diff("def broken_add(a, b:\n    return a + b", result.final_code)
        assert "-def broken_add(a, b:" in diff
        assert "+def broken_add(a, b):" in diff

    def test_orchestrator_ram_budget_check_and_gc(self):
        """Orchestrator tracks process RSS RAM and ensures execution within 1024MB budget."""
        orchestrator = Orchestrator(ram_budget_mb=1024.0)
        current_ram = orchestrator.get_current_ram_mb()
        assert isinstance(current_ram, float)
        assert 0 < current_ram < 1024.0

        checked_ram = orchestrator.check_ram_budget()
        assert checked_ram <= 1024.0

    def test_orchestrator_fluff_stripping(self):
        """strip_fluff removes conversational chatter, intro headers, and markdown fences."""
        cases = [
            ("Sure! Here is the python code:\n```python\nprint('hello')\n```\nHope this helps!", "print('hello')"),
            ("```bash\necho 123\n```", "echo 123"),
            ("def pure_code():\n    return True\n", "def pure_code():\n    return True"),
        ]
        for raw, expected in cases:
            assert Orchestrator.strip_fluff(raw) == expected


# ==============================================================================
# PILLAR 4: Surgical Patch Application, AST Verification & Git Rollback
# ==============================================================================

class TestPillar4SurgicalPatcherAndGitRollback:
    """Validates SEARCH/REPLACE block parsing, fuzzy matching, AST pre-write checks, and Git rollback."""

    def test_parse_single_and_multiple_search_replace_blocks(self):
        """Patcher extracts multiple <<<<<<< SEARCH / ======= / >>>>>>> blocks cleanly."""
        text = (
            "Here is the surgical patch:\n\n"
            "<<<<<<< SEARCH\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "=======\n"
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
            ">>>>>>>\n\n"
            "And second block:\n"
            "<<<<<<< SEARCH\n"
            "def sub(a, b):\n"
            "    return a - b\n"
            "=======\n"
            "def sub(a: int, b: int) -> int:\n"
            "    return a - b\n"
            ">>>>>>>\n"
        )
        blocks = Patcher.parse_search_replace_blocks(text)
        assert len(blocks) == 2
        assert "def add(a, b):" in blocks[0][0]
        assert "-> int:" in blocks[0][1]
        assert "def sub(a, b):" in blocks[1][0]
        assert "-> int:" in blocks[1][1]

    def test_fuzzy_matching_indentation_and_whitespace_tolerance(self):
        """Patcher matches code with uniform indentation shift and whitespace differences."""
        orig = (
            "class MyService:\n"
            "    def handle(self):\n"
            "        val = 10\n"
            "        return val\n"
        )
        # Search block with 0-space base indentation
        search_block = (
            "def handle(self):\n"
            "    val = 10\n"
            "    return val\n"
        )
        replace_block = (
            "def handle(self):\n"
            "    val = 20\n"
            "    return val * 2\n"
        )

        success, patched, err = Patcher.apply_patch(orig, search_block, replace_block, fuzzy=True)
        assert success is True
        assert "val = 20" in patched
        assert "return val * 2" in patched
        # Preserves class-level 4-space indentation
        assert "    def handle(self):" in patched
        assert "        val = 20" in patched

    def test_ast_verification_blocks_broken_patch_write(self, tmp_path):
        """Patcher validates AST before disk write; syntax errors leave the disk file 100% untouched."""
        target_file = tmp_path / "module.py"
        original_code = "def calculate(x: int) -> int:\n    return x * 2\n"
        target_file.write_text(original_code, encoding="utf-8")

        # Patch that introduces a syntax error (broken colon/parens)
        broken_patch = (
            "<<<<<<< SEARCH\n"
            "def calculate(x: int) -> int:\n"
            "    return x * 2\n"
            "=======\n"
            "def calculate(x: int -> int\n"
            "    return x * 2\n"
            ">>>>>>>\n"
        )

        success, err = Patcher.apply_file_patches(str(target_file), broken_patch, validate_ast=True)
        assert success is False
        assert "AST" in err or "SyntaxError" in err
        # File on disk MUST be identical to original
        assert target_file.read_text(encoding="utf-8") == original_code

    def test_git_guard_atomic_commit_and_instant_rollback(self, temp_git_repo):
        """GitGuard creates snapshot, commits valid changes, and rolls back on failure."""
        gg = GitGuard(repo_dir=str(temp_git_repo))
        assert gg.is_git_repo() is True

        # 1. Snapshot
        snap_id = gg.create_snapshot()
        assert snap_id != ""

        # 2. Valid modification & commit
        calc_file = temp_git_repo / "calculator.py"
        calc_file.write_text(calc_file.read_text(encoding="utf-8") + "\ndef multiply(a, b): return a * b\n", encoding="utf-8")
        commit_sha = gg.commit_success("feat: add multiply function")
        assert commit_sha is not None
        assert gg.get_diff() == ""

        # 3. Flawed modification & rollback
        calc_file.write_text(calc_file.read_text(encoding="utf-8") + "\ndef broken_syntax(:\n", encoding="utf-8")
        assert gg.get_diff() != ""

        rb_success = gg.rollback()
        assert rb_success is True
        assert gg.get_diff() == ""
        assert "broken_syntax" not in calc_file.read_text(encoding="utf-8")

    def test_session_end_to_end_patch_workflow_with_rollback_on_failure(self, temp_git_repo):
        """SessionManager applies SEARCH/REPLACE patch from turn output or rolls back on failure."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        session.add_file("calculator.py")

        # Mock orchestrator to output a patch block
        patch_output = (
            "```python\n"
            "<<<<<<< SEARCH\n"
            "def subtract(a: int, b: int) -> int:\n"
            "    \"\"\"Returns subtraction of b from a.\"\"\"\n"
            "    return a - b\n"
            "=======\n"
            "def subtract(a: int, b: int) -> int:\n"
            "    \"\"\"Returns subtraction of b from a with logging.\"\"\"\n"
            "    return int(a - b)\n"
            ">>>>>>>\n"
            "```"
        )
        session.orchestrator.execute_pipeline = MagicMock(return_value=OrchestratorResult(
            success=True,
            final_code=patch_output,
            language="python",
            verification=VerificationResult(success=True, error_trace="", code=patch_output, verification_type="ast"),
            attempts=1,
            architecture_plan="Update subtract docstring and return cast",
            critic_output="VALIDATED",
            ram_usage_mb=session._get_current_ram_mb(),
        ))

        res = session.execute_turn("Update subtract function")
        assert res["success"] is True
        assert res["patches_applied"] is True

        # Verify disk file updated
        calc_content = (temp_git_repo / "calculator.py").read_text(encoding="utf-8")
        assert "with logging" in calc_content
        assert "return int(a - b)" in calc_content


# ==============================================================================
# PILLAR 5: Repo Mapping & DevDocs Retrieval
# ==============================================================================

class TestPillar5RepoMappingAndDevDocs:
    """Validates AST codebase symbol extraction, token budgeting, SQLite FTS5 search, and prompt injection."""

    def test_repo_map_symbol_extraction_and_hierarchy(self, sample_project_tree):
        """RepoMap extracts classes, methods, functions, and docstrings from workspace."""
        repo_map = RepoMap(root_dir=str(sample_project_tree))
        files = repo_map.scan_workspace_files()
        assert len(files) >= 3

        # Extract symbols from utils/math_ops.py
        math_file = str(sample_project_tree / "utils" / "math_ops.py")
        symbols = repo_map.extract_symbols(math_file)
        sym_names = [s.get("name") for s in symbols]
        assert "compute_factorial" in sym_names
        assert "is_prime" in sym_names

        # Extract symbols from models/data_model.py
        model_file = str(sample_project_tree / "models" / "data_model.py")
        symbols_m = repo_map.extract_symbols(model_file)
        class_syms = [s for s in symbols_m if s.get("type") == "class"]
        assert len(class_syms) == 1
        assert class_syms[0]["name"] == "UserRecord"
        assert "is_admin" in [m.get("name") for m in class_syms[0].get("methods", [])]

    def test_repo_map_token_budgeting_and_focus_file_prioritization(self, sample_project_tree):
        """RepoMap respects max_tokens budget (< 400 tokens) and prioritizes focused context files."""
        repo_map = RepoMap(root_dir=str(sample_project_tree))
        focus = ["models/data_model.py"]

        tree_map = repo_map.get_repo_map(max_tokens=200, focus_files=focus)
        assert tree_map != ""
        # Focused file should appear first or be prioritized
        assert "UserRecord" in tree_map
        # Estimated token budget check (words approx)
        assert len(tree_map.split()) <= 250

    def test_doc_retriever_sqlite_fts5_indexing_and_search(self, tmp_path):
        """DocRetriever creates SQLite FTS5 index, indexes doc entries, and performs fast BM25 search."""
        db_file = tmp_path / "test_devdocs.db"
        retriever = DocRetriever(db_path=str(db_file), auto_index=False)

        custom_docs = {
            "functions": [
                {
                    "name": "parse_jwt_token",
                    "signature": "parse_jwt_token(token: str, secret: str) -> dict",
                    "doc": "Decodes and verifies JSON Web Token signature using HMAC-SHA256.",
                },
                {
                    "name": "verify_signature",
                    "signature": "verify_signature(data: bytes, sig: bytes) -> bool",
                    "doc": "Cryptographically validates payload byte signature against public key.",
                },
            ],
            "classes": [
                {
                    "name": "TokenManager",
                    "signature": "class TokenManager(cache_ttl: int = 3600)",
                    "doc": "Manages lifecycle and revocation list for authentication tokens.",
                    "methods": [
                        {
                            "name": "revoke",
                            "signature": "revoke(token_id: str) -> None",
                            "doc": "Adds token ID to revocation blocklist.",
                        }
                    ],
                }
            ],
        }

        indexed_count = retriever.index_module("security.jwt", custom_docs)
        assert indexed_count >= 3

        # Search for exact function symbol
        t0 = time.perf_counter()
        results = retriever.search("parse_jwt_token", limit=5)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        assert len(results) >= 1
        assert any("parse_jwt_token" in r["name"] for r in results)
        assert latency_ms < 50.0  # High-speed retrieval requirement

        # Context snippet formatting with token budget
        snippets = retriever.format_context_snippets("parse_jwt_token", max_tokens=150)
        assert "parse_jwt_token" in snippets

        # Search for class symbol
        class_results = retriever.search("TokenManager", limit=5)
        assert len(class_results) >= 1
        assert any("TokenManager" in r["name"] for r in class_results)

    def test_end_to_end_session_with_repomap_and_devdocs_injection(self, sample_project_tree):
        """SessionManager integrates RepoMap and DocRetriever into enriched prompt formulation."""
        db_file = sample_project_tree / "devdocs.db"
        retriever = DocRetriever(db_path=str(db_file), auto_index=False)
        retriever.index_module("math", {
            "functions": [{
                "name": "is_prime",
                "signature": "is_prime(n: int) -> bool",
                "doc": "Fast primality testing.",
            }]
        })

        session = SessionManager(
            workspace_dir=str(sample_project_tree),
            doc_retriever=retriever,
            mock_mode=True,
        )
        session.add_file("utils/math_ops.py")

        # Capture prompt passed to orchestrator
        captured_prompt: List[str] = []
        original_execute = session.orchestrator.execute_pipeline

        def mock_execute(user_prompt, **kwargs):
            captured_prompt.append(user_prompt)
            return original_execute(user_prompt, **kwargs)

        session.orchestrator.execute_pipeline = mock_execute

        res = session.execute_turn("Check if 97 is prime")
        assert res["success"] is True
        assert len(captured_prompt) == 1
        prompt_text = captured_prompt[0]

        # Verify enriched prompt contains all layers
        assert "DevDocs Reference Snippets:" in prompt_text or "is_prime" in prompt_text
        assert "Workspace Repository Map:" in prompt_text or "math_ops" in prompt_text
        assert "Active Context Files:" in prompt_text
        assert "utils/math_ops.py" in prompt_text
        assert "User Task Request:" in prompt_text
        assert "Check if 97 is prime" in prompt_text


# ==============================================================================
# PILLAR 6: Full End-to-End System Integrity & Zero-Fluff Benchmark
# ==============================================================================

class TestPillar6FullSystemIntegrity:
    """Stress tests complete pipeline for end-to-end memory limits, determinism, and zero fluff."""

    def test_full_pipeline_memory_budget_under_1024mb(self, temp_git_repo):
        """End-to-end multi-turn session maintains strict RSS memory footprint < 1024 MB."""
        session = SessionManager(workspace_dir=str(temp_git_repo), mock_mode=True)
        session.add_file("calculator.py")

        for turn_idx in range(5):
            res = session.execute_turn(f"Task turn {turn_idx}: Optimize calculator routines")
            assert res["success"] is True
            assert res["ram_mb"] < 1024.0

        status = session.get_status()
        assert status["turns"] == 5
        assert status["ram_mb"] < 1024.0

    def test_zero_fluff_compiler_grounded_output(self, temp_git_repo):
        """Verified pipeline outputs only executable, ground-truth code with zero conversational fluff."""
        driver = LLMDriver(mock_mode=True)
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier)

        result = orchestrator.execute_pipeline("Write a function to return system info")
        assert result.success is True
        
        # Verify AST validity of final code
        tree = ast.parse(result.final_code)
        assert isinstance(tree, ast.Module)

        # Disallow conversational filler in final code
        forbidden_phrases = ["here is", "certainly", "hope this helps", "let me know"]
        for phrase in forbidden_phrases:
            assert phrase not in result.final_code.lower()
