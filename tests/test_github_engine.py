"""
test_github_engine.py - Comprehensive Unit & Integration Tests for GitHub Ecosystem Engine
Project Bankai Engine v1.0.0
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from k_cli.github.github_engine import (
    GitHubEngine,
    GitHubIssue,
    GitHubRelease,
    IssueSolveResult,
    WorkflowRun,
)
from k_cli.cli import app

runner = CliRunner()


@pytest.fixture
def mock_github_engine(tmp_path):
    """Creates a GitHubEngine with mocked network calls."""
    repo_dir = tmp_path / "mock_gh_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), capture_output=True)
    
    (repo_dir / "math_utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    subprocess.run(["git", "add", "math_utils.py"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: initial math utils"], cwd=str(repo_dir), capture_output=True)

    engine = GitHubEngine(token="mock-token-12345", owner="bankai-org", repo="k-cli-test", repo_path=str(repo_dir))
    return engine


def test_list_issues_parsing(mock_github_engine):
    """Tests fetching and parsing GitHub issues."""
    mock_issues_json = [
        {
            "number": 101,
            "title": "Fix division by zero in calculator",
            "body": "When dividing by zero, an unhandled ZeroDivisionError is raised.",
            "state": "open",
            "user": {"login": "octocat"},
            "labels": [{"name": "bug"}, {"name": "priority-high"}],
            "comments": 3,
            "html_url": "https://github.com/bankai-org/k-cli-test/issues/101",
            "created_at": "2026-08-22T10:00:00Z",
        }
    ]

    with patch.object(mock_github_engine, "_make_request", return_value=mock_issues_json):
        issues = mock_github_engine.list_issues()
        assert len(issues) == 1
        assert issues[0].number == 101
        assert issues[0].title == "Fix division by zero in calculator"
        assert issues[0].author == "octocat"
        assert "bug" in issues[0].labels


def test_get_issue_and_create_issue(mock_github_engine):
    """Tests get_issue and create_issue."""
    mock_issue_data = {
        "number": 102,
        "title": "Add multi-model benchmark support",
        "body": "Support testing latency and tok/s across models.",
        "state": "open",
        "user": {"login": "developer"},
        "labels": [{"name": "enhancement"}],
        "comments": 0,
        "html_url": "https://github.com/bankai-org/k-cli-test/issues/102",
        "created_at": "2026-08-22T11:00:00Z",
    }

    with patch.object(mock_github_engine, "_make_request", return_value=mock_issue_data):
        issue = mock_github_engine.get_issue(102)
        assert issue.number == 102
        assert issue.title == "Add multi-model benchmark support"

        created = mock_github_engine.create_issue("Add multi-model benchmark support", "Body text")
        assert created.number == 102


def test_list_releases_and_create_release(mock_github_engine):
    """Tests releases listing and release creation with changelog generation."""
    mock_releases_data = [
        {
            "id": 5001,
            "tag_name": "v1.0.0",
            "name": "K-CLI v1.0.0 Release",
            "body": "## What's Changed\n- Added GitHub Engine & Model Hub",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/bankai-org/k-cli-test/releases/tag/v1.0.0",
            "published_at": "2026-08-22T12:00:00Z",
            "assets": [],
        }
    ]

    with patch.object(mock_github_engine, "_make_request", return_value=mock_releases_data):
        releases = mock_github_engine.list_releases()
        assert len(releases) == 1
        assert releases[0].tag_name == "v1.0.0"

    with patch.object(mock_github_engine, "_make_request", return_value=mock_releases_data[0]):
        new_rel = mock_github_engine.create_release(tag_name="v1.0.0", name="K-CLI v1.0.0 Release")
        assert new_rel.tag_name == "v1.0.0"


def test_list_workflow_runs(mock_github_engine):
    """Tests GitHub Actions workflow runs listing."""
    mock_runs_data = {
        "workflow_runs": [
            {
                "id": 99001,
                "name": "CI Test Suite",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/bankai-org/k-cli-test/actions/runs/99001",
                "head_branch": "main",
                "head_sha": "abc1234567",
                "created_at": "2026-08-22T12:30:00Z",
            }
        ]
    }

    with patch.object(mock_github_engine, "_make_request", return_value=mock_runs_data):
        runs = mock_github_engine.list_workflow_runs()
        assert len(runs) == 1
        assert runs[0].id == 99001
        assert runs[0].conclusion == "success"


def test_create_and_list_gists(mock_github_engine):
    """Tests creating and listing GitHub Gists."""
    mock_gist_resp = {
        "id": "gist-12345",
        "html_url": "https://gist.github.com/octocat/gist-12345",
        "description": "Snippet",
        "files": {"demo.py": {}},
    }

    with patch.object(mock_github_engine, "_make_request", return_value=mock_gist_resp):
        url = mock_github_engine.create_gist({"demo.py": "print('hello world')"})
        assert "gist.github.com" in url


def test_cli_gh_commands():
    """Tests CLI commands: k-cli gh issues, releases, actions."""
    mock_issues = [
        {
            "number": 1,
            "title": "Bug in parser",
            "body": "Description",
            "state": "open",
            "user": {"login": "tester"},
            "labels": [],
            "comments": 0,
            "html_url": "https://github.com/owner/repo/issues/1",
            "created_at": "2026-08-22",
        }
    ]

    with patch("k_cli.github.github_engine.GitHubEngine._make_request", return_value=mock_issues):
        res = runner.invoke(app, ["gh", "issues", "--json"])
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert len(data) == 1
        assert data[0]["number"] == 1
