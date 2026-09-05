"""
test_sandbox.py - Comprehensive Unit & Integration Tests for Sovereign Sandbox Engine
Project Bankai Engine v1.0.0
"""

import os
import sys
import pytest
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from k_cli.core.sandbox import (
    ASTSecurityScanner,
    SandboxConfig,
    SandboxEngine,
    SandboxResult,
    SandboxTier,
    global_sandbox_engine,
)
from k_cli.tools.command_runner import LocalCommandExecutor


class TestASTSecurityScanner:
    """Tests for static AST security analysis."""

    def test_safe_code_passes(self):
        code = "def add(x, y):\n    return x + y\n"
        report = ASTSecurityScanner.scan_python_code(code)
        assert report.is_safe is True
        assert report.risk_level == "SAFE"
        assert len(report.violations) == 0

    def test_detect_destructive_rm_rf(self):
        code = "import os\ncmd = 'rm -rf /tmp/data'\nos.system(cmd)\n"
        report = ASTSecurityScanner.scan_python_code(code)
        assert report.is_safe is False
        assert report.risk_level == "CRITICAL"
        assert any("Destructive file system command" in v for v in report.violations)

    def test_detect_sensitive_path_reference(self):
        code = "with open('/etc/shadow', 'r') as f:\n    data = f.read()\n"
        report = ASTSecurityScanner.scan_python_code(code)
        assert report.is_safe is False
        assert report.risk_level == "CRITICAL"
        assert any("/etc/shadow" in v for v in report.violations)

    def test_syntax_error_handled_gracefully(self):
        code = "def broken(\n"
        report = ASTSecurityScanner.scan_python_code(code)
        assert report.is_safe is False
        assert report.risk_level == "HIGH"
        assert len(report.violations) > 0


class TestSecretScrubbing:
    """Tests for environment variable credential sanitization."""

    def test_scrubs_all_cloud_credentials(self):
        dirty_env = {
            "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE12345",
            "AWS_SECRET_ACCESS_KEY": "SECRET_KEY_ABCD",
            "OPENAI_API_KEY": "sk-proj-mock123",
            "ANTHROPIC_API_KEY": "sk-ant-mock123",
            "GEMINI_API_KEY": "AIzaSyMock",
            "GROQ_API_KEY": "gsk_mock",
            "GITHUB_TOKEN": "ghp_mock",
            "SAFE_PROJECT_DIR": "/home/k/project",
            "LANG": "en_US.UTF-8",
        }
        clean_env = SandboxEngine.scrub_environment(dirty_env)

        assert "AWS_ACCESS_KEY_ID" not in clean_env
        assert "AWS_SECRET_ACCESS_KEY" not in clean_env
        assert "OPENAI_API_KEY" not in clean_env
        assert "ANTHROPIC_API_KEY" not in clean_env
        assert "GEMINI_API_KEY" not in clean_env
        assert "GROQ_API_KEY" not in clean_env
        assert "GITHUB_TOKEN" not in clean_env

        assert clean_env.get("SAFE_PROJECT_DIR") == "/home/k/project"
        assert clean_env.get("LANG") == "en_US.UTF-8"
        assert clean_env.get("HOME") == "/tmp"


class TestSandboxEngineExecution:
    """Tests for sandbox execution and container isolation."""

    def test_basic_command_execution(self):
        res = global_sandbox_engine.execute(["echo", "K_CLI_SANDBOX_PASS"])
        assert res.success is True
        assert res.exit_code == 0
        assert "K_CLI_SANDBOX_PASS" in res.stdout
        assert res.duration_sec >= 0.0

    def test_python_code_execution_in_sandbox(self):
        code = (
            "import math\n"
            "print('COMPUTED_VAL:', math.factorial(5))\n"
        )
        res = global_sandbox_engine.run_python_code(code)
        assert res.success is True
        assert res.exit_code == 0
        assert "COMPUTED_VAL: 120" in res.stdout

    def test_timeout_enforcement(self):
        res = global_sandbox_engine.execute(["sleep", "5"], timeout=0.5)
        assert res.success is False
        assert res.exit_code == -1
        assert "Timeout" in res.stderr or "killed" in res.stderr

    def test_resolve_tier_hierarchy(self):
        tier_auto = global_sandbox_engine.resolve_tier("auto")
        assert tier_auto in (SandboxTier.BUBBLEWRAP, SandboxTier.NAMESPACES, SandboxTier.POSIX_RLIMIT)

        tier_posix = global_sandbox_engine.resolve_tier("posix")
        assert tier_posix == SandboxTier.POSIX_RLIMIT

        tier_off = global_sandbox_engine.resolve_tier("disabled")
        assert tier_off == SandboxTier.DISABLED

    def test_filesystem_read_only_protection(self):
        res = global_sandbox_engine.execute("touch /usr/kcli_exploit_probe 2>&1 || true")
        output = res.stdout + res.stderr
        assert "Read-only" in output or "Permission denied" in output

    def test_network_airgap_blocks_outbound_sockets(self):
        net_code = (
            "import socket\n"
            "try:\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.settimeout(0.5)\n"
            "    s.connect(('8.8.8.8', 53))\n"
            "    print('VULNERABLE_SOCKET_OPEN')\n"
            "except Exception as e:\n"
            "    print('AIRGAP_BLOCKED:', type(e).__name__)\n"
        )
        res = global_sandbox_engine.run_python_code(net_code)
        assert "AIRGAP_BLOCKED" in res.stdout
        assert "VULNERABLE_SOCKET_OPEN" not in res.stdout

    def test_diagnostics_and_self_test(self):
        diag = global_sandbox_engine.get_diagnostics()
        assert "virtualization_engine" in diag
        assert diag["default_memory_budget_mb"] == 1024
        assert diag["security_rating"] != ""

        st = global_sandbox_engine.self_test()
        assert st["overall_pass"] is True
        assert st["basic_execution"]["passed"] is True
        assert st["filesystem_protection"]["passed"] is True
        assert st["network_airgap"]["passed"] is True
        assert st["secret_scrubbing"]["passed"] is True


class TestCommandRunnerIntegration:
    """Tests that LocalCommandExecutor works seamlessly with sandbox."""

    def test_command_runner_with_sandbox(self):
        executor = LocalCommandExecutor()
        res = executor.execute("echo SANDBOX_INTEGRATED", sandbox=True)
        assert res.success is True
        assert res.exit_code == 0
        assert "SANDBOX_INTEGRATED" in res.stdout
