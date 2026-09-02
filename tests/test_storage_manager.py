"""
test_storage_manager.py - Unit tests for persistent local storage & -c session resumption.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from k_cli.core.storage_manager import LocalStorageManager, SessionCheckpoint
from k_cli.core.session import SessionManager


def test_storage_manager_save_and_load(tmp_path):
    with patch("k_cli.core.storage_manager.STORAGE_DIR", tmp_path), \
         patch("k_cli.core.storage_manager.SESSIONS_DIR", tmp_path / "sessions"), \
         patch("k_cli.core.storage_manager.LATEST_SESSION_FILE", tmp_path / "sessions" / "latest_session.json"):
        
        saved_file = LocalStorageManager.save_session(
            session_id="test_session_123",
            workspace_dir=str(tmp_path),
            active_model="krishivjoshi/bankai-10b",
            active_persona="Fullstack AI Systems Engineer",
            context_files=["src/main.py"],
            history=[
                {"prompt": "Write a binary search", "response": "def binary_search()...", "success": True}
            ],
            git_branch="feat/storage",
            total_tokens=420,
            total_cost_saved=0.015,
        )

        assert saved_file.exists()
        assert (tmp_path / "sessions" / "latest_session.json").exists()

        loaded = LocalStorageManager.load_latest_session()
        assert loaded is not None
        assert loaded.session_id == "test_session_123"
        assert loaded.active_model == "krishivjoshi/bankai-10b"
        assert len(loaded.history) == 1
        assert loaded.context_files == ["src/main.py"]
        assert loaded.git_branch == "feat/storage"


def test_session_manager_resume(tmp_path):
    with patch("k_cli.core.storage_manager.STORAGE_DIR", tmp_path), \
         patch("k_cli.core.storage_manager.SESSIONS_DIR", tmp_path / "sessions"), \
         patch("k_cli.core.storage_manager.LATEST_SESSION_FILE", tmp_path / "sessions" / "latest_session.json"):
        
        LocalStorageManager.save_session(
            session_id="resume_test_456",
            workspace_dir=str(tmp_path),
            active_model="gemini-2.0-flash",
            active_persona="CODER",
            context_files=["app.py"],
            history=[
                {"prompt": "hello", "response": "world", "code": "", "success": True, "attempts": 1, "patches_applied": False}
            ],
            git_branch="main",
        )

        session = SessionManager.load_latest(workspace_dir=str(tmp_path), mock_mode=True)
        assert session is not None
        assert session.model_name == "gemini-2.0-flash"
        assert len(session.history) == 1
        assert session.context_files == ["app.py"]
