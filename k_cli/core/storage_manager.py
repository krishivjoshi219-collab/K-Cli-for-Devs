"""
storage_manager.py - Persistent Local Storage & Session Resumption Engine for K-CLI
Project Bankai v1.0.0 — Built for AWS "Agents for Humans" Hackathon
Developer: Krishiv Joshi (@krishivjoshi)

Manages persistent local storage in ~/.kcli/:
- Multi-turn conversation sessions & checkpoints (~/.kcli/sessions/)
- API Keys & credentials (~/.kcli/credentials.env)
- Developer preferences & default models (~/.kcli/preferences.json)
- Enables 1-flag session continuation: `k-cli -c` or `k-cli --continue`
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME_DIR = Path.home()
STORAGE_DIR = Path(os.getenv("KCLI_HOME", HOME_DIR / ".kcli")).resolve()
SESSIONS_DIR = STORAGE_DIR / "sessions"
CREDS_FILE = STORAGE_DIR / "credentials.env"
PREFS_FILE = STORAGE_DIR / "preferences.json"
LATEST_SESSION_FILE = SESSIONS_DIR / "latest_session.json"
AUDIT_JOURNAL_FILE = STORAGE_DIR / "audit_journal.jsonl"


@dataclass
class SessionTurn:
    prompt: str
    response: str
    code: str = ""
    success: bool = True
    attempts: int = 1
    patches_applied: bool = False
    timestamp: float = field(default_factory=time.time)
    routed_model: str = "auto"
    persona: str = "CODER"


@dataclass
class SessionCheckpoint:
    session_id: str
    workspace_dir: str
    active_model: str
    active_persona: str
    context_files: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    git_branch: str = "main"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    total_tokens: int = 0
    total_cost_saved: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionCheckpoint:
        return cls(
            session_id=data.get("session_id", f"session_{int(time.time())}"),
            workspace_dir=data.get("workspace_dir", "."),
            active_model=data.get("active_model", "qwen2.5-coder:1.5b"),
            active_persona=data.get("active_persona", "Fullstack AI Systems Engineer"),
            context_files=data.get("context_files", []),
            history=data.get("history", []),
            git_branch=data.get("git_branch", "main"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            total_tokens=data.get("total_tokens", 0),
            total_cost_saved=data.get("total_cost_saved", 0.0),
        )


class LocalStorageManager:
    """Enterprise-grade local storage engine for persistent session state and zero-config resume."""

    @classmethod
    def ensure_dirs(cls) -> None:
        """Ensures ~/.kcli and ~/.kcli/sessions directories exist with proper permissions."""
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def save_session(
        cls,
        session_id: str,
        workspace_dir: str,
        active_model: str,
        active_persona: str,
        context_files: List[str],
        history: List[Dict[str, Any]],
        git_branch: str = "main",
        total_tokens: int = 0,
        total_cost_saved: float = 0.0,
    ) -> Path:
        """Persists a session checkpoint to ~/.kcli/sessions/ and updates latest_session.json."""
        cls.ensure_dirs()
        checkpoint = SessionCheckpoint(
            session_id=session_id,
            workspace_dir=str(Path(workspace_dir).resolve()),
            active_model=active_model,
            active_persona=active_persona,
            context_files=context_files,
            history=history,
            git_branch=git_branch,
            updated_at=time.time(),
            total_tokens=total_tokens,
            total_cost_saved=total_cost_saved,
        )

        # Write timestamped session file
        session_file = SESSIONS_DIR / f"{session_id}.json"
        data_json = json.dumps(checkpoint.to_dict(), indent=2)
        session_file.write_text(data_json, encoding="utf-8")

        # Write pointer to latest session
        LATEST_SESSION_FILE.write_text(data_json, encoding="utf-8")

        return session_file

    @classmethod
    def load_latest_session(cls) -> Optional[SessionCheckpoint]:
        """Loads the most recently saved session checkpoint for -c / --continue flag."""
        cls.ensure_dirs()
        if not LATEST_SESSION_FILE.exists():
            # Check if any session files exist in sessions dir
            session_files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not session_files:
                return None
            target_file = session_files[0]
        else:
            target_file = LATEST_SESSION_FILE

        try:
            data = json.loads(target_file.read_text(encoding="utf-8"))
            return SessionCheckpoint.from_dict(data)
        except Exception:
            return None

    @classmethod
    def list_saved_sessions(cls) -> List[Dict[str, Any]]:
        """Returns metadata for all persisted sessions."""
        cls.ensure_dirs()
        results = []
        for p in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.name == "latest_session.json":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append({
                    "session_id": data.get("session_id", p.stem),
                    "file": str(p),
                    "model": data.get("active_model", "unknown"),
                    "turns": len(data.get("history", [])),
                    "workspace": data.get("workspace_dir", "."),
                    "updated_at": data.get("updated_at", p.stat().st_mtime),
                })
            except Exception:
                continue
        return results

    @classmethod
    def record_activity(cls, event_type: str, details: Dict[str, Any]) -> None:
        """Appends an immutable event record to ~/.kcli/audit_journal.jsonl."""
        cls.ensure_dirs()
        record = {
            "timestamp": time.time(),
            "event": event_type,
            **details,
        }
        with open(AUDIT_JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
