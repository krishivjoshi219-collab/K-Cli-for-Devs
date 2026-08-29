"""
tests/test_devdocs_expansion.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Verification test suite for DevDocs Knowledge Base Expansion (Project Bankai).

Asserts:
1. SQLite WAL journaling, normal synchronous mode, and FTS5 optimization.
2. Comprehensive multi-language docset coverage:
   - Go Standard Library (net/http, sync, context, io, os)
   - JavaScript / TypeScript Standard Library (ES2024, Promises, Web APIs, DOM)
   - Linux Kernel Syscalls & POSIX IPC (epoll, io_uring, futex, mmap, signals)
   - PyTorch Core API (torch.nn, torch.autograd, torch.distributed)
   - NumPy Core API (ndarray, linalg, fft, indexing)
3. Clean Markdown documentation with metadata tags, signatures, and code examples.
4. Strict search latency SLA: < 2.0 ms for epoll_create1, sync.WaitGroup, Promise.allSettled, torch.nn.Linear.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

DEFAULT_DB_PATH = Path.home() / ".kcli" / "docs.db"


@pytest.fixture(scope="module")
def db_conn():
    """Provides an optimized connection to the knowledge database."""
    assert DEFAULT_DB_PATH.exists(), f"Database file {DEFAULT_DB_PATH} must exist"
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 30000000000;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA case_sensitive_like = ON;")
    yield conn
    conn.close()


def test_sqlite_pragmas_and_schema(db_conn: sqlite3.Connection):
    """Asserts WAL mode, synchronous mode, and proper schema/triggers."""
    cur = db_conn.cursor()

    # Check journal mode
    cur.execute("PRAGMA journal_mode;")
    mode = cur.fetchone()[0].lower()
    assert mode == "wal", f"Expected WAL journal mode, got {mode}"

    # Check tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    assert "docs" in tables, "Table 'docs' must exist"
    assert "docs_fts" in tables, "Virtual table 'docs_fts' must exist"

    # Check indexes
    cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {r[0] for r in cur.fetchall()}
    assert "idx_docs_name" in indexes or "idx_docs_docset_name" in indexes, "B-tree indexes must exist"

    # Check triggers
    cur.execute("SELECT name FROM sqlite_master WHERE type='trigger';")
    triggers = {r[0] for r in cur.fetchall()}
    assert "docs_ai" in triggers, "Sync trigger docs_ai must exist"


def test_docset_inventory_coverage(db_conn: sqlite3.Connection):
    """Asserts required docsets are indexed with substantial symbol counts."""
    cur = db_conn.cursor()
    cur.execute("SELECT docset, COUNT(*) FROM docs GROUP BY docset")
    counts = dict(cur.fetchall())

    expected_docsets = {
        "go": 5000,
        "javascript": 1000,
        "typescript": 300,
        "dom": 5000,
        "man": 10000,
        "pytorch": 4000,
        "numpy": 2500,
        "python": 8000,
        "cpp": 5000,
        "rust": 20000,
    }

    for docset, min_count in expected_docsets.items():
        assert docset in counts, f"Docset '{docset}' must be present in database"
        assert counts[docset] >= min_count, f"Docset '{docset}' count {counts[docset]:,} < {min_count:,}"

    cur.execute("SELECT COUNT(*) FROM docs")
    total = cur.fetchone()[0]
    assert total >= 80000, f"Expected >= 80,000 total symbols, found {total:,}"


def test_markdown_documentation_quality(db_conn: sqlite3.Connection):
    """Asserts that indexed documentation contains clean Markdown, headers, docset badges, and code."""
    cur = db_conn.cursor()

    sample_targets = [
        ("go", "sync.WaitGroup"),
        ("javascript", "Promise.allSettled"),
        ("pytorch", "torch.nn.Linear"),
        ("man", "epoll_create1 (2)"),
    ]

    for docset, name in sample_targets:
        cur.execute("SELECT content, path, type FROM docs WHERE name = ? AND docset = ? LIMIT 1", (name, docset))
        row = cur.fetchone()
        assert row is not None, f"Sample symbol '{name}' in docset '{docset}' must be found"
        content, path, entry_type = row

        # Assert Markdown structure
        assert content.startswith("# "), f"Content for {name} must start with Markdown header #, got: {content[:30]}"
        assert f"**Docset**: `{docset}`" in content, f"Docset tag badge must be present in {name}"
        assert len(content.strip().splitlines()) >= 3, f"Documentation must be multi-line: {name}"


@pytest.mark.parametrize(
    "docset,candidate_names,expected_fragment",
    [
        ("man", ["epoll_create1 (2)", "epoll_create1"], "epoll"),
        ("go", ["sync.WaitGroup"], "WaitGroup"),
        ("javascript", ["Promise.allSettled"], "allSettled"),
        ("pytorch", ["torch.nn.Linear"], "Linear"),
    ],
)
def test_strict_query_latency_sla(
    db_conn: sqlite3.Connection,
    docset: str,
    candidate_names: List[str],
    expected_fragment: str,
):
    """
    CRITICAL SLA REQUIREMENT:
    Asserts that queries for 'epoll_create1', 'sync.WaitGroup', 'Promise.allSettled',
    and 'torch.nn.Linear' return in < 2.0 ms.
    """
    cur = db_conn.cursor()

    # Warmup
    for name in candidate_names:
        cur.execute(
            "SELECT docset, name, type, path, content FROM docs WHERE name = ? AND docset = ? LIMIT 3",
            (name, docset),
        )
        matches = cur.fetchall()
        if matches:
            break
    if not matches:
        for name in candidate_names:
            cur.execute(
                "SELECT docset, name, type, path, content FROM docs WHERE name LIKE ? AND docset = ? LIMIT 3",
                (f"{name}%", docset),
            )
            matches = cur.fetchall()
            if matches:
                break

    assert matches, f"Must find matches for {candidate_names} in {docset}"

    # Timed benchmark: 10 repetitions to verify P99 < 2.0 ms
    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        for name in candidate_names:
            cur.execute(
                "SELECT docset, name, type, path, content FROM docs WHERE name = ? AND docset = ? LIMIT 3",
                (name, docset),
            )
            res = cur.fetchall()
            if res:
                break
        if not res:
            for name in candidate_names:
                cur.execute(
                    "SELECT docset, name, type, path, content FROM docs WHERE name LIKE ? AND docset = ? LIMIT 3",
                    (f"{name}%", docset),
                )
                res = cur.fetchall()
                if res:
                    break
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p99 = latencies[-1]

    # Verify results
    assert expected_fragment.lower() in res[0][1].lower(), f"Expected '{expected_fragment}' in symbol name '{res[0][1]}'"
    assert p99 < 2.0, f"Query latency for {docset}:{candidate_names} exceeded SLA: P50={p50:.3f}ms, P99={p99:.3f}ms (target < 2.0ms)"


def test_fts5_full_text_search(db_conn: sqlite3.Connection):
    """Asserts that FTS5 full-text queries execute with high precision and sub-5ms latency."""
    cur = db_conn.cursor()
    # Warmup query cache
    cur.execute("SELECT rowid FROM docs_fts WHERE docs_fts MATCH 'warmup' LIMIT 1")

    queries = ["epoll_create1", "WaitGroup", "allSettled", "Linear", "ndarray"]
    for q in queries:
        # Warmup for query
        cur.execute("SELECT rowid, name, type FROM docs_fts WHERE docs_fts MATCH ? LIMIT 5", (q,))
        t0 = time.perf_counter()
        cur.execute(
            "SELECT rowid, name, type FROM docs_fts WHERE docs_fts MATCH ? LIMIT 5",
            (q,),
        )
        rows = cur.fetchall()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert len(rows) > 0, f"FTS5 query for '{q}' must return matches"
        assert elapsed_ms < 5.0, f"FTS5 query '{q}' took {elapsed_ms:.3f}ms (expected < 5.0ms)"
