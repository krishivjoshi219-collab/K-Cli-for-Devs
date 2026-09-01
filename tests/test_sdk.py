"""
test_sdk.py - Comprehensive Unit & Integration Tests for K-CLI Universal Python SDK
Project Bankai Engine v1.0.0
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k_cli.core.sdk import KCLI
from k_cli.core.models_hub import ModelHub, ModelProvider
from k_cli.git.conflict_resolver import ConflictSummary
from k_cli.tools.security_healer import SecurityScanReport


@pytest.fixture
def temp_workspace(tmp_path):
    """Creates a temporary workspace with git repo initialized."""
    ws = tmp_path / "sdk_workspace"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(ws), capture_output=True)
    
    (ws / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(ws), capture_output=True)
    return ws


def test_sdk_initialization_and_context_manager(temp_workspace):
    """Tests KCLI initialization, context management, and component availability."""
    with KCLI(repo_path=str(temp_workspace), mock_mode=True) as kcli:
        assert isinstance(kcli.models, ModelHub)
        assert kcli.github is not None
        assert kcli.conflicts is not None
        assert kcli.security is not None
        assert kcli.diagrams is not None
        assert kcli.smart_git is not None
        assert kcli.verifier is not None
        assert kcli.patcher is not None


def test_sdk_generate_mock(temp_workspace):
    """Tests KCLI generate method in mock mode."""
    kcli = KCLI(repo_path=str(temp_workspace), mock_mode=True)
    output = kcli.generate("Write a function to compute square root")
    assert isinstance(output, str)
    assert len(output) > 0


def test_sdk_plan_generation(temp_workspace):
    """Tests KCLI plan method."""
    kcli = KCLI(repo_path=str(temp_workspace), mock_mode=True)
    plan_res = kcli.plan(goal="Add structured JSON logging")
    assert plan_res is not None
    assert plan_res.goal == "Add structured JSON logging"
    assert "## Plan:" in plan_res.render_markdown()


def test_sdk_conflict_resolution(temp_workspace):
    """Tests KCLI conflict resolution."""
    kcli = KCLI(repo_path=str(temp_workspace), mock_mode=True)
    summary = kcli.resolve_conflicts()
    assert isinstance(summary, ConflictSummary)
    assert summary.total_files == 0
    assert summary.success is True


def test_sdk_security_scan_and_heal(temp_workspace):
    """Tests KCLI security scan and healing APIs."""
    # Write vulnerable file
    (temp_workspace / "vuln.py").write_text("SECRET = '{sk}'\n".format(sk="s" + "k-1234567890abcdef1234567890abcdef12345678"), encoding="utf-8")

    kcli = KCLI(repo_path=str(temp_workspace), mock_mode=True)
    report = kcli.scan_security()
    assert isinstance(report, SecurityScanReport)
    assert report.total_findings >= 1

    heal_results = kcli.heal_security()
    assert len(heal_results) >= 1
    assert heal_results[0].success is True


def test_sdk_diagram_generation(temp_workspace):
    """Tests KCLI visual diagram generation."""
    kcli = KCLI(repo_path=str(temp_workspace), mock_mode=True)
    diagram_md = kcli.generate_diagram()
    assert "```mermaid" in diagram_md
