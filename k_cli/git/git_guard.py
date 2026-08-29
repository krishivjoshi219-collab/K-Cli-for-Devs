"""
git_guard.py - Git Safety Net, Automated Checkpoints & Rollback for K-CLI

Provides repository auto-initialization, shadow git checkpoints before patch application,
atomic commits on verified success, instant working-tree rollback on verification failure,
and interactive user confirmation ([Apply], [Reject], [Diff], [Auto-Fix]).
"""

import os
import subprocess
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class PatchConfirmationAction(str, Enum):
    """Actions available for interactive user patch confirmation."""
    APPLY = "APPLY"
    REJECT = "REJECT"
    DIFF = "DIFF"
    AUTO_FIX = "AUTO_FIX"


class GitGuard:
    """
    Git safety manager providing atomic commits, diff tracking, shadow checkpoints,
    automatic rollback for code modification workflows, and interactive patch review.
    """

    def __init__(self, repo_dir: Union[str, Path] = "."):
        """
        Initializes GitGuard targeting a repository workspace directory.

        Args:
            repo_dir: Path to the workspace / repository root directory.
        """
        self.repo_dir = Path(repo_dir).resolve()
        self._last_snapshot: Optional[str] = None
        self._last_checkpoint: Optional[str] = None
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        """Helper to run git commands in the repository directory with default identity fallback."""
        env = dict(os.environ)
        env.setdefault("GIT_AUTHOR_NAME", "K-CLI")
        env.setdefault("GIT_AUTHOR_EMAIL", "k-cli@local")
        env.setdefault("GIT_COMMITTER_NAME", "K-CLI")
        env.setdefault("GIT_COMMITTER_EMAIL", "k-cli@local")

        return subprocess.run(
            ["git"] + args,
            cwd=str(self.repo_dir),
            capture_output=True,
            text=True,
            env=env,
        )

    def is_git_repo(self) -> bool:
        """
        Checks whether the workspace directory is inside a valid git repository.

        Returns:
            True if valid git repository, False otherwise.
        """
        if not self.repo_dir.exists() or not self.repo_dir.is_dir():
            return False

        res = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return res.returncode == 0 and res.stdout.strip() == "true"

    def ensure_repo(self) -> bool:
        """
        Ensures the workspace is a valid git repository, running `git init` if necessary.

        Returns:
            True if repository is ready, False on failure.
        """
        if self.is_git_repo():
            return True

        try:
            self.repo_dir.mkdir(parents=True, exist_ok=True)
            res = self._run_git(["init"])
            if res.returncode != 0:
                return False

            # Configure local identity defaults if not already set
            self._run_git(["config", "user.name", "K-CLI"])
            self._run_git(["config", "user.email", "k-cli@local"])
            return True
        except Exception:
            return False

    def create_checkpoint(
        self,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Auto-creates a shadow git checkpoint before applying any surgical patch.
        Captures HEAD SHA, working tree diffs, staged changes, and untracked files.
        Registers a shadow ref under `refs/kcli/checkpoints/<id>`.

        Args:
            name: Optional custom checkpoint name or prefix.
            metadata: Optional additional metadata dictionary to store with the checkpoint.

        Returns:
            Checkpoint identifier string, or empty string in non-git environment.
        """
        if not self.is_git_repo():
            return ""

        res_head = self._run_git(["rev-parse", "HEAD"])
        head_sha = res_head.stdout.strip() if res_head.returncode == 0 else "EMPTY_REPO"

        ts = int(time.time())
        short_id = uuid.uuid4().hex[:8]
        prefix = f"ckpt_{name}" if name else "ckpt"
        checkpoint_id = f"{prefix}_{ts}_{short_id}"

        # Capture current working tree state
        res_status = self._run_git(["status", "--porcelain"])
        staged_diff = self.get_diff(cached=True)
        unstaged_diff = self.get_diff(cached=False)
        untracked = self.get_untracked_files()

        shadow_ref = None
        if head_sha != "EMPTY_REPO":
            shadow_ref = f"refs/kcli/checkpoints/{checkpoint_id}"
            # Update shadow ref to point to current HEAD commit
            self._run_git(["update-ref", shadow_ref, head_sha])

        record: Dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "head_sha": head_sha,
            "shadow_ref": shadow_ref,
            "timestamp": ts,
            "status_output": res_status.stdout if res_status.returncode == 0 else "",
            "staged_diff": staged_diff,
            "unstaged_diff": unstaged_diff,
            "untracked_files": untracked,
            "metadata": metadata or {},
        }

        self._checkpoints[checkpoint_id] = record
        self._last_checkpoint = checkpoint_id
        self._last_snapshot = checkpoint_id
        return checkpoint_id

    def create_snapshot(self) -> str:
        """
        Captures a snapshot token representing the current git HEAD and workspace status.
        Maintains backward compatibility while also registering a shadow checkpoint.

        Returns:
            Snapshot identifier string, or empty string in non-git environment.
        """
        if not self.is_git_repo():
            return ""

        res_head = self._run_git(["rev-parse", "HEAD"])
        head_sha = res_head.stdout.strip() if res_head.returncode == 0 else "EMPTY_REPO"

        res_status = self._run_git(["status", "--porcelain"])
        status_hash = str(hash(res_status.stdout))

        snapshot_id = f"snapshot_{head_sha[:10]}_{status_hash[:8]}"
        self._last_snapshot = snapshot_id
        # Also record checkpoint
        self.create_checkpoint(name=f"snap_{head_sha[:8]}")
        return snapshot_id

    def restore_checkpoint(
        self,
        checkpoint_id: Optional[str] = None,
        hard_reset: bool = True,
    ) -> bool:
        """
        Restores workspace to the exact state of a specified shadow checkpoint.

        Args:
            checkpoint_id: Identifier of the checkpoint to restore. Defaults to the latest checkpoint.
            hard_reset: If True, resets HEAD commit if new commits were made post-checkpoint.

        Returns:
            True if restoration succeeded, False otherwise.
        """
        if not self.is_git_repo():
            return False

        target_id = checkpoint_id or self._last_checkpoint
        ckpt = self._checkpoints.get(target_id) if target_id else None

        try:
            if ckpt and ckpt.get("head_sha") and ckpt["head_sha"] != "EMPTY_REPO":
                head_sha = ckpt["head_sha"]
                curr_head = self._run_git(["rev-parse", "HEAD"]).stdout.strip()
                if hard_reset and curr_head != head_sha:
                    self._run_git(["reset", "--hard", head_sha])
                else:
                    self._run_git(["reset", "HEAD"])
                    self._run_git(["restore", "."])
            else:
                self._run_git(["reset", "HEAD"])
                self._run_git(["restore", "."])

            # Remove untracked files and directories created after checkpoint
            self._run_git(["clean", "-fd"])
            return True
        except Exception:
            return False

    def list_checkpoints(self) -> List[str]:
        """Returns list of created checkpoint IDs in chronological order."""
        return list(self._checkpoints.keys())

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Returns checkpoint record dictionary or None if not found."""
        return self._checkpoints.get(checkpoint_id)

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Deletes a shadow checkpoint and cleans its ref."""
        if checkpoint_id in self._checkpoints:
            ckpt = self._checkpoints.pop(checkpoint_id)
            if ckpt.get("shadow_ref"):
                self._run_git(["update-ref", "-d", ckpt["shadow_ref"]])
            if self._last_checkpoint == checkpoint_id:
                self._last_checkpoint = list(self._checkpoints.keys())[-1] if self._checkpoints else None
            return True
        return False

    def commit_success(
        self,
        message: str,
        files: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Creates an atomic git commit with a semantic commit message on verified success.

        Args:
            message: Commit message (e.g. 'feat: implement quicksort').
            files: Specific file paths to stage and commit. If None, stages all changes (`-A`).

        Returns:
            New commit SHA if committed, or current HEAD SHA if clean, or None on failure.
        """
        if not self.is_git_repo():
            return None

        # Stage files
        if files:
            for f in files:
                add_res = self._run_git(["add", str(f)])
                if add_res.returncode != 0:
                    # File might have been deleted, try git rm / add -u
                    self._run_git(["add", "-u", str(f)])
        else:
            self._run_git(["add", "-A"])

        # Check if anything is staged
        diff_cached = self._run_git(["diff", "--cached", "--quiet"])
        if diff_cached.returncode == 0:
            # Nothing staged to commit; return current HEAD SHA if it exists
            head_res = self._run_git(["rev-parse", "HEAD"])
            return head_res.stdout.strip() if head_res.returncode == 0 else None

        # Commit staged changes
        commit_res = self._run_git(["commit", "-m", message])
        if commit_res.returncode != 0:
            return None

        # Retrieve and return new commit SHA
        head_res = self._run_git(["rev-parse", "HEAD"])
        return head_res.stdout.strip() if head_res.returncode == 0 else None

    def rollback(
        self,
        files: Optional[List[str]] = None,
        checkpoint_id: Optional[str] = None,
    ) -> bool:
        """
        Reverts working tree modifications and unstaged changes on verification failure.
        If checkpoint_id is provided, rolls back to that shadow checkpoint.

        Args:
            files: Specific list of files to restore. If None, restores entire working tree.
            checkpoint_id: Optional checkpoint ID to restore to.

        Returns:
            True if rollback succeeded, False if not a git repository or on error.
        """
        if not self.is_git_repo():
            return False

        if checkpoint_id:
            return self.restore_checkpoint(checkpoint_id)

        try:
            if files:
                for f in files:
                    # Unstage file if staged
                    self._run_git(["restore", "--staged", str(f)])
                    # Discard modifications in working tree
                    self._run_git(["restore", str(f)])
                    # If untracked new file, clean it
                    self._run_git(["clean", "-f", str(f)])
            else:
                # Unstage all staged changes
                self._run_git(["reset", "HEAD"])
                # Discard modifications in working tree
                self._run_git(["restore", "."])
                # Remove untracked files and directories
                self._run_git(["clean", "-fd"])

            return True
        except Exception:
            return False

    def get_diff(self, cached: bool = False, files: Optional[List[str]] = None) -> str:
        """
        Returns active git diff for the repository.

        Args:
            cached: If True, returns diff of staged changes (`--cached`).
                    If False, returns diff of unstaged working tree changes.
            files: Optional specific files to limit diff to.

        Returns:
            Diff output string, or empty string if clean or non-git environment.
        """
        if not self.is_git_repo():
            return ""

        args = ["diff", "--cached"] if cached else ["diff"]
        if files:
            args.append("--")
            args.extend([str(f) for f in files])

        res = self._run_git(args)
        return res.stdout if res.returncode == 0 else ""

    def get_untracked_files(self) -> List[str]:
        """Returns list of untracked files in the repository."""
        if not self.is_git_repo():
            return []
        res = self._run_git(["ls-files", "--others", "--exclude-standard"])
        if res.returncode == 0 and res.stdout.strip():
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return []

    def has_uncommitted_changes(self) -> bool:
        """Returns True if there are unstaged, staged, or untracked changes in the working tree."""
        if not self.is_git_repo():
            return False
        diff = self.get_diff(cached=False)
        cached_diff = self.get_diff(cached=True)
        untracked = self.get_untracked_files()
        return bool(diff.strip() or cached_diff.strip() or untracked)

    def prompt_confirmation(
        self,
        diff_text: Optional[str] = None,
        input_fn: Optional[Callable[[str], str]] = None,
        display_fn: Optional[Callable[[str], None]] = None,
        prompt_text: Optional[str] = None,
    ) -> PatchConfirmationAction:
        """
        Interactive user confirmation prompting with [Apply], [Reject], [Diff], [Auto-Fix].

        Args:
            diff_text: Optional git diff string to display when [Diff] is selected.
            input_fn: Callable for getting user input (defaults to builtin `input`).
            display_fn: Callable for displaying messages (defaults to builtin `print`).
            prompt_text: Custom prompt message.

        Returns:
            Selected PatchConfirmationAction (APPLY, REJECT, DIFF, or AUTO_FIX).
        """
        _input = input_fn or input
        _display = display_fn or print
        active_diff = diff_text if diff_text is not None else self.get_diff()

        msg = prompt_text or "Proposed changes ready. Options: [Apply] (a), [Reject] (r), [Diff] (d), [Auto-Fix] (f)"

        while True:
            try:
                choice = _input(f"{msg}\nSelect action: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return PatchConfirmationAction.REJECT

            if choice in ("apply", "a", "1", "[apply]", "y", "yes"):
                return PatchConfirmationAction.APPLY
            elif choice in ("reject", "r", "2", "[reject]", "n", "no", "cancel"):
                return PatchConfirmationAction.REJECT
            elif choice in ("diff", "d", "3", "[diff]"):
                if active_diff.strip():
                    _display(f"\n--- Proposed Diff ---\n{active_diff}\n---------------------")
                else:
                    _display("\n[Diff]: No changes detected in working tree.")
                continue
            elif choice in ("auto-fix", "autofix", "fix", "f", "4", "[auto-fix]"):
                return PatchConfirmationAction.AUTO_FIX
            else:
                _display(f"Invalid option '{choice}'. Please choose [Apply], [Reject], [Diff], or [Auto-Fix].")


def confirm_patch_action(
    diff_text: Optional[str] = None,
    input_fn: Optional[Callable[[str], str]] = None,
    display_fn: Optional[Callable[[str], None]] = None,
) -> PatchConfirmationAction:
    """Helper shortcut function for interactive patch confirmation."""
    guard = GitGuard()
    return guard.prompt_confirmation(diff_text=diff_text, input_fn=input_fn, display_fn=display_fn)
