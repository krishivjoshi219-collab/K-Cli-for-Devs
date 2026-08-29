"""
test_credentials.py - Unit test suite for CredentialsManager & Keys CLI
"""

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from k_cli.core.credentials import CredentialsManager, SUPPORTED_KEYS


def test_credentials_manager_set_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(CredentialsManager, "CRED_DIR", tmp_path / ".kcli")
    monkeypatch.setattr(CredentialsManager, "ENV_FILE", tmp_path / ".kcli" / "credentials.env")
    monkeypatch.setattr(CredentialsManager, "JSON_FILE", tmp_path / ".kcli" / "credentials.json")

    CredentialsManager.set_key("GEMINI_API_KEY", "AIzaSy_fake_test_key_12345")
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSy_fake_test_key_12345"

    # Verify persistent files
    assert (tmp_path / ".kcli" / "credentials.env").exists()
    assert "GEMINI_API_KEY=AIzaSy_fake_test_key_12345" in (tmp_path / ".kcli" / "credentials.env").read_text()

    # Clear env and reload
    os.environ.pop("GEMINI_API_KEY", None)
    loaded = CredentialsManager.load_all_credentials()
    assert loaded.get("GEMINI_API_KEY") == "AIzaSy_fake_test_key_12345"
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSy_fake_test_key_12345"


def test_credentials_get_key_statuses():
    statuses = CredentialsManager.get_key_statuses()
    assert isinstance(statuses, list)
    assert len(statuses) == len(SUPPORTED_KEYS)
    keys_list = [s["key"] for s in statuses]
    assert "GEMINI_API_KEY" in keys_list
    assert "GITHUB_TOKEN" in keys_list


def test_credentials_test_key_connectivity():
    ok, msg = CredentialsManager.test_key_connectivity("MOCK_KEY")
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
