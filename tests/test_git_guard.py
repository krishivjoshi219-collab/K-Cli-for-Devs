"""
test_git_guard.py - Unit and Integration Tests for Git Safety Net (GitGuard)
"""

import subprocess
from pathlib import Path
import pytest

from k_cli.git.git_guard import GitGuard


@pytest.fixture
def initialized_git_dir(tmp_path: Path) -> Path:
    """Fixture providing an initialized git repository with initial commit."""
    repo = tmp_path / "git_test_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo, check=True, capture_output=True)

    init_file = repo / "hello.py"
    init_file.write_text("print('hello world')\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


class TestGitGuardRepositoryManagement:
    """Tests for GitGuard repo discovery and auto-initialization."""

    def test_is_git_repo_true(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        assert guard.is_git_repo() is True

    def test_is_git_repo_false_on_plain_dir(self, tmp_path: Path):
        plain = tmp_path / "plain_folder"
        plain.mkdir()
        guard = GitGuard(repo_dir=str(plain))
        assert guard.is_git_repo() is False

    def test_is_git_repo_false_on_nonexistent_dir(self, tmp_path: Path):
        ghost = tmp_path / "ghost_folder"
        guard = GitGuard(repo_dir=str(ghost))
        assert guard.is_git_repo() is False

    def test_ensure_repo_initializes_plain_dir(self, tmp_path: Path):
        new_repo = tmp_path / "new_repo"
        new_repo.mkdir()
        guard = GitGuard(repo_dir=str(new_repo))
        assert guard.is_git_repo() is False

        ensured = guard.ensure_repo()
        assert ensured is True
        assert guard.is_git_repo() is True
        assert (new_repo / ".git").exists()

    def test_ensure_repo_idempotent_on_existing_repo(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        assert guard.ensure_repo() is True
        assert guard.is_git_repo() is True


class TestGitGuardSnapshotsAndCommits:
    """Tests for GitGuard snapshots, atomic commits, and diff tracking."""

    def test_create_snapshot_valid_repo(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        snapshot = guard.create_snapshot()
        assert isinstance(snapshot, str)
        assert len(snapshot) > 0
        assert "snapshot_" in snapshot

    def test_create_snapshot_non_git_returns_empty(self, tmp_path: Path):
        plain = tmp_path / "non_git"
        plain.mkdir()
        guard = GitGuard(repo_dir=str(plain))
        assert guard.create_snapshot() == ""

    def test_commit_success_stages_and_commits_all(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        feature = initialized_git_dir / "feature.py"
        feature.write_text("def feat(): return 1\n", encoding="utf-8")

        commit_sha = guard.commit_success("feat: add new feature")
        assert commit_sha is not None
        assert len(commit_sha) == 40
        assert guard.get_diff() == ""

    def test_commit_success_specific_files(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        f1 = initialized_git_dir / "f1.py"
        f2 = initialized_git_dir / "f2.py"
        f1.write_text("a = 1\n", encoding="utf-8")
        f2.write_text("b = 2\n", encoding="utf-8")

        commit_sha = guard.commit_success("feat: add f1 only", files=["f1.py"])
        assert commit_sha is not None
        # f2 is untracked / uncommitted
        diff = guard.get_diff()
        assert "f1.py" not in diff

    def test_commit_success_clean_working_tree_returns_head(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        head_sha = guard.commit_success("chore: nothing to commit")
        assert head_sha is not None
        assert len(head_sha) == 40

    def test_commit_success_non_git_returns_none(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        guard = GitGuard(repo_dir=str(plain))
        assert guard.commit_success("feat: test") is None


class TestGitGuardRollbackAndDiff:
    """Tests for GitGuard rollback mechanisms and active diff reporting."""

    def test_get_diff_tracked_modifications(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        assert guard.get_diff() == ""

        hello = initialized_git_dir / "hello.py"
        hello.write_text("print('corrupted line')\n", encoding="utf-8")

        diff = guard.get_diff()
        assert "corrupted line" in diff
        assert "hello.py" in diff

    def test_get_diff_cached_changes(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        hello.write_text("print('staged edit')\n", encoding="utf-8")
        subprocess.run(["git", "add", "hello.py"], cwd=initialized_git_dir, check=True)

        cached_diff = guard.get_diff(cached=True)
        assert "staged edit" in cached_diff

    def test_rollback_restores_tracked_files(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        orig_content = hello.read_text(encoding="utf-8")

        hello.write_text("INVALID BROKEN STATE\n", encoding="utf-8")
        assert guard.get_diff() != ""

        rolled_back = guard.rollback()
        assert rolled_back is True
        assert hello.read_text(encoding="utf-8") == orig_content
        assert guard.get_diff() == ""

    def test_rollback_specific_files(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        orig_hello = hello.read_text(encoding="utf-8")

        second = initialized_git_dir / "second.py"
        second.write_text("x = 100\n", encoding="utf-8")
        guard.commit_success("chore: add second.py", files=["second.py"])
        orig_second = second.read_text(encoding="utf-8")

        # Corrupt both
        hello.write_text("# corrupt hello\n", encoding="utf-8")
        second.write_text("# corrupt second\n", encoding="utf-8")

        # Rollback only hello.py
        guard.rollback(files=["hello.py"])
        assert hello.read_text(encoding="utf-8") == orig_hello
        assert second.read_text(encoding="utf-8") == "# corrupt second\n"

    def test_rollback_missing_file_handled_safely(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        # Should not raise exception
        assert guard.rollback(files=["ghost_nonexistent_file.py"]) is True

    def test_rollback_non_git_returns_false(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        guard = GitGuard(repo_dir=str(plain))
        assert guard.rollback() is False


class TestGitGuardShadowCheckpoints:
    """Tests for shadow git checkpoints, listing, restoration, and deletion."""

    def test_create_checkpoint_unique_and_recorded(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        ckpt1 = guard.create_checkpoint()
        assert ckpt1.startswith("ckpt_")
        assert ckpt1 in guard.list_checkpoints()

        ckpt2 = guard.create_checkpoint(name="custom")
        assert "custom" in ckpt2
        assert ckpt2 != ckpt1
        assert len(guard.list_checkpoints()) == 2

    def test_create_checkpoint_captures_uncommitted_diffs(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        hello.write_text("print('edited before checkpoint')\n", encoding="utf-8")

        new_file = initialized_git_dir / "new_file.py"
        new_file.write_text("x = 42\n", encoding="utf-8")

        ckpt_id = guard.create_checkpoint()
        record = guard.get_checkpoint(ckpt_id)
        assert record is not None
        assert "edited before checkpoint" in record["unstaged_diff"]
        assert "new_file.py" in record["untracked_files"]

    def test_restore_checkpoint_discards_post_checkpoint_changes(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        orig_text = hello.read_text(encoding="utf-8")

        # Create checkpoint on pristine state
        ckpt_id = guard.create_checkpoint(name="pristine")

        # Corrupt file and create rogue untracked file
        hello.write_text("CORRUPTED_CODE\n", encoding="utf-8")
        rogue = initialized_git_dir / "rogue.py"
        rogue.write_text("malicious = True\n", encoding="utf-8")

        assert guard.has_uncommitted_changes() is True

        # Restore to checkpoint
        restored = guard.restore_checkpoint(ckpt_id)
        assert restored is True
        assert hello.read_text(encoding="utf-8") == orig_text
        assert not rogue.exists()
        assert guard.has_uncommitted_changes() is False

    def test_restore_checkpoint_with_hard_reset_on_committed_changes(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        hello = initialized_git_dir / "hello.py"
        orig_text = hello.read_text(encoding="utf-8")

        ckpt_id = guard.create_checkpoint(name="pre_commit")

        # Make and commit changes post-checkpoint
        hello.write_text("print('committed post checkpoint')\n", encoding="utf-8")
        commit_sha = guard.commit_success("feat: committed change")
        assert commit_sha is not None

        # Restore checkpoint should hard-reset back to pre_commit HEAD
        restored = guard.restore_checkpoint(ckpt_id, hard_reset=True)
        assert restored is True
        assert hello.read_text(encoding="utf-8") == orig_text

    def test_delete_checkpoint(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        ckpt_id = guard.create_checkpoint(name="to_delete")
        assert guard.get_checkpoint(ckpt_id) is not None

        deleted = guard.delete_checkpoint(ckpt_id)
        assert deleted is True
        assert guard.get_checkpoint(ckpt_id) is None
        assert ckpt_id not in guard.list_checkpoints()

    def test_create_and_restore_checkpoint_non_git_dir(self, tmp_path: Path):
        plain = tmp_path / "plain_dir"
        plain.mkdir()
        guard = GitGuard(repo_dir=str(plain))
        assert guard.create_checkpoint() == ""
        assert guard.restore_checkpoint("dummy") is False


class TestGitGuardInteractiveConfirmation:
    """Tests for interactive user confirmation ([Apply], [Reject], [Diff], [Auto-Fix])."""

    def test_prompt_confirmation_apply(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        from k_cli.git.git_guard import PatchConfirmationAction, confirm_patch_action

        # Test 'apply'
        action = guard.prompt_confirmation(input_fn=lambda prompt: "apply")
        assert action == PatchConfirmationAction.APPLY

        # Test 'a' shortcut
        action_a = guard.prompt_confirmation(input_fn=lambda prompt: "a")
        assert action_a == PatchConfirmationAction.APPLY

        # Test '[apply]'
        action_bracket = guard.prompt_confirmation(input_fn=lambda prompt: "[Apply]")
        assert action_bracket == PatchConfirmationAction.APPLY

    def test_prompt_confirmation_reject(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        from k_cli.git.git_guard import PatchConfirmationAction

        action_r = guard.prompt_confirmation(input_fn=lambda prompt: "r")
        assert action_r == PatchConfirmationAction.REJECT

        action_reject = guard.prompt_confirmation(input_fn=lambda prompt: "reject")
        assert action_reject == PatchConfirmationAction.REJECT

    def test_prompt_confirmation_auto_fix(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        from k_cli.git.git_guard import PatchConfirmationAction

        action_f = guard.prompt_confirmation(input_fn=lambda prompt: "f")
        assert action_f == PatchConfirmationAction.AUTO_FIX

        action_autofix = guard.prompt_confirmation(input_fn=lambda prompt: "auto-fix")
        assert action_autofix == PatchConfirmationAction.AUTO_FIX

    def test_prompt_confirmation_diff_then_apply(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        from k_cli.git.git_guard import PatchConfirmationAction

        inputs = iter(["diff", "apply"])
        displayed_outputs = []

        action = guard.prompt_confirmation(
            diff_text="--- hello.py\n+++ hello.py\n+new line",
            input_fn=lambda prompt: next(inputs),
            display_fn=lambda msg: displayed_outputs.append(msg),
        )
        assert action == PatchConfirmationAction.APPLY
        assert any("--- Proposed Diff ---" in out for out in displayed_outputs)

    def test_prompt_confirmation_eof_defaults_to_reject(self, initialized_git_dir: Path):
        guard = GitGuard(repo_dir=str(initialized_git_dir))
        from k_cli.git.git_guard import PatchConfirmationAction

        def raise_eof(_prompt):
            raise EOFError()

        action = guard.prompt_confirmation(input_fn=raise_eof)
        assert action == PatchConfirmationAction.REJECT

