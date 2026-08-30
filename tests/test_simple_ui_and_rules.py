"""
tests/test_simple_ui_and_rules.py
Unit and integration tests for:
1. Tier 3 Simple REPL UI (k_cli.ui.simple_repl)
2. Custom Developer Instructions & Workspace Rules (.kclirules)
"""

import os
import pytest
from pathlib import Path
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.tools.rules import load_project_rules, create_default_rules_file, set_global_rules
from k_cli.ui.simple_repl import SimpleCyberCLI


@pytest.fixture
def runner():
    return CliRunner()


def test_rules_file_creation_and_loading(tmp_path):
    # 1. Create .kclirules template
    target = create_default_rules_file(workspace_dir=tmp_path, force=True)
    assert target.exists()
    assert target.name == ".kclirules"

    # 2. Load rules
    content = load_project_rules(workspace_dir=tmp_path)
    assert "Custom Developer Instructions" in content
    assert "AST verification" in content


def test_global_rules_setting_and_loading(tmp_path):
    rules_text = "Always prioritize asynchronous concurrency and test coverage."
    p = set_global_rules(rules_text)
    assert p.exists()


def test_cli_rules_init_and_get(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res_init = runner.invoke(app, ["rules", "init"])
    assert res_init.exit_code == 0
    assert "Initialized custom rules template" in res_init.output

    res_get = runner.invoke(app, ["rules", "get"])
    assert res_get.exit_code == 0
    assert "Custom Developer Instructions" in res_get.output


def test_simple_cyber_cli_initialization(tmp_path):
    cli = SimpleCyberCLI(workspace_dir=str(tmp_path), mock_mode=True)
    assert cli.mock_mode is True
    assert cli.session is not None
    assert cli.session.mouse_support is True
