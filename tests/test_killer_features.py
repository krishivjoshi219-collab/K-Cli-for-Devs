"""
test_killer_features.py - Full Unit & Integration Test Suite for 10 Killer Features
Project Bankai Engine v1.0.0
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from k_cli.core.sdk import KCLI
from k_cli.github.pr_watcher import PRWatcherDaemon, WatchEvent
from k_cli.git.ai_bisect import AIBisectEngine, BisectResult
from k_cli.core.smart_router import SmartModelRouter, TaskTier, RouteDecision
from k_cli.tools.repo_gardener import RepoGardener, GardenReport
from k_cli.tools.codebase_qa import CodebaseQAEngine, QAResult
from k_cli.tools.ghost_daemon import GhostTerminalDaemon, GhostHealPrompt
from k_cli.agents.adversarial_swarm import AdversarialConsensusSwarm, SwarmConsensusResult
from k_cli.tools.synapse_graph import SynapseCodeGraph, SynapseSlice
from k_cli.core.airgap import AirgapManager, AirgapAuditReport
from k_cli.agents.scaffold_engine import FullStackScaffolder, ScaffoldResult


@pytest.fixture
def temp_repo(tmp_path):
    """Temporary git repository for testing."""
    ws = tmp_path / "killer_repo"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(ws), capture_output=True)
    
    (ws / "main.py").write_text("def run_task():\n    return 42\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=str(ws), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(ws), capture_output=True)
    return ws


# Feature 1: PR Watcher Daemon
def test_pr_watcher_poll_and_event():
    from k_cli.github.github_client import PullRequest
    mock_client = MagicMock()
    mock_client.list_pull_requests.return_value = [
        PullRequest(number=101, title="Add feature X", head_sha="sha123", base_branch="main", author="alice", html_url="http://pr101")
    ]
    mock_client.get_pr_diff.return_value = "+ def feature_x(): pass"
    daemon = PRWatcherDaemon(github_client=mock_client)
    events = daemon.poll_once()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert events[0].pr_number == 101
    assert events[0].action_taken == "reviewed_and_commented"


# Feature 2: AI Git Bisect
def test_ai_bisect_execution(temp_repo):
    engine = AIBisectEngine(repo_path=str(temp_repo))
    res = engine.run_bisect(test_command="python -c 'import sys; sys.exit(0)'", good_commit="HEAD", bad_commit="HEAD")
    assert isinstance(res, BisectResult)
    assert res.total_commits_searched >= 0
    assert "Root-Cause" in res.render_markdown()


# Feature 3: Smart Model Router
def test_smart_model_router_tiers():
    router = SmartModelRouter()
    trivial_dec = router.route("fix a small typo in the readme")
    assert trivial_dec.tier == TaskTier.TRIVIAL
    assert trivial_dec.savings_usd > 0.0

    complex_dec = router.route("architect a distributed lock-free consensus protocol with adversarial red-team verification")
    assert complex_dec.tier == TaskTier.COMPLEX
    assert "claude" in complex_dec.selected_model


# Feature 4: Repo Gardener
def test_repo_gardener_sweep(temp_repo):
    gardener = RepoGardener(repo_path=str(temp_repo))
    report = gardener.run_garden_sweep()
    assert isinstance(report, GardenReport)
    assert report.total_files_scanned >= 1
    assert report.health_score <= 100.0
    assert "Report" in report.render_markdown()


# Feature 5: Codebase QA Explainer
def test_codebase_qa_explainer(temp_repo):
    qa = CodebaseQAEngine(repo_path=str(temp_repo))
    res = qa.ask("How does run_task work?")
    assert isinstance(res, QAResult)
    assert res.confidence > 0.8
    assert "run_task" in res.referenced_files or "main.py" in str(res.referenced_files)


# Feature 6: Ghost Terminal Daemon
def test_ghost_terminal_daemon(temp_repo):
    daemon = GhostTerminalDaemon(repo_path=str(temp_repo))
    trace = "Traceback (most recent call last):\n  File 'main.py', line 2, in run_task\nTypeError: unsupported operand"
    prompt = daemon.analyze_output_buffer(trace)
    assert prompt is not None
    assert prompt.target_file == "main.py"


# Feature 7: Adversarial Swarm Loop
def test_adversarial_swarm_consensus():
    swarm = AdversarialConsensusSwarm(max_rounds=2)
    res = swarm.run_consensus("Write a binary search algorithm in Python")
    assert isinstance(res, SwarmConsensusResult)
    assert res.consensus_reached is True
    assert len(res.attacks_evaluated) >= 1
    assert "Consensus" in res.summary


# Feature 8: Synapse Code Graph
def test_synapse_code_graph(temp_repo):
    graph = SynapseCodeGraph(repo_path=str(temp_repo))
    slice_res = graph.extract_subgraph_slice(query="run_task")
    assert isinstance(slice_res, SynapseSlice)
    assert slice_res.compression_ratio >= 0.0
    assert "Synapse" in slice_res.render_context()


# Feature 9: Airgap Sovereign Mode
def test_airgap_manager_audit():
    mgr = AirgapManager()
    mgr.enable_airgap()
    rep = mgr.audit_environment()
    assert isinstance(rep, AirgapAuditReport)
    assert rep.is_airgap_active is True
    assert len(rep.local_toolchains_detected) >= 1
    mgr.disable_airgap()


# Feature 10: Full-Stack Scaffolder
def test_full_stack_scaffolder(tmp_path):
    scaffolder = FullStackScaffolder()
    res = scaffolder.scaffold(spec_prompt="FastAPI + Redis Cache", target_dir=str(tmp_path / "app"), write_to_disk=True)
    assert isinstance(res, ScaffoldResult)
    assert res.total_files == 5
    assert (tmp_path / "app" / "main.py").exists()
    assert (tmp_path / "app" / "Dockerfile").exists()


# SDK Integration for all 10
def test_sdk_10_features_integration(temp_repo):
    from k_cli.github.github_client import PullRequest
    with KCLI(repo_path=str(temp_repo), mock_mode=True) as kcli:
        kcli.github.client.list_pull_requests = MagicMock(return_value=[
            PullRequest(number=99, title="Mock PR", head_sha="sha99", base_branch="main", author="bob", html_url="http://pr99")
        ])
        kcli.github.client.get_pr_diff = MagicMock(return_value="+ def mock(): pass")
        assert len(kcli.watch_prs(max_iterations=1)) >= 1
        assert kcli.route("fix a typo").tier == TaskTier.TRIVIAL
        assert kcli.garden().total_files_scanned >= 1
        assert kcli.explain("where is main").confidence > 0.5
        assert kcli.swarm_adversarial("sum function").consensus_reached is True
        assert kcli.synapse("run_task").compression_ratio >= 0.0
        assert kcli.airgap().is_airgap_active is False
        assert kcli.scaffold("app").total_files == 5
