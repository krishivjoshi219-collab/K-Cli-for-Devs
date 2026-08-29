"""
test_github_client.py - Comprehensive Unit & Integration Tests for GitHub Client & PR Lifecycle
"""

import io
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from k_cli.github.github_client import (
    CIStatus,
    GitHubAPIError,
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    MockGitHubClient,
    PRFixResult,
    PRLifecycleManager,
    PRReviewResult,
    PullRequest,
    discover_github_token,
    infer_repo_from_git,
)
from k_cli.git.verifier import VerificationResult


# =============================================================================
# 1. Token Discovery Tests
# =============================================================================


class TestTokenDiscovery:
    """Tests for multi-tier GitHub token discovery."""

    def test_discover_from_github_token_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_env_token_123")
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
        tok = discover_github_token()
        assert tok == "ghp_env_token_123"

    def test_discover_from_gh_token_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", "gho_gh_token_456")
        tok = discover_github_token()
        assert tok == "gho_gh_token_456"

    def test_discover_from_github_pat_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_PAT", "github_pat_789")
        tok = discover_github_token()
        assert tok == "github_pat_789"

    def test_discover_from_hosts_yml(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)

        mock_config_dir = tmp_path / ".config" / "gh"
        mock_config_dir.mkdir(parents=True, exist_ok=True)
        hosts_file = mock_config_dir / "hosts.yml"
        hosts_file.write_text(
            "github.com:\n"
            "    user: testuser\n"
            "    oauth_token: gho_hosts_yaml_token_abc\n"
            "    git_protocol: https\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        tok = discover_github_token()
        assert tok == "gho_hosts_yaml_token_abc"

    def test_discover_from_env_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")

        env_file = tmp_path / ".env"
        env_file.write_text("SOME_VAR=foo\nGITHUB_TOKEN=\"ghp_env_file_token_999\"\n", encoding="utf-8")

        tok = discover_github_token(search_paths=[tmp_path])
        assert tok == "ghp_env_file_token_999"

    def test_discover_from_key_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")

        key_file = tmp_path / "key.json"
        key_file.write_text(json.dumps({"github_token": "ghp_json_key_token_111"}), encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        tok = discover_github_token()
        assert tok == "ghp_json_key_token_111"

    def test_discover_none_when_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")
        monkeypatch.chdir(tmp_path)

        tok = discover_github_token()
        assert tok is None


# =============================================================================
# 2. Git Remote Inference Tests
# =============================================================================


class TestGitRepoInference:
    """Tests for extracting repository owner/name from git remotes."""

    def test_infer_repo_ssh(self, tmp_path: Path):
        mock_repo = tmp_path / "repo_ssh"
        mock_repo.mkdir()
        subprocess.run(["git", "init"], cwd=mock_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:facebook/react.git"],
            cwd=mock_repo,
            capture_output=True,
            check=True,
        )

        res = infer_repo_from_git(mock_repo)
        assert res is not None
        assert res["owner"] == "facebook"
        assert res["repo"] == "react"
        assert res["full_name"] == "facebook/react"
        assert res["remote_name"] == "origin"

    def test_infer_repo_https(self, tmp_path: Path):
        mock_repo = tmp_path / "repo_https"
        mock_repo.mkdir()
        subprocess.run(["git", "init"], cwd=mock_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/google/jax.git"],
            cwd=mock_repo,
            capture_output=True,
            check=True,
        )

        res = infer_repo_from_git(mock_repo)
        assert res is not None
        assert res["owner"] == "google"
        assert res["repo"] == "jax"
        assert res["full_name"] == "google/jax"

    def test_infer_repo_https_no_git_suffix(self, tmp_path: Path):
        mock_repo = tmp_path / "repo_no_suffix"
        mock_repo.mkdir()
        subprocess.run(["git", "init"], cwd=mock_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/pallets/flask"],
            cwd=mock_repo,
            capture_output=True,
            check=True,
        )

        res = infer_repo_from_git(mock_repo)
        assert res is not None
        assert res["owner"] == "pallets"
        assert res["repo"] == "flask"

    def test_infer_repo_non_git(self, tmp_path: Path):
        non_git = tmp_path / "not_git"
        non_git.mkdir()
        assert infer_repo_from_git(non_git) is None


# =============================================================================
# 3. Data Classes Tests
# =============================================================================


class TestDataClasses:
    """Tests for PullRequest, CIStatus, PRReviewResult, PRFixResult dataclasses."""

    def test_pull_request_serialization(self):
        raw = {
            "number": 42,
            "title": "feat: async memory buffer",
            "body": "Implements zero-copy memory ring buffer.",
            "state": "open",
            "head": {"ref": "feature/async-buffer", "sha": "abcd1234ef"},
            "base": {"ref": "main"},
            "user": {"login": "octocat"},
            "created_at": "2026-08-22T12:00:00Z",
            "updated_at": "2026-08-22T13:00:00Z",
            "html_url": "https://github.com/k-cli/k-cli/pull/42",
            "draft": False,
            "mergeable": True,
            "merged": False,
            "labels": [{"name": "perf"}, "memory"],
        }
        pr = PullRequest.from_dict(raw)
        assert pr.number == 42
        assert pr.title == "feat: async memory buffer"
        assert pr.head_branch == "feature/async-buffer"
        assert pr.head_sha == "abcd1234ef"
        assert pr.base_branch == "main"
        assert pr.author == "octocat"
        assert pr.labels == ["perf", "memory"]

        pr_dict = pr.to_dict()
        assert pr_dict["number"] == 42
        assert pr_dict["author"] == "octocat"
        assert pr_dict["head_sha"] == "abcd1234ef"

    def test_ci_status_calculation(self):
        check_runs_data = {
            "check_runs": [
                {"name": "test-suite", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "completed", "conclusion": "success"},
                {"name": "security-scan", "status": "completed", "conclusion": "failure"},
            ]
        }
        status = CIStatus.from_github_data(check_runs_data=check_runs_data)
        assert status.total_count == 3
        assert status.passed_count == 2
        assert status.failed_count == 1
        assert status.state == "failure"
        assert status.is_passing is False
        assert "CI Failing" in status.summary

    def test_ci_status_all_passing(self):
        check_runs_data = {
            "check_runs": [
                {"name": "test-suite", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "completed", "conclusion": "success"},
            ]
        }
        status = CIStatus.from_github_data(check_runs_data=check_runs_data)
        assert status.total_count == 2
        assert status.passed_count == 2
        assert status.failed_count == 0
        assert status.state == "success"
        assert status.is_passing is True

    def test_ci_status_pending(self):
        check_runs_data = {
            "check_runs": [
                {"name": "test-suite", "status": "in_progress", "conclusion": None},
            ]
        }
        status = CIStatus.from_github_data(check_runs_data=check_runs_data)
        assert status.state == "pending"
        assert status.is_passing is False

    def test_pr_review_result_format_markdown(self):
        res = PRReviewResult(
            pr_number=10,
            verdict="REQUEST_CHANGES",
            summary="Identified an injection vulnerability in query builder.",
            bugs=["SQL query string concatenation without escaping."],
            security_issues=["SQL injection in search_users handler."],
            performance_notes=["N+1 query loop when fetching user tags."],
            line_suggestions=[{"file": "db.py", "line": 45, "suggestion": "Use parameterized queries."}],
        )
        md = res.format_markdown()
        assert "## 🤖 K-CLI Automated PR Review (PR #10)" in md
        assert "REQUEST CHANGES" in md
        assert "SQL query string concatenation" in md
        assert "SQL injection in search_users handler" in md
        assert "`db.py:45`" in md
        assert res.to_dict()["pr_number"] == 10

    def test_pr_fix_result_to_dict(self):
        fix_res = PRFixResult(
            pr_number=15,
            branch="fix-pr-15",
            success=True,
            fixes_applied=["db.py", "utils.py"],
            commit_sha="commit12345",
            pushed=True,
        )
        d = fix_res.to_dict()
        assert d["pr_number"] == 15
        assert d["success"] is True
        assert "db.py" in d["fixes_applied"]


# =============================================================================
# 4. HTTP Client & REST API Tests
# =============================================================================


class TestGitHubClientHttp:
    """Tests for low-level HTTP requests and error handling in GitHubClient."""

    def test_http_get_success(self):
        client = GitHubClient(token="ghp_test_tok", repo="owner/test-repo")
        mock_response = io.BytesIO(json.dumps({"id": 1, "name": "test-repo"}).encode("utf-8"))
        mock_response.status = 200  # type: ignore

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            data = client._request("GET", "/repos/owner/test-repo")
            assert data["name"] == "test-repo"
            assert mock_urlopen.called
            req = mock_urlopen.call_args[0][0]
            assert req.headers["Authorization"] == "Bearer ghp_test_tok"

    def test_http_raw_diff_response(self):
        client = GitHubClient(token="ghp_test_tok", repo="owner/test-repo")
        raw_diff = "diff --git a/a.py b/a.py\n+hello"
        mock_response = io.BytesIO(raw_diff.encode("utf-8"))
        mock_response.status = 200  # type: ignore

        with patch("urllib.request.urlopen", return_value=mock_response):
            diff = client._request("GET", "/repos/owner/test-repo/pulls/1", raw_response=True)
            assert diff == raw_diff

    def test_http_401_auth_error(self):
        client = GitHubClient(token="invalid_tok", repo="owner/test-repo")
        err_body = json.dumps({"message": "Bad credentials"}).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/user",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore
            fp=io.BytesIO(err_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(GitHubAuthError) as exc_info:
                client._request("GET", "/user")
            assert exc_info.value.status_code == 401
            assert "Bad credentials" in str(exc_info.value)

    def test_http_403_rate_limit_error(self):
        client = GitHubClient(token="some_tok", repo="owner/test-repo")
        err_body = json.dumps({"message": "API rate limit exceeded"}).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/repos/a/b",
            code=403,
            msg="Forbidden",
            hdrs={"X-RateLimit-Remaining": "0"},  # type: ignore
            fp=io.BytesIO(err_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(GitHubRateLimitError):
                client._request("GET", "/repos/a/b")

    def test_http_404_not_found_error(self):
        client = GitHubClient(token="some_tok", repo="owner/test-repo")
        err_body = json.dumps({"message": "Not Found"}).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/repos/a/b/pulls/999",
            code=404,
            msg="Not Found",
            hdrs={},  # type: ignore
            fp=io.BytesIO(err_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(GitHubNotFoundError):
                client.get_pull_request(999)


# =============================================================================
# 5. GitHubClient Operations Suite (Mock Mode & Live Mocking)
# =============================================================================


class TestGitHubClientOperations:
    """Tests for high-level GitHubClient operations."""

    def test_mock_mode_list_prs(self):
        client = MockGitHubClient(repo="k-cli/k-cli")
        prs = client.list_pull_requests()
        assert len(prs) >= 2
        assert prs[0].number == 1
        assert prs[0].head_branch == "feat/vector-cache"

    def test_mock_mode_get_pr_and_diff(self):
        client = MockGitHubClient()
        pr1 = client.get_pull_request(1)
        assert pr1.title == "feat: implement fast vector search caching"
        diff1 = client.get_pr_diff(1)
        assert "VectorCache" in diff1

    def test_mock_mode_get_pr_files_and_comments(self):
        client = MockGitHubClient()
        files = client.get_pr_files(1)
        assert len(files) == 1
        assert files[0]["filename"] == "cache.py"

        comments = client.get_pr_comments(1)
        assert len(comments) == 1
        assert "thread safety" in comments[0]["body"]

    def test_mock_mode_ci_status(self):
        client = MockGitHubClient()
        ci = client.get_ci_status("a1b2c3d4e5f6")
        assert ci.is_passing is True
        assert ci.state == "success"

        ci_fail = client.get_ci_status("f6e5d4c3b2a1")
        assert ci_fail.is_passing is False
        assert ci_fail.state == "failure"

    def test_mock_mode_post_review_comment(self):
        client = MockGitHubClient()
        ok = client.post_review_comment(1, "Looks fantastic! Approved.", event="APPROVE")
        assert ok is True
        comments = client.get_pr_comments(1)
        assert any("Looks fantastic" in c.get("body", "") for c in comments)

    def test_mock_mode_merge_pr(self):
        client = MockGitHubClient()
        ok = client.merge_pull_request(1, merge_method="squash")
        assert ok is True
        pr = client.get_pull_request(1)
        assert pr.merged is True
        assert pr.state == "closed"

    def test_set_and_override_mock_pr(self):
        client = MockGitHubClient()
        custom_pr = PullRequest(
            number=99,
            title="custom: test pr",
            head_branch="custom-branch",
            head_sha="customsha123",
        )
        custom_ci = CIStatus(state="success", is_passing=True, total_count=1, passed_count=1)
        client.set_mock_pr(custom_pr, diff="custom diff", ci_status=custom_ci)

        assert client.get_pull_request(99).title == "custom: test pr"
        assert client.get_pr_diff(99) == "custom diff"
        assert client.get_ci_status("customsha123").is_passing is True

    def test_live_list_pull_requests(self):
        client = GitHubClient(token="tok", repo="k-cli/k-cli", mock_mode=False)
        mock_pr_list = [
            {"number": 1, "title": "PR 1", "state": "open", "head": {"ref": "b1"}, "base": {"ref": "main"}},
            {"number": 2, "title": "PR 2", "state": "open", "head": {"ref": "b2"}, "base": {"ref": "main"}},
        ]
        with patch.object(client, "_request", return_value=mock_pr_list):
            prs = client.list_pull_requests()
            assert len(prs) == 2
            assert prs[0].number == 1
            assert prs[1].title == "PR 2"

    def test_live_merge_pull_request(self):
        client = GitHubClient(token="tok", repo="k-cli/k-cli", mock_mode=False)
        with patch.object(client, "_request", return_value={"merged": True, "message": "Pull Request successfully merged"}):
            ok = client.merge_pull_request(5, merge_method="squash", commit_title="Merge PR 5")
            assert ok is True

    def test_live_post_review_fallback_to_issue_comment(self):
        client = GitHubClient(token="tok", repo="k-cli/k-cli", mock_mode=False)

        def mock_req(method, endpoint, data=None, **kwargs):
            if "/reviews" in endpoint:
                raise GitHubAPIError("Cannot review own PR", status_code=422)
            if "/comments" in endpoint:
                return {"id": 999, "body": data.get("body")}
            return {}

        with patch.object(client, "_request", side_effect=mock_req):
            ok = client.post_review_comment(1, "Comment body", event="APPROVE")
            assert ok is True


# =============================================================================
# 6. PR Lifecycle Manager Tests: AI Review
# =============================================================================


class TestPRLifecycleReview:
    """Tests for automated AI PR code review."""

    def test_review_pr_with_json_llm_output(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)

        llm_json_response = json.dumps({
            "verdict": "APPROVE",
            "summary": "Clean and well-structured implementation.",
            "bugs": [],
            "security_issues": [],
            "performance_notes": ["LRU cache significantly reduces compute time."],
            "line_suggestions": [{"file": "cache.py", "line": 10, "suggestion": "Add docstring."}],
        })

        mock_llm = MagicMock()
        mock_llm.generate.return_value = f"```json\n{llm_json_response}\n```"

        result = manager.review_pr(pr_number=1, llm_driver=mock_llm, post_comment=True)
        assert result.pr_number == 1
        assert result.verdict == "APPROVE"
        assert "Clean and well-structured" in result.summary
        assert len(result.performance_notes) == 1
        assert len(result.line_suggestions) == 1

        # Check comment was posted to mock PR
        comments = client.get_pr_comments(1)
        assert any("K-CLI Automated PR Review" in c.get("body", "") for c in comments)

    def test_review_pr_with_text_markdown_llm_output(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)

        llm_text_response = (
            "VERDICT: REQUEST_CHANGES\n"
            "SUMMARY: Found critical race condition in buffer allocation.\n"
            "BUGS:\n"
            "- Buffer overflow on chunk sizes > 4096 bytes.\n"
            "SECURITY:\n"
            "- Unchecked buffer allocation can cause out-of-memory denial of service.\n"
            "PERFORMANCE:\n"
            "- Bytearray reallocations in hot loop.\n"
            "SUGGESTIONS:\n"
            "- stream_parser.py:12: Preallocate fixed buffer size.\n"
        )

        mock_llm = lambda prompt: llm_text_response

        result = manager.review_pr(pr_number=2, llm_driver=mock_llm)
        assert result.verdict == "REQUEST_CHANGES"
        assert len(result.bugs) == 1
        assert "Buffer overflow" in result.bugs[0]
        assert len(result.security_issues) == 1
        assert len(result.performance_notes) == 1

    def test_review_pr_fallback_on_empty_llm(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)
        mock_llm = lambda prompt: ""

        result = manager.review_pr(pr_number=1, llm_driver=mock_llm)
        assert result.verdict == "APPROVE"
        assert "zero critical issues" in result.summary


# =============================================================================
# 7. PR Lifecycle Manager Tests: PR Bug Fixing & Auto-Merge
# =============================================================================


class TestPRLifecycleFixAndMerge:
    """Tests for automated PR fix loop and auto-merge operations."""

    def test_fix_pr_mock_mode_success(self, tmp_path: Path):
        client = MockGitHubClient(repo_dir=tmp_path)
        manager = PRLifecycleManager(client=client, repo_dir=tmp_path)

        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            "<<<<<<< SEARCH: stream_parser.py\n"
            "    buffer = []\n"
            "=======\n"
            "    buffer = bytearray()\n"
            ">>>>>>> REPLACE\n"
        )

        fix_result = manager.fix_pr(pr_number=2, llm_driver=mock_llm, auto_push=True)
        assert fix_result.pr_number == 2
        assert fix_result.success is True
        assert fix_result.pushed is True
        assert fix_result.commit_sha is not None

    def test_auto_merge_pr_success(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)

        # PR 1 CI is passing in default mock
        merged = manager.auto_merge_pr(pr_number=1, require_ci_pass=True)
        assert merged is True
        pr = client.get_pull_request(1)
        assert pr.merged is True

    def test_auto_merge_pr_blocks_failing_ci(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)

        # PR 2 CI is failing in default mock
        merged = manager.auto_merge_pr(pr_number=2, require_ci_pass=True)
        assert merged is False
        pr = client.get_pull_request(2)
        assert pr.merged is False

    def test_auto_merge_pr_already_merged(self):
        client = MockGitHubClient()
        manager = PRLifecycleManager(client=client)
        pr = client.get_pull_request(1)
        pr.merged = True
        pr.state = "closed"

        assert manager.auto_merge_pr(1) is True


# =============================================================================
# 8. Integration & Edge Cases Tests
# =============================================================================


class TestIntegrationAndEdgeCases:
    """Edge cases and integration scenarios."""

    def test_empty_review_comment_posting(self):
        client = MockGitHubClient()
        assert client.post_review_comment(1, "   ") is False

    def test_git_repo_info_inference_and_fallback(self, tmp_path: Path):
        client = GitHubClient(repo="k-cli/bankai", repo_dir=tmp_path)
        info = client.get_repo_info()
        assert info["owner"] == "k-cli"
        assert info["repo"] == "bankai"
        assert info["full_name"] == "k-cli/bankai"

    def test_ci_status_with_workflow_runs(self):
        workflow_data = {
            "workflow_runs": [
                {"name": "build", "status": "completed", "conclusion": "success"}
            ]
        }
        status = CIStatus.from_github_data(workflow_runs_data=workflow_data)
        assert status.workflow_runs == workflow_data["workflow_runs"]

    def test_fix_pr_with_real_git_repo_and_verifier_pass(self, tmp_path: Path):
        # 1. Setup real git repository
        repo_dir = tmp_path / "fix_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "K-CLI"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "k-cli@local"], cwd=repo_dir, check=True, capture_output=True)

        target_file = repo_dir / "calc.py"
        target_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        subprocess.run(["git", "add", "calc.py"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial buggy commit"], cwd=repo_dir, check=True, capture_output=True)

        # 2. Setup mock client and manager
        client = GitHubClient(repo="k-cli/calc", repo_dir=repo_dir, mock_mode=True)
        pr = PullRequest(
            number=7,
            title="fix: correct addition operator",
            head_branch="main",
            head_sha="sha777",
        )
        client.set_mock_pr(pr, diff="--- a/calc.py\n+++ b/calc.py\n@@ -2 +2 @@\n-    return a - b\n+    return a + b\n")

        manager = PRLifecycleManager(client=client, repo_dir=repo_dir)

        # Mock LLM returns patch
        patch_text = (
            "<<<<<<< SEARCH: calc.py\n"
            "def add(a, b):\n"
            "    return a - b\n"
            "=======\n"
            "def add(a, b):\n"
            "    return a + b\n"
            ">>>>>>> REPLACE\n"
        )
        mock_llm = MagicMock()
        mock_llm.generate.return_value = patch_text

        # Mock verifier passes
        mock_verifier = MagicMock()
        mock_verifier.run_project_tests.return_value = VerificationResult(
            success=True, error_trace="", code="", language="pytest"
        )

        res = manager.fix_pr(pr_number=7, llm_driver=mock_llm, verifier=mock_verifier)
        assert res.success is True
        assert "calc.py" in res.fixes_applied
        assert res.commit_sha is not None

        # Verify file on disk is patched
        assert "return a + b" in target_file.read_text(encoding="utf-8")

        # Verify git commit was created
        log_res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=repo_dir, capture_output=True, text=True)
        assert "fix(pr-7)" in log_res.stdout

    def test_fix_pr_with_failing_verifier_rolls_back(self, tmp_path: Path):
        # 1. Setup real git repository
        repo_dir = tmp_path / "fix_fail_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "K-CLI"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "k-cli@local"], cwd=repo_dir, check=True, capture_output=True)

        target_file = repo_dir / "service.py"
        original_content = "def run():\n    return 'original'\n"
        target_file.write_text(original_content, encoding="utf-8")
        subprocess.run(["git", "add", "service.py"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True, capture_output=True)

        client = GitHubClient(repo="k-cli/service", repo_dir=repo_dir, mock_mode=True)
        pr = PullRequest(number=8, title="broken fix", head_branch="main")
        client.set_mock_pr(pr)

        manager = PRLifecycleManager(client=client, repo_dir=repo_dir)

        # Patch that breaks
        patch_text = (
            "<<<<<<< SEARCH: service.py\n"
            "def run():\n"
            "    return 'original'\n"
            "=======\n"
            "def run():\n"
            "    raise RuntimeError('broken')\n"
            ">>>>>>> REPLACE\n"
        )
        mock_llm = MagicMock()
        mock_llm.generate.return_value = patch_text

        # Mock verifier always fails
        mock_verifier = MagicMock()
        mock_verifier.run_project_tests.return_value = VerificationResult(
            success=False, error_trace="RuntimeError: broken", code="", language="pytest"
        )

        res = manager.fix_pr(pr_number=8, llm_driver=mock_llm, verifier=mock_verifier, max_fix_attempts=2)
        assert res.success is False
        assert res.rolled_back is True

        # Verify file is restored to original content
        assert target_file.read_text(encoding="utf-8") == original_content

    def test_auto_merge_pr_verifier_failure_blocks_merge(self, tmp_path: Path):
        client = GitHubClient(repo="k-cli/proj", repo_dir=tmp_path, mock_mode=False)
        pr = PullRequest(number=9, title="feature", state="open", head_branch="main", head_sha="sha99")
        with patch.object(client, "get_pull_request", return_value=pr):
            with patch.object(client, "get_ci_status", return_value=CIStatus(is_passing=True, state="success")):
                mock_verifier = MagicMock()
                mock_verifier.run_project_tests.return_value = VerificationResult(
                    success=False, error_trace="Tests failed", code="", language="pytest"
                )
                manager = PRLifecycleManager(client=client, repo_dir=tmp_path)
                merged = manager.auto_merge_pr(9, require_ci_pass=True, verifier=mock_verifier)
                assert merged is False

