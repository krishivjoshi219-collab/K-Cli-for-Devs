"""
test_cli.py - Unit and integration tests for K-CLI Typer terminal user interface (Milestone 5)
"""

import difflib
import sys
from pathlib import Path

# Add root package path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from typer.testing import CliRunner
from rich.syntax import Syntax
from rich.panel import Panel

from k_cli.cli import app, execute_run, print_banner, _resolve_val, get_persona_color, compute_diff, interactive_mode
from k_cli.agents.orchestrator import Orchestrator, Persona
from k_cli.core.llm_driver import LLMDriver
from k_cli.git.verifier import Verifier
from k_cli.tools.doc_retriever import DocRetriever
from k_cli.git.repo_map import RepoMap

runner = CliRunner()


def test_cli_banner():
    """Verify print_banner executes without error."""
    print_banner()
    assert True


def test_resolve_val():
    """Verify _resolve_val extracts raw value or fallback."""
    assert _resolve_val("python", "bash") == "python"
    assert _resolve_val(None, "default") == "default"


def test_get_persona_color():
    """Verify get_persona_color maps personas to correct colors."""
    assert get_persona_color("RESEARCHER") == "cyan"
    assert get_persona_color("ARCHITECT") == "magenta"
    assert get_persona_color("CODER") == "green"
    assert get_persona_color("CRITIC") == "yellow"
    assert get_persona_color("DEBUGGER") == "red"
    assert get_persona_color("UNKNOWN") == "blue"


def test_cli_status_command():
    """Verify status command renders diagnostics table with required fields."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "System Diagnostics" in result.output
    assert "Memory RSS Allocation" in result.output
    assert "Ollama" in result.output or "SLM Driver Engine" in result.output
    assert "Default Model" in result.output
    assert "Python Environment" in result.output


def test_cli_plan_is_read_only_and_renders_workspace(tmp_path):
    """Plan mode should inspect a workspace without changing its files."""
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return True\n", encoding="utf-8")
    before = source.read_text(encoding="utf-8")
    result = runner.invoke(app, ["plan", "add logging", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "protected plan" in result.output
    assert source.read_text(encoding="utf-8") == before


def test_cli_plan_renders_bounded_project_guidance(tmp_path):
    rules = tmp_path / ".kcli" / "rules.md"
    rules.parent.mkdir()
    rules.write_text("Prefer focused tests.", encoding="utf-8")

    result = runner.invoke(app, ["plan", "add tests", "--dir", str(tmp_path), "--rules", ".kcli/rules.md"])

    assert result.exit_code == 0
    assert "Project guidance" in result.output or "Custom Developer Instructions" in result.output
    assert "Prefer focused tests." in result.output


def test_cli_prompt_preview_is_provider_aware():
    result = runner.invoke(app, ["prompt", "add tests", "--model", "gemini-2.5-pro"])
    assert result.exit_code == 0
    assert "Gemini" in result.output
    assert "Task: add tests" in result.output


def test_cli_prompt_preview_can_include_project_guidance(tmp_path, monkeypatch):
    rules = tmp_path / ".kcli" / "rules.md"
    rules.parent.mkdir()
    rules.write_text("Keep the public API stable.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["prompt", "add tests", "--rules", ".kcli/rules.md"])

    assert result.exit_code == 0
    assert "Custom Developer Instructions" in result.output or "rules.md" in result.output
    assert "Keep the public API stable." in result.output


def test_cli_multi_model_audit_mock():
    result = runner.invoke(
        app,
        ["audit", "write a Python function", "--models", "model-a,model-b", "--mock"],
    )
    assert result.exit_code == 0
    assert "Multi-Model Swarm Audit" in result.output


def test_cli_doctor_reports_secret_hygiene(tmp_path):
    result = runner.invoke(app, ["doctor", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Secret hygiene" in result.output


def test_cli_review_requires_git_repository(tmp_path):
    result = runner.invoke(app, ["review", "--dir", str(tmp_path), "--json"])
    assert result.exit_code == 2
    assert '"git_repository": false' in result.output


def test_cli_review_reports_changed_python_syntax(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "K-CLI Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@k-cli.local"], cwd=tmp_path, check=True)
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n", encoding="utf-8")

    result = runner.invoke(app, ["review", "--dir", str(tmp_path), "--json"])

    assert result.exit_code == 1
    assert '"status": "failed"' in result.output
    assert "broken.py" in result.output


def test_cli_feature_proves_implementation_and_tests(tmp_path):
    (tmp_path / "feature.py").write_text(
        "def secure_patch_engine():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "test_feature.py").write_text(
        "def test_secure_patch_engine():\n    assert True\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["feature", "secure patch engine", "--dir", str(tmp_path), "--require-tests", "--json"])

    assert result.exit_code == 0
    assert '"proven": true' in result.output


def test_cli_run_command_mock():
    """Verify run command with mock LLM driver."""
    result = runner.invoke(app, ["run", "Write a RAM monitoring function", "--mock"])
    assert result.exit_code == 0
    assert "GROUND-TRUTH VERIFIED" in result.output or "Verified" in result.output


def test_cli_run_command_with_save_to(tmp_path):
    """Verify run command saves code when --save-to option is provided."""
    save_file = tmp_path / "output.py"
    result = runner.invoke(app, ["run", "Write a function to double an integer", "--mock", "--save-to", str(save_file)])
    assert result.exit_code == 0
    assert save_file.exists()
    assert save_file.read_text(encoding="utf-8").strip() != ""


def test_cli_run_command_with_test_code():
    """Verify run command with inline --test-code."""
    test_code = "def test_dummy(): assert True\n"
    result = runner.invoke(app, ["run", "Write solution", "--mock", "--test-code", test_code])
    assert result.exit_code == 0


def test_cli_run_command_with_test_file(tmp_path):
    """Verify run command with --test-file."""
    tf = tmp_path / "test_spec.py"
    tf.write_text("def test_dummy(): assert 1 == 1\n", encoding="utf-8")
    result = runner.invoke(app, ["run", "Write solution", "--mock", "--test-file", str(tf)])
    assert result.exit_code == 0


def test_cli_run_accepts_openai_compatible_options():
    result = runner.invoke(
        app,
        [
            "run",
            "Write a small function",
            "--mock",
            "--provider",
            "openai-compatible",
            "--base-url",
            "https://models.example/v1",
        ],
    )
    assert result.exit_code == 0


def test_cli_verify_command_valid_file(tmp_path):
    """Verify verify command with a valid Python file."""
    valid_file = tmp_path / "sample.py"
    valid_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(valid_file)])
    assert result.exit_code == 0
    assert "passed ground-truth" in result.output


def test_cli_verify_command_invalid_file(tmp_path):
    """Verify verify command raises exit code 1 on syntax error file."""
    invalid_file = tmp_path / "bad.py"
    invalid_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(invalid_file)])
    assert result.exit_code == 1
    assert "failed verification" in result.output or "Error Trace" in result.output


def test_cli_verify_command_inline_code_pass():
    """Verify verify command with valid inline --code string."""
    result = runner.invoke(app, ["verify", "-c", "def add(a, b):\n    return a + b\n"])
    assert result.exit_code == 0
    assert "passed ground-truth" in result.output


def test_cli_verify_command_inline_code_fail():
    """Verify verify command raises exit code 1 on invalid inline --code string."""
    result = runner.invoke(app, ["verify", "-c", "def invalid("])
    assert result.exit_code == 1
    assert "failed verification" in result.output or "Error Trace" in result.output


def test_cli_verify_command_no_args():
    """Verify verify command without file or code raises exit code 1."""
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == 1
    assert "Must specify" in result.output or "Error" in result.output


def test_cli_verify_command_with_pytest_pass(tmp_path):
    """Verify verify command passing pytest test suite."""
    src_file = tmp_path / "sol.py"
    src_file.write_text("def double(x: int) -> int:\n    return x * 2\n", encoding="utf-8")
    test_file = tmp_path / "test_sol.py"
    test_file.write_text("from solution import double\ndef test_double(): assert double(4) == 8\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(src_file), "--test-file", str(test_file)])
    assert result.exit_code == 0
    assert "passed ground-truth" in result.output


def test_cli_verify_command_with_pytest_fail(tmp_path):
    """Verify verify command raising exit code 1 when pytest test fails."""
    src_file = tmp_path / "sol.py"
    src_file.write_text("def double(x: int) -> int:\n    return x + 2\n", encoding="utf-8")
    test_file = tmp_path / "test_sol.py"
    test_file.write_text("from solution import double\ndef test_double(): assert double(4) == 8\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(src_file), "--test-file", str(test_file)])
    assert result.exit_code == 1


class MockFailingDriver(LLMDriver):
    """Driver that generates syntax error initially and fixes it on attempt 2."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("mock_mode", True)
        super().__init__(*args, **kwargs)

    def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        sys_lower = (system_prompt or "").lower()
        if "coder" in sys_lower:
            res = "```python\ndef broken_func(:\n    return 42\n```"
        elif "debugger" in sys_lower:
            res = "```python\ndef broken_func():\n    return 42\n```"
        else:
            res = super().generate(prompt, system_prompt, temperature, stream_callback)

        if stream_callback:
            for token in res.split():
                stream_callback(token + " ")
        return res


def test_cli_auto_debug_diff_rendering():
    """Verify unified diff calculation and CLI diff rendering when auto-debug retries occur."""
    driver = MockFailingDriver()
    verifier = Verifier()
    orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=3)

    tokens_captured = []

    def stream_cb(persona, token):
        tokens_captured.append((persona, token))

    res = orchestrator.execute_pipeline("Fix broken function", language="python", token_stream_callback=stream_cb)
    assert res.attempts == 2
    assert res.success is True

    coder_entry = next((h for h in res.history if h.get("persona") == Persona.CODER.value), None)
    assert coder_entry is not None
    initial_code = coder_entry["output"]

    diff_text = compute_diff(initial_code, res.final_code)
    assert "--- candidate_code.py" in diff_text
    assert "+++ repaired_code.py" in diff_text
    assert "-def broken_func(:" in diff_text
    assert "+def broken_func():" in diff_text
    assert len(tokens_captured) > 0


def test_cli_run_auto_debug_diff_output(monkeypatch):
    """Verify that execute_run outputs the diff panel when retries occur."""
    monkeypatch.setattr("k_cli.cli.LLMDriver", MockFailingDriver)
    result = runner.invoke(app, ["run", "Fix function", "--mock"])
    assert result.exit_code == 0
    assert "Auto-Debug Repair Diff" in result.output


def test_cli_doc_command_existing_symbol(tmp_path):
    """Verify k doc command searches and displays indexed API documentation."""
    db_file = tmp_path / "test_docs.db"
    retriever = DocRetriever(db_path=str(db_file))
    retriever.index_module("math", {
        "functions": [{"name": "math.sqrt", "signature": "math.sqrt(x: float) -> float", "doc": "Return square root."}]
    })

    result = runner.invoke(app, ["doc", "sqrt", "--db", str(db_file)])
    assert result.exit_code == 0
    assert "math.sqrt" in result.output


def test_cli_doc_command_missing_symbol(tmp_path):
    """Verify k doc command returns exit code 2 when symbol is not found."""
    db_file = tmp_path / "empty_docs.db"
    DocRetriever(db_path=str(db_file))
    result = runner.invoke(app, ["doc", "nonexistent_symbol_12345", "--db", str(db_file)])
    assert result.exit_code == 2
    assert "No documentation found" in result.output


def test_cli_map_command(tmp_path):
    """Verify k map command displays AST tree of workspace."""
    sample_py = tmp_path / "sample_service.py"
    sample_py.write_text("class TestService:\n    def execute(self): pass\n", encoding="utf-8")

    result = runner.invoke(app, ["map", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "TestService" in result.output


def test_cli_main_entrypoint_with_prompt(monkeypatch):
    """Verify running k with direct prompt option invokes execute_run."""
    monkeypatch.setattr("k_cli.cli.LLMDriver", MockFailingDriver)
    result = runner.invoke(app, ["--prompt", "Write a function"])
    assert result.exit_code == 0
    assert "GROUND-TRUTH VERIFIED" in result.output or "Verified" in result.output


def test_cli_ui_and_tui_command_help():
    """Verify both ui and tui commands are available in CLI."""
    res_ui = runner.invoke(app, ["ui", "--help"])
    assert res_ui.exit_code == 0
    assert "Textual workstation" in res_ui.output

    res_tui = runner.invoke(app, ["tui", "--help"])
    assert res_tui.exit_code == 0
    assert "Textual" in res_tui.output

