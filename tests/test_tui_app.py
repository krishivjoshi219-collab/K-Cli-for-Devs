"""
test_tui_app.py - Tests for KCliCyberWorkstation (Textual 8.x)
Project Bankai Engine v1.0.0
"""

import os
from unittest.mock import patch
import pytest

from k_cli.tui.tui_app import (
    KCliCyberWorkstation,
    CredentialsVaultModal,
    ConflictStudioModal,
    GitHubCenterModal,
    ModelHubModal,
    SecurityScannerModal,
)


def test_workstation_title():
    app = KCliCyberWorkstation()
    assert app.TITLE == "K-CLI"


def test_workstation_subtitle():
    app = KCliCyberWorkstation()
    assert "Agentic Coding Workstation" in app.SUB_TITLE


def test_workstation_has_bindings():
    app = KCliCyberWorkstation()
    keys = [b.key for b in app.BINDINGS]
    assert "ctrl+a" in keys
    assert "ctrl+k" in keys
    assert "ctrl+g" in keys
    assert "ctrl+m" in keys
    assert "ctrl+s" in keys
    assert "ctrl+q" in keys


def test_credentials_vault_missing_key():
    modal = CredentialsVaultModal()
    assert modal._get_status_label("NONEXISTENT_KEY_ZCVX") == "○ Missing"


def test_credentials_vault_active_key():
    modal = CredentialsVaultModal()
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
        assert modal._get_status_label("OPENAI_API_KEY") == "✔ Active"


def test_credentials_vault_modal_has_save_method():
    modal = CredentialsVaultModal()
    assert hasattr(modal, "action_save_keys")


def test_credentials_vault_modal_has_test_method():
    modal = CredentialsVaultModal()
    assert hasattr(modal, "action_test_connections")


def test_conflict_studio_has_callbacks():
    modal = ConflictStudioModal()
    assert hasattr(modal, "on_resolve")
    assert hasattr(modal, "on_accept")
    assert hasattr(modal, "on_verify")
    assert hasattr(modal, "on_close")


def test_github_center_has_callbacks():
    modal = GitHubCenterModal()
    assert hasattr(modal, "on_solve")
    assert hasattr(modal, "on_review")
    assert hasattr(modal, "on_release")
    assert hasattr(modal, "on_close")


def test_model_hub_has_callbacks():
    modal = ModelHubModal()
    assert hasattr(modal, "on_bench")
    assert hasattr(modal, "on_pull")
    assert hasattr(modal, "on_select")
    assert hasattr(modal, "on_close")


def test_security_scanner_has_callbacks():
    modal = SecurityScannerModal()
    assert hasattr(modal, "on_scan")
    assert hasattr(modal, "on_heal")
    assert hasattr(modal, "on_close")
