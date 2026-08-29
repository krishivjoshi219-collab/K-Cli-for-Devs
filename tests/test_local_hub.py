"""
test_local_hub.py - Unit tests for Local GitHub Hub & Trending Engine

Validates:
1. Local GitHub Hub repository analytics, git log parsing, commit records, and summary calculations.
2. Trending Engine online API search and curated catalog offline fallbacks.
3. CLI commands `k-cli hub` and `k-cli trending`.
4. Textual UI Modals (LocalHubModal & TrendingModal) initialization.
"""

import json
import subprocess
import pytest
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.github.local_hub import LocalGitHubHub, LocalCommit, LocalHubSummary
from k_cli.github.trending import TrendingEngine, TrendingRepo, CURATED_TRENDING_REPOS
from k_cli.tui.tui_app import LocalHubModal, TrendingModal

runner = CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path):
    """Initializes a temporary git repository with commit history."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@kcli.local"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "K-CLI Developer"], cwd=repo_dir, check=True, capture_output=True)

    f = repo_dir / "README.md"
    f.write_text("# Test Repo\nInitial content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: initial commit"], cwd=repo_dir, check=True, capture_output=True)

    return repo_dir


class TestLocalGitHubHub:
    """Tests local GitHub workstation analytics and git log parsing."""

    def test_hub_summary_calculation(self, temp_git_repo):
        hub = LocalGitHubHub(repo_path=str(temp_git_repo))
        summary = hub.get_summary()

        assert isinstance(summary, LocalHubSummary)
        assert summary.branch_name in ("main", "master")
        assert summary.total_commits >= 1
        assert summary.uncommitted_changes == 0
        assert summary.is_clean is True
        assert summary.health_score >= 90.0

    def test_recent_commits_parsing(self, temp_git_repo):
        hub = LocalGitHubHub(repo_path=str(temp_git_repo))
        commits = hub.get_recent_commits(limit=5)

        assert len(commits) >= 1
        first = commits[0]
        assert isinstance(first, LocalCommit)
        assert first.subject == "feat: initial commit"
        assert first.author == "K-CLI Developer"

    def test_activity_feed_generation(self, temp_git_repo):
        hub = LocalGitHubHub(repo_path=str(temp_git_repo))
        feed = hub.get_activity_feed(limit=5)

        assert len(feed) >= 1
        assert feed[0]["type"] == "commit"
        assert "initial commit" in feed[0]["title"]


class TestTrendingEngine:
    """Tests trending GitHub repository discovery engine."""

    def test_trending_engine_offline_fallback(self):
        engine = TrendingEngine(offline_only=True)
        repos = engine.get_trending(limit=5)

        assert len(repos) == 5
        first = repos[0]
        assert isinstance(first, TrendingRepo)
        assert first.owner == "krishivjoshi219-collab"
        assert first.name == "K-Cli"

    def test_trending_filtering_by_language_and_query(self):
        engine = TrendingEngine(offline_only=True)

        py_repos = engine.get_trending(language="Python", limit=10)
        assert all(r.language == "Python" for r in py_repos)

        ai_repos = engine.get_trending(query="ollama", limit=10)
        assert len(ai_repos) >= 1
        assert any("ollama" in r.name.lower() or "ollama" in r.description.lower() for r in ai_repos)


class TestHubAndTrendingCLICommands:
    """Tests CLI commands `k-cli hub` and `k-cli trending`."""

    def test_hub_cli_command(self, temp_git_repo):
        res = runner.invoke(app, ["hub", "--repo", str(temp_git_repo), "--json"])
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert data["total_commits"] >= 1
        assert data["is_clean"] is True

    def test_trending_cli_command(self):
        res = runner.invoke(app, ["trending", "--limit", "3", "--json"])
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert len(data) == 3
        assert "name" in data[0]


class TestHubAndTrendingModals:
    """Tests Textual TUI modal initializations."""

    def test_local_hub_modal_init(self):
        modal = LocalHubModal()
        assert modal is not None

    def test_trending_modal_init(self):
        modal = TrendingModal()
        assert modal is not None
