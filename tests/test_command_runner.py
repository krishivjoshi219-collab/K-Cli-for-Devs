"""
test_command_runner.py - Unit and Integration Tests for Local Command Execution Engine
(Google Antigravity Engine for K-CLI)
"""

import asyncio
import pytest
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.tools.command_runner import LocalCommandExecutor, CommandExecutionResult, global_command_executor


def test_command_runner_sync_echo():
    executor = LocalCommandExecutor()
    res = executor.execute("echo 'Google Antigravity Runner Active'")
    assert res.success is True
    assert res.exit_code == 0
    assert "Google Antigravity Runner Active" in res.stdout
    assert res.duration_sec >= 0.0


def test_command_runner_sync_failure():
    executor = LocalCommandExecutor()
    res = executor.execute("sh -c 'exit 42'")
    assert res.success is False
    assert res.exit_code == 42


def test_command_runner_cwd():
    executor = LocalCommandExecutor()
    res = executor.execute("pwd", cwd="/tmp")
    assert res.success is True
    assert "/tmp" in res.stdout


def test_command_runner_timeout():
    executor = LocalCommandExecutor()
    res = executor.execute("sleep 5", timeout=1)
    assert res.success is False
    assert res.exit_code == -1
    assert "timed out" in res.stderr.lower()


def test_command_runner_async():
    executor = LocalCommandExecutor()
    res = asyncio.run(executor.execute_async("echo 'Async Runner Active'"))
    assert res.success is True
    assert res.exit_code == 0
    assert "Async Runner Active" in res.stdout


def test_cli_exec_echo():
    runner = CliRunner()
    result = runner.invoke(app, ["exec", "echo Antigravity CLI Success"])
    assert result.exit_code == 0
    assert "Antigravity CLI Success" in result.stdout
