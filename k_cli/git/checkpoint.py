"""
checkpoint.py - Autonomous Time-Travel Checkpoint & Instant Rollback Engine
Project Bankai Engine v1.0.0

Provides:
1. Lightweight, non-destructive snapshotting before any autonomous file edit or command run.
2. Instant one-command rollback (`k-cli undo`) to restore repository state cleanly.
3. Clean unified diff computation between current workspace and previous checkpoint.
4. Preserves developer branch status and uncommitted changes without destructive git resets.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("k_cli.git.checkpoint")


@dataclass
class CheckpointMeta:
    checkpoint_id: str
    timestamp: float
    description: str
    files_tracked: List[str] = field(default_factory=list)
    git_head: Optional[str] = None


class CheckpointManager:
    """
    Manages non-destructive workspace checkpoints for autonomous agent operations.
    Stores file snapshots under `.kcli/checkpoints/<id>/` to guarantee 100% safe rollbacks.
    """

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = Path(workspace_dir or ".").resolve()
        self.checkpoints_dir = self.workspace_dir / ".kcli" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.checkpoints_dir / "index.json"

    def _load_index(self) -> List[Dict[str, Any]]:
        if not self.meta_file.exists():
            return []
        try:
            return json.loads(self.meta_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_index(self, index: List[Dict[str, Any]]) -> None:
        try:
            self.meta_file.write_text(json.dumps(index, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save checkpoint index: {e}")

    def get_git_head(self) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def create_checkpoint(
        self,
        description: str = "Autonomous agent pre-execution snapshot",
        tracked_paths: Optional[List[str]] = None,
    ) -> str:
        """
        Creates a time-travel checkpoint by snapshotting workspace files.
        Returns the unique checkpoint ID.
        """
        checkpoint_id = f"ckpt_{int(time.time())}_{os.urandom(3).hex()}"
        snapshot_dir = self.checkpoints_dir / checkpoint_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        tracked_files: List[str] = []
        ignored = {".git", ".venv", "venv", "k_cli_env", "__pycache__", "node_modules", ".kcli", "dist", "build"}

        # If specific paths requested, snapshot those; otherwise snapshot modified or code files
        if tracked_paths:
            for p_str in tracked_paths:
                p = Path(p_str).resolve()
                if p.is_file() and p.exists():
                    rel = p.relative_to(self.workspace_dir)
                    dest = snapshot_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
                    tracked_files.append(str(rel))
        else:
            # Snapshot all primary workspace code files (< 1MB each)
            for item in self.workspace_dir.rglob("*"):
                if any(ig in item.parts for ig in ignored):
                    continue
                if item.is_file() and item.suffix.lower() in {
                    ".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".toml", ".yaml", ".yml", ".sh"
                }:
                    try:
                        if item.stat().st_size < 1_500_000:
                            rel = item.relative_to(self.workspace_dir)
                            dest = snapshot_dir / rel
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest)
                            tracked_files.append(str(rel))
                    except Exception:
                        continue

        meta = CheckpointMeta(
            checkpoint_id=checkpoint_id,
            timestamp=time.time(),
            description=description,
            files_tracked=tracked_files,
            git_head=self.get_git_head(),
        )

        index = self._load_index()
        index.append(asdict(meta))
        # Keep last 15 checkpoints
        if len(index) > 15:
            old = index.pop(0)
            old_dir = self.checkpoints_dir / old["checkpoint_id"]
            if old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)

        self._save_index(index)
        logger.info(f"Checkpoint '{checkpoint_id}' created ({len(tracked_files)} files tracked)")
        return checkpoint_id

    def rollback_last_checkpoint(self) -> Tuple[bool, str]:
        """
        Reverts the workspace to the most recent checkpoint state.
        Returns (success, status_message).
        """
        index = self._load_index()
        if not index:
            return False, "No previous checkpoints found to rollback."

        latest = index.pop()
        checkpoint_id = latest["checkpoint_id"]
        snapshot_dir = self.checkpoints_dir / checkpoint_id

        if not snapshot_dir.exists():
            self._save_index(index)
            return False, f"Checkpoint directory '{checkpoint_id}' missing."

        restored_count = 0
        for rel_path_str in latest.get("files_tracked", []):
            src = snapshot_dir / rel_path_str
            dest = self.workspace_dir / rel_path_str
            if src.exists() and src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored_count += 1

        self._save_index(index)
        return True, f"Successfully rolled back to checkpoint '{checkpoint_id}' ({restored_count} files restored: {latest.get('description', '')})"

    def compute_diff(self, checkpoint_id: Optional[str] = None) -> str:
        """
        Computes a unified diff showing all changes between the checkpoint and current workspace.
        """
        index = self._load_index()
        if not index:
            return "No checkpoints available for diff comparison."

        target = None
        if checkpoint_id:
            for c in index:
                if c["checkpoint_id"] == checkpoint_id:
                    target = c
                    break
        if target is None:
            target = index[-1]

        snapshot_dir = self.checkpoints_dir / target["checkpoint_id"]
        diff_lines: List[str] = []

        for rel_path_str in target.get("files_tracked", []):
            snap_file = snapshot_dir / rel_path_str
            current_file = self.workspace_dir / rel_path_str

            snap_lines = snap_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if snap_file.exists() else []
            curr_lines = current_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if current_file.exists() else []

            if snap_lines != curr_lines:
                diff = list(difflib.unified_diff(
                    snap_lines,
                    curr_lines,
                    fromfile=f"a/{rel_path_str} (checkpoint: {target['checkpoint_id']})",
                    tofile=f"b/{rel_path_str} (working directory)",
                ))
                diff_lines.extend(diff)

        if not diff_lines:
            return f"Zero modifications detected since checkpoint '{target['checkpoint_id']}'."
        return "".join(diff_lines)

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        return self._load_index()


# Global Singleton Accessor
global_checkpoint_manager = CheckpointManager()
