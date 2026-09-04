"""
test_autonomous_killer_features.py - Full Unit & Integration Tests for the 5 Killer Features
Project Bankai Engine v1.0.0

Features Tested:
1. Autonomous Time-Travel Checkpoints & Instant Rollback (CheckpointManager)
2. Persistent Self-Learning Project Memory (ProjectMemoryManager)
3. Standardized Evaluation & Benchmark Scorecard (EvaluationHarness)
4. Autonomous Docker & CI/CD Pipeline Healer (CICDHealer)
5. Global Ambient Error Interceptor Sentinel (GlobalSentinel)
"""

import os
import sys
import subprocess
from pathlib import Path
import pytest

from k_cli.git.checkpoint import CheckpointManager
from k_cli.core.memory import ProjectMemoryManager
from k_cli.tools.benchmark_harness import EvaluationHarness, BenchmarkReport
from k_cli.tools.cicd_healer import CICDHealer, CICDFixResult
from k_cli.tools.sentinel import GlobalSentinel, SentinelInterceptionResult
from k_cli.agents.autonomous_agent import AVAILABLE_TOOLS, tool_heal_cicd_pipeline


def test_checkpoint_manager_lifecycle(tmp_path):
    """Verifies snapshot creation, diff calculation, and non-destructive rollback."""
    ws = tmp_path / "repo"
    ws.mkdir()
    
    file1 = ws / "main.py"
    file1.write_text("def hello():\n    return 'initial'\n", encoding="utf-8")
    file2 = ws / "README.md"
    file2.write_text("# Project Docs\n", encoding="utf-8")

    mgr = CheckpointManager(workspace_dir=str(ws))
    
    # 1. Create Checkpoint
    ckpt_id = mgr.create_checkpoint(description="Initial test snapshot")
    assert ckpt_id.startswith("ckpt_")
    
    ckpts = mgr.list_checkpoints()
    assert len(ckpts) == 1
    assert ckpts[0]["checkpoint_id"] == ckpt_id
    assert "main.py" in ckpts[0]["files_tracked"]

    # 2. Modify files
    file1.write_text("def hello():\n    return 'mutated'\n", encoding="utf-8")
    
    # 3. Compute Diff
    diff_out = mgr.compute_diff()
    assert "-    return 'initial'" in diff_out
    assert "+    return 'mutated'" in diff_out

    # 4. Rollback
    success, msg = mgr.rollback_last_checkpoint()
    assert success is True
    assert "Successfully rolled back" in msg
    assert file1.read_text(encoding="utf-8") == "def hello():\n    return 'initial'\n"

    # 5. After rollback, diff should be 0 modifications
    clean_diff = mgr.compute_diff()
    assert "Zero modifications detected" in clean_diff or "No checkpoints available" in clean_diff


def test_project_memory_manager_lifecycle(tmp_path):
    """Verifies KCLI.md initialization, learning append, and bounded context loading."""
    mgr = ProjectMemoryManager(workspace_dir=str(tmp_path))
    
    # 1. Initialize
    mgr.initialize_if_missing()
    target = tmp_path / "KCLI.md"
    assert target.exists()
    assert "K-CLI Project Memory" in target.read_text(encoding="utf-8")

    # 2. Record Learning
    mgr.record_learning("Use pytest -v --tb=short for fast verification", category="TestingDirective")
    
    content = mgr.load_memory()
    assert "TestingDirective" in content
    assert "Use pytest -v --tb=short" in content


def test_evaluation_harness_scorecard(tmp_path):
    """Verifies the 5-battery standardized evaluation and markdown export."""
    harness = EvaluationHarness(workspace_dir=str(tmp_path))
    report = harness.run_full_evaluation()
    
    assert isinstance(report, BenchmarkReport)
    assert report.total_tasks == 5
    assert report.passed_tasks == 5
    assert report.ast_pass_rate_pct == 100.0
    assert report.total_duration_sec >= 0.0
    assert report.total_saved_usd > 0.0

    scorecard_path = tmp_path / ".kcli" / "BENCHMARK_SCORECARD.md"
    assert scorecard_path.exists()
    scorecard_text = scorecard_path.read_text(encoding="utf-8")
    assert "Benchmark Scorecard" in scorecard_text
    assert "TASK-01" in scorecard_text
    assert "TASK-05" in scorecard_text
    assert "100.0% PASS" in scorecard_text


def test_cicd_healer_workflow_and_docker(tmp_path):
    """Verifies automatic healing of legacy GitHub Actions and unoptimized Dockerfiles."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    wf_file = wf_dir / "ci.yml"
    wf_file.write_text(
        "name: CI\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v2\n"
        "      - uses: actions/setup-python@v3\n"
        "      - run: python -m pytest\n",
        encoding="utf-8",
    )

    df_file = tmp_path / "Dockerfile"
    df_file.write_text(
        "FROM python:3.11-alpine\n"
        "RUN apk add git gcc\n"
        "RUN pip install requests\n",
        encoding="utf-8",
    )

    healer = CICDHealer(workspace_dir=str(tmp_path))
    
    # 1. Heal workflow
    wf_res = healer.audit_and_heal_workflow(str(wf_file))
    assert wf_res.success is True
    assert wf_res.issues_found >= 2
    healed_wf = wf_file.read_text(encoding="utf-8")
    assert "actions/checkout@v4" in healed_wf
    assert "actions/setup-python@v5" in healed_wf
    assert "PYTHONPATH=." in healed_wf

    # 2. Heal Dockerfile
    df_res = healer.audit_and_heal_dockerfile(str(df_file))
    assert df_res.success is True
    assert df_res.issues_found >= 2
    healed_df = df_file.read_text(encoding="utf-8")
    assert "apk add --no-cache" in healed_df
    assert "pip install --no-cache-dir" in healed_df


def test_global_sentinel_success_and_alias_repair(tmp_path):
    """Verifies sub-second error interception and automatic python interpreter healing."""
    sentinel = GlobalSentinel(workspace_dir=str(tmp_path))
    
    # 1. Clean command
    res1 = sentinel.wrap_and_heal("echo 'Sentinel Online'")
    assert res1.original_exit_code == 0
    assert res1.final_exit_code == 0
    assert "Sentinel Online" in res1.stdout

    # 2. Command with python unaliased
    res2 = sentinel.wrap_and_heal('python -c "print(100 + 200)"')
    assert res2.repair_successful is True
    assert res2.final_exit_code == 0
    assert "300" in res2.stdout


def test_autonomous_agent_tool_registry():
    """Verifies that the new CI/CD healer tool is properly registered in AutonomousAgent."""
    assert "heal_cicd_pipeline" in AVAILABLE_TOOLS
    res = tool_heal_cicd_pipeline("nonexistent_workflow.yml")
    assert "does not exist" in res or "Success=False" in res
