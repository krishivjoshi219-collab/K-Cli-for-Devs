"""
test_tui_app_screens.py - Unit & Modal Tests for Flagship Hybrid KCliCyberWorkstation
Project Bankai Engine v1.0.0
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from k_cli.tui.tui_app import (
    KCliCyberWorkstation,
    CredentialsVaultModal,
    ConflictStudioModal,
    GitHubCenterModal,
    ModelHubModal,
    SecurityScannerModal,
)


def test_kcli_cyber_workstation_init():
    """Verifies that KCliCyberWorkstation initializes with title, sub_title and bindings."""
    app = KCliCyberWorkstation()
    assert app.TITLE == "K-CLI"
    assert "Agentic Coding Workstation" in app.SUB_TITLE
    assert len(app.BINDINGS) >= 5


def test_credentials_vault_modal_structure_and_labels():
    """Verifies CredentialsVaultModal widgets and status label resolution."""
    modal = CredentialsVaultModal()
    assert modal._get_status_label("NON_EXISTENT_KEY_12345") == "○ Missing"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaTestKey"}):
        assert modal._get_status_label("GEMINI_API_KEY") == "✔ Active"


def test_conflict_studio_modal():
    """Verifies ConflictStudioModal initialization and method signatures."""
    modal = ConflictStudioModal()
    assert hasattr(modal, "on_resolve")
    assert hasattr(modal, "on_accept")
    assert hasattr(modal, "on_verify")
    assert hasattr(modal, "on_close")


def test_github_center_modal():
    """Verifies GitHubCenterModal methods."""
    modal = GitHubCenterModal()
    assert hasattr(modal, "on_solve")
    assert hasattr(modal, "on_review")
    assert hasattr(modal, "on_release")
    assert hasattr(modal, "on_close")


def test_model_hub_modal():
    """Verifies ModelHubModal methods."""
    modal = ModelHubModal()
    assert hasattr(modal, "on_bench")
    assert hasattr(modal, "on_pull")
    assert hasattr(modal, "on_select")
    assert hasattr(modal, "on_close")


def test_security_scanner_modal():
    """Verifies SecurityScannerModal methods."""
    modal = SecurityScannerModal()
    assert hasattr(modal, "on_scan")
    assert hasattr(modal, "on_heal")
    assert hasattr(modal, "on_close")
