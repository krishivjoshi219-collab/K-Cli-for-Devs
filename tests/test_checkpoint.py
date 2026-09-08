"""
test_checkpoint.py - Unit tests for CheckpointManager rollback and orphan file purging
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

_root_dir = Path(__file__).parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

import pytest
from k_cli.git.checkpoint import CheckpointManager


@pytest.fixture
def temp_workspace():
    """Creates an isolated temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    workspace = Path(temp_dir)
    # Create initial files
    (workspace / "module_a.py").write_text("def a(): return 1\n", encoding="utf-8")
    (workspace / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    yield workspace
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_checkpoint_creation_and_rollback(temp_workspace: Path):
    mgr = CheckpointManager(workspace_dir=str(temp_workspace))

    # 1. Create baseline checkpoint
    ckpt_id = mgr.create_checkpoint(description="Baseline snapshot")
    assert ckpt_id.startswith("ckpt_")

    # 2. Modify module_a.py
    (temp_workspace / "module_a.py").write_text("def a(): return 999\n", encoding="utf-8")

    # 3. Verify diff shows modification
    diff = mgr.compute_diff(ckpt_id)
    assert "-def a(): return 1" in diff
    assert "+def a(): return 999" in diff

    # 4. Rollback
    ok, msg = mgr.rollback_last_checkpoint()
    assert ok is True
    assert "Successfully rolled back" in msg

    # 5. Verify module_a.py restored
    content = (temp_workspace / "module_a.py").read_text(encoding="utf-8")
    assert content == "def a(): return 1\n"


def test_checkpoint_orphan_file_purging(temp_workspace: Path):
    mgr = CheckpointManager(workspace_dir=str(temp_workspace))

    # 1. Create baseline checkpoint
    ckpt_id = mgr.create_checkpoint(description="Pre-agent execution snapshot")

    # 2. Simulate agent creating a new file that fails verification
    orphan_file = temp_workspace / "corrupted_generated_code.py"
    orphan_file.write_text("invalid syntax !!!", encoding="utf-8")
    assert orphan_file.exists()

    # 3. Modify existing file
    (temp_workspace / "module_a.py").write_text("def a(): return 42\n", encoding="utf-8")

    # 4. Rollback last checkpoint
    ok, msg = mgr.rollback_last_checkpoint()
    assert ok is True
    assert "orphan files purged" in msg

    # 5. Verify orphan file was deleted and modified file was restored
    assert not orphan_file.exists(), "Orphan file must be purged during rollback"
    assert (temp_workspace / "module_a.py").read_text(encoding="utf-8") == "def a(): return 1\n"
