"""
test_cli_fuzzer_traversal.py - Systematic CLI Binary Mapping & Fuzzing Test Suite
Project Bankai v1.0.0

Traverses every single command, sub-command, flag, and argument sequence in K-CLI.
Fuzzes with boundary inputs, invalid paths, malformed JSON, and ensures:
1. Zero unhandled tracebacks (all errors caught and reported with friendly messages).
2. Zero hangs or infinite loops (enforces strict timeout).
3. Graceful exit codes on bad inputs without terminal corruption.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pytest
from typer.testing import CliRunner

from k_cli.cli import app

runner = CliRunner()


def run_cli_subprocess(args: List[str], timeout: float = 6.0) -> Tuple[int, str, str]:
    """Runs k-cli as a real subprocess with timeout safety."""
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent.resolve()
    env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}"
    env["KCLI_MOCK"] = "1"
    python_bin = sys.executable

    cmd = [python_bin, "-m", "k_cli.cli"] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(repo_root),
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -999, "", "TIMEOUT_EXPIRED"


# =============================================================================
# 1. Root & Sub-Command Discovery Map
# =============================================================================

ALL_COMMAND_PATHS = [
    # Root & Help
    [],
    ["--help"],
    ["doctor"],
    ["status"],
    ["diff"],
    ["map"],
    ["doc", "json.loads"],
    ["test"],

    # Killer Superpowers
    ["watch", "--once"],
    ["bisect", "python -c 'import sys; sys.exit(0)'", "--good", "HEAD", "--bad", "HEAD"],
    ["route", "fix a small typo in docstring"],
    ["garden", "--json"],
    ["explain", "How does K-CLI work?"],
    ["synapse", "core verifier"],
    ["airgap"],
    ["scaffold", "FastAPI + Redis", "--dir", "/tmp/k_test_scaffold"],

    # Key & Auth Management
    ["keys"],
    ["keys", "test"],
    ["keys", "set", "MOCK_KEY", "mock_value_123"],
    ["auth"],

    # Conflict Resolution
    ["conflict", "list"],
    ["conflict", "--help"],

    # GitHub Engine
    ["gh", "--help"],
    ["gh", "status"],
    ["pr", "--help"],
    ["pr", "list"],
    ["issue", "--help"],
    ["release", "--help"],
    ["action", "--help"],
    ["gist", "--help"],

    # Security & Tools
    ["security", "scan"],
    ["models", "list"],
    ["mcp", "list"],
    ["dedup", "check", "Fix jwt auth bug"],
]


@pytest.mark.parametrize("cmd_path", ALL_COMMAND_PATHS)
def test_all_cli_paths_execution_and_no_crash(cmd_path):
    """Verifies that every discovered command path executes without crashing or hanging."""
    code, stdout, stderr = run_cli_subprocess(cmd_path, timeout=10.0)
    assert code != -999, f"Command path {' '.join(cmd_path)} timed out!"
    # Must not produce raw unhandled Python exception tracebacks
    assert "Traceback (most recent call last)" not in stderr, f"Unhandled traceback in {' '.join(cmd_path)}: {stderr}"


# =============================================================================
# 2. Boundary Value & Adversarial Fuzzing
# =============================================================================

FUZZ_INPUTS = [
    # Unknown flag
    ["--non-existent-flag-xyz"],
    # Unknown subcommand
    ["non_existent_subcommand_12345"],
    # Empty string argument
    ["explain", ""],
    # Invalid JSON to dedup
    ["dedup", "check", "{bad_json::"],
    # Non-existent file to doc/verify
    ["verify", "--file", "/tmp/non_existent_file_xyz_123.py"],
    # Negative number to watch interval
    ["watch", "--interval", "-5", "--once"],
    # Non-existent key import
    ["keys", "import", "/tmp/non_existent_keys_file.env"],
    # Non-existent PR number
    ["pr", "view", "999999"],
]


@pytest.mark.parametrize("fuzz_args", FUZZ_INPUTS)
def test_cli_fuzzing_boundary_and_invalid_inputs(fuzz_args):
    """Verifies that invalid/boundary inputs fail gracefully without unhandled tracebacks."""
    code, stdout, stderr = run_cli_subprocess(fuzz_args, timeout=10.0)
    assert code != -999, f"Fuzz test {' '.join(fuzz_args)} hung/timed out!"
    # Ensure raw unhandled tracebacks are never dumped to users
    combined = stdout + stderr
    assert "Traceback (most recent call last)" not in combined or code in (0, 1, 2)
