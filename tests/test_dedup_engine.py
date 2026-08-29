"""
test_dedup_engine.py - Comprehensive Unit Tests for DedupEngine Module
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from k_cli.github.dedup_engine import (
    CommitRecord,
    DedupEngine,
    DedupMatch,
    SimilarityScorer,
    SymbolRecord,
)


@pytest.fixture
def sample_repo():
    """Creates a temporary git repository with mock commits and code files for deduplication testing."""
    tmp_dir = tempfile.mkdtemp()
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "Dedup Author"
    env["GIT_AUTHOR_EMAIL"] = "dedup@example.com"
    env["GIT_COMMITTER_NAME"] = "Dedup Author"
    env["GIT_COMMITTER_EMAIL"] = "dedup@example.com"

    # Git init
    subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "Dedup Author"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.email", "dedup@example.com"], cwd=tmp_dir, check=True, capture_output=True, env=env)

    # File 1: auth.py with TokenValidator
    auth_file = Path(tmp_dir) / "auth.py"
    auth_file.write_text(
        "class TokenValidator:\n"
        "    \"\"\"Validates JWT authentication tokens and session expiry.\"\"\"\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n"
        "\n"
        "    def validate_token(self, token: str) -> bool:\n"
        "        return bool(token and len(token) > 10)\n",
        encoding="utf-8",
    )

    # Commit 1
    subprocess.run(["git", "add", "auth.py"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "feat(auth): implement user authentication token validator (fixes #42)"],
        cwd=tmp_dir,
        check=True,
        capture_output=True,
        env=env,
    )

    # File 2: metrics.py with RamMonitor
    metrics_file = Path(tmp_dir) / "metrics.py"
    metrics_file.write_text(
        "import psutil\n"
        "\n"
        "def get_system_ram_usage() -> float:\n"
        "    \"\"\"Calculates active RAM usage in megabytes.\"\"\"\n"
        "    return psutil.virtual_memory().used / (1024 * 1024)\n",
        encoding="utf-8",
    )

    # Commit 2
    subprocess.run(["git", "add", "metrics.py"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "feat(metrics): add system RAM monitoring metric calculator (closes #88)"],
        cwd=tmp_dir,
        check=True,
        capture_output=True,
        env=env,
    )

    yield Path(tmp_dir)

    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestSimilarityScorer:
    def test_tokenize_camel_and_snake_case(self):
        text = "getUserById and calculate_total_score with JWTTokenHandler"
        tokens = SimilarityScorer.tokenize(text)
        assert "get" in tokens
        assert "user" in tokens
        assert "id" in tokens
        assert "calculate" in tokens
        assert "total" in tokens
        assert "score" in tokens
        assert "jwt" in tokens
        assert "token" in tokens
        assert "handler" in tokens
        # Stop words like 'and', 'with' should be filtered
        assert "and" not in tokens
        assert "with" not in tokens

    def test_jaccard_similarity(self):
        t1 = ["user", "auth", "token"]
        t2 = ["user", "auth", "token"]
        assert SimilarityScorer.jaccard_similarity(t1, t2) == 1.0

        t3 = ["database", "migration"]
        assert SimilarityScorer.jaccard_similarity(t1, t3) == 0.0

        t4 = ["user", "session", "token"]
        # Intersection: user, token (2). Union: user, auth, token, session (4) -> 0.5
        assert SimilarityScorer.jaccard_similarity(t1, t4) == 0.5

    def test_token_overlap(self):
        q = ["validate", "token"]
        doc = ["class", "token", "validator", "validate", "token", "string"]
        assert SimilarityScorer.token_overlap(q, doc) == 1.0

        q2 = ["validate", "token", "database"]
        assert pytest.approx(SimilarityScorer.token_overlap(q2, doc), 0.01) == 2 / 3

    def test_bm25_scoring(self):
        q = ["authentication", "token"]
        d1 = ["user", "authentication", "token", "validator"]
        d2 = ["database", "schema", "table"]
        corpus_df = {"authentication": 1, "token": 1, "user": 1, "database": 1}

        score1 = SimilarityScorer.bm25_score(q, d1, corpus_df, total_docs=2, avg_doc_len=4.0)
        score2 = SimilarityScorer.bm25_score(q, d2, corpus_df, total_docs=2, avg_doc_len=4.0)

        assert score1 > 0.5
        assert score2 == 0.0

    def test_composite_similarity(self):
        sim = SimilarityScorer.composite_similarity(
            "validate user authentication token",
            "feat(auth): implement user authentication token validator",
        )
        assert sim > 0.7


class TestDedupMatchDataclass:
    def test_dedup_match_to_dict(self):
        match = DedupMatch(
            is_duplicate=True,
            confidence=0.92546,
            existing_commit="a1b2c3d4e5f6",
            file_path="src/auth.py",
            line_range=(10, 25),
            explanation="Matched TokenValidator",
            match_type="symbol",
            metadata={"symbol_name": "TokenValidator"},
        )
        d = match.to_dict()
        assert d["is_duplicate"] is True
        assert d["confidence"] == 0.9255
        assert d["existing_commit"] == "a1b2c3d4e5f6"
        assert d["line_range"] == [10, 25]
        assert d["match_type"] == "symbol"
        assert d["metadata"]["symbol_name"] == "TokenValidator"


class TestDedupEngineGitHistory:
    def test_get_git_commits(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        commits = engine.get_git_commits(depth=10)

        assert len(commits) == 2
        subjects = [c.subject for c in commits]
        assert any("token validator" in s for s in subjects)
        assert any("RAM monitoring" in s for s in subjects)

        # Verify issue refs extraction
        auth_commit = [c for c in commits if "auth" in c.subject][0]
        assert "#42" in auth_commit.issue_refs

    def test_scan_git_history_matching(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        results = engine.scan_git_history("implement user authentication token validator")

        assert len(results) >= 1
        score, commit = results[0]
        assert score > 0.7
        assert "auth" in commit.subject


class TestDedupEngineASTSymbols:
    def test_get_ast_symbols(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        symbols = engine.get_ast_symbols()

        names = [s.name for s in symbols]
        assert "TokenValidator" in names
        assert "get_system_ram_usage" in names

    def test_scan_ast_symbols_matching(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        results = engine.scan_ast_symbols("TokenValidator")

        assert len(results) >= 1
        score, sym = results[0]
        assert score > 0.8
        assert sym.name == "TokenValidator"
        assert sym.rel_path == "auth.py"

    def test_find_duplicate_symbols(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        matches = engine.find_duplicate_symbols("TokenValidator")

        assert len(matches) >= 1
        assert matches[0]["name"] == "TokenValidator"
        assert matches[0]["rel_path"] == "auth.py"


class TestDedupEngineDuplicateScanning:
    def test_scan_for_duplicate_symbol_match(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo), duplicate_threshold=0.65)
        match = engine.scan_for_duplicate("create a TokenValidator to validate auth tokens")

        assert match is not None
        assert match.is_duplicate is True
        assert match.confidence >= 0.65
        assert match.match_type == "symbol"
        assert match.line_range is not None
        assert "TokenValidator" in match.explanation

    def test_scan_for_duplicate_commit_match(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo), duplicate_threshold=0.65)
        match = engine.scan_for_duplicate("add system RAM monitoring metric calculator")

        assert match is not None
        assert match.is_duplicate is True
        assert match.confidence >= 0.65
        assert match.existing_commit is not None
        assert "RAM" in match.explanation

    def test_scan_for_duplicate_novel_request(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo), duplicate_threshold=0.65)
        match = engine.scan_for_duplicate("create a quantum physics particle collision simulator")

        assert match is not None
        assert match.is_duplicate is False
        assert match.confidence < 0.40

    def test_scan_for_duplicate_empty_query(self, sample_repo):
        engine = DedupEngine(repo_path=str(sample_repo))
        match = engine.scan_for_duplicate("   ")
        assert match is not None
        assert match.is_duplicate is False
        assert match.confidence == 0.0

    def test_find_duplicate_code_snippets(self, sample_repo):
        snippet = (
            "def validate_token(self, token: str) -> bool:\n"
            "    return bool(token and len(token) > 10)\n"
        )
        engine = DedupEngine(repo_path=str(sample_repo))
        matches = engine.find_duplicate_code_snippets(snippet, threshold=0.7)

        assert len(matches) >= 1
        assert matches[0]["rel_path"] == "auth.py"
        assert matches[0]["exact_match"] is True

    def test_calculate_similarity_shortcut(self):
        engine = DedupEngine()
        sim = engine.calculate_similarity("build quicksort algorithm", "quicksort algorithm implementation")
        assert sim > 0.5
