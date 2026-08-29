"""
Comprehensive unit test suite for DocRetriever (Offline DevDocs SQLite Indexer & BM25 Retriever).
Tests FTS5 virtual table creation, BM25 ranking, exact signature retrieval, token truncation limits,
performance benchmark (< 5ms latency), empty/whitespace query handling, FTS5/SQL injection safety,
and corrupt DB recovery.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List
import pytest

from k_cli.tools.doc_retriever import (
    DocRetriever,
    DEFAULT_STDLIB_MODULES,
    DEFAULT_OFFICIAL_LIBRARIES,
    OFFICIAL_DEV_DOCS,
    QueryExpander,
)


@pytest.fixture
def sample_docs() -> Dict[str, Any]:
    """Sample documentation data fixture for indexing."""
    return {
        "os.path": {
            "functions": [
                {
                    "name": "os.path.join",
                    "signature": "os.path.join(path, *paths) -> str",
                    "doc": "Join one or more path segments intelligently.",
                },
                {
                    "name": "os.path.exists",
                    "signature": "os.path.exists(path) -> bool",
                    "doc": "Test whether a path exists. Returns False for broken symbolic links.",
                },
                {
                    "name": "os.path.abspath",
                    "signature": "os.path.abspath(path) -> str",
                    "doc": "Return a normalized absolutized version of the pathname path.",
                },
            ]
        },
        "math": {
            "functions": [
                {
                    "name": "math.sqrt",
                    "signature": "math.sqrt(x: float) -> float",
                    "doc": "Return the square root of x.",
                },
                {
                    "name": "math.factorial",
                    "signature": "math.factorial(n: int) -> int",
                    "doc": "Find x!. Raise a ValueError if x is negative or non-integral.",
                },
            ]
        },
        "json": {
            "functions": [
                {
                    "name": "json.loads",
                    "signature": "json.loads(s, *, cls=None, object_hook=None) -> Any",
                    "doc": "Deserialize s (a str, bytes or bytearray instance) to a Python object.",
                },
                {
                    "name": "json.dumps",
                    "signature": "json.dumps(obj, *, indent=None) -> str",
                    "doc": "Serialize obj to a JSON formatted str.",
                },
            ]
        },
    }


class TestDocRetrieverTableCreation:
    """Test SQLite initialization, schema creation, and context management."""

    def test_fts5_table_creation(self, tmp_path: Path):
        db_file = tmp_path / "test_docs.db"
        retriever = DocRetriever(db_path=str(db_file))
        assert db_file.exists()

        # Check tables inside SQLite
        con = sqlite3.connect(str(db_file))
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        con.close()

        assert "meta" in tables
        assert "doc_entries" in tables
        retriever.close()

    def test_memory_db_initialization(self):
        retriever = DocRetriever(db_path=":memory:")
        assert retriever.db_path == ":memory:"
        count = retriever.index_module("test_mod", {"functions": [{"name": "test_fn", "signature": "test_fn()", "doc": "test"}]})
        assert count == 1
        results = retriever.search("test_fn")
        assert len(results) == 1
        assert results[0]["name"] == "test_fn"
        retriever.close()

    def test_context_manager(self, tmp_path: Path):
        db_file = tmp_path / "cm_docs.db"
        with DocRetriever(db_path=str(db_file)) as retriever:
            retriever.index_module("math", {"functions": [{"name": "math.sin", "signature": "math.sin(x)", "doc": "Sine"}]})
            res = retriever.search("sin")
            assert len(res) == 1
        # DB connection closed gracefully after context exit
        assert retriever._conn is None

    def test_missing_directory_auto_creation(self, tmp_path: Path):
        nested_db = tmp_path / "nested" / "dir" / "deeper" / "docs.db"
        retriever = DocRetriever(db_path=str(nested_db))
        assert nested_db.parent.exists()
        assert nested_db.exists()
        retriever.close()


class TestDocRetrieverIndexing:
    """Test indexing various doc_data formats and idempotency."""

    def test_index_module_with_functions_and_classes(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "index_test.db"))
        doc_data = {
            "functions": [
                {"name": "calc.add", "signature": "calc.add(a, b) -> int", "doc": "Add numbers"}
            ],
            "classes": [
                {
                    "name": "calc.Calculator",
                    "signature": "class calc.Calculator()",
                    "doc": "Calculator class",
                    "methods": [
                        {"name": "calc.Calculator.sub", "signature": "calc.Calculator.sub(a, b)", "doc": "Subtract"}
                    ],
                }
            ],
        }
        count = retriever.index_module("calc", doc_data)
        assert count == 3
        res = retriever.search("Subtract")
        assert len(res) >= 1
        assert res[0]["name"] == "calc.Calculator.sub"
        retriever.close()

    def test_index_module_with_flat_list_of_dicts(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "list_test.db"))
        items = [
            {"name": "tool.run", "signature": "tool.run(cmd: str)", "doc": "Run a tool"},
            {"name": "tool.stop", "signature": "tool.stop()", "doc": "Stop a tool"},
        ]
        count = retriever.index_module("tool", items)
        assert count == 2
        res = retriever.search("run tool")
        assert len(res) >= 1
        assert res[0]["name"] == "tool.run"
        retriever.close()

    def test_index_module_with_dict_mapping(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "map_test.db"))
        doc_map = {
            "parse_ast": {"signature": "parse_ast(code: str) -> AST", "doc": "Parse Python AST"},
            "format_code": "Format code using Black",
        }
        count = retriever.index_module("formatter", doc_map)
        assert count == 2
        res = retriever.search("Black")
        assert len(res) >= 1
        assert "format_code" in res[0]["name"]
        retriever.close()

    def test_index_empty_data_returns_zero(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "empty_test.db"))
        assert retriever.index_module("empty1", {}) == 0
        assert retriever.index_module("empty2", []) == 0
        assert retriever.index_module("empty3", None) == 0
        retriever.close()

    def test_reindexing_module_replaces_old_entries(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "reindex_test.db"))
        data_v1 = {"functions": [{"name": "mod.fn", "signature": "mod.fn(v1)", "doc": "Version 1"}]}
        data_v2 = {"functions": [{"name": "mod.fn", "signature": "mod.fn(v2)", "doc": "Version 2"}]}

        count1 = retriever.index_module("mod", data_v1)
        assert count1 == 1
        res1 = retriever.search("mod.fn")
        assert "Version 1" in res1[0]["doc"]

        count2 = retriever.index_module("mod", data_v2)
        assert count2 == 1
        res2 = retriever.search("mod.fn")
        assert len(res2) == 1
        assert "Version 2" in res2[0]["doc"]
        retriever.close()


class TestDocRetrieverBM25Search:
    """Test BM25 search ranking, result contracts, and limit options."""

    def test_bm25_exact_signature_rank_higher(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "bm25_test.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        # Exact symbol search
        results = retriever.search("os.path.join", limit=3)
        assert len(results) >= 1
        assert results[0]["name"] == "os.path.join"
        assert "os.path.join" in results[0]["signature"]
        assert results[0]["module"] == "os.path"
        assert isinstance(results[0]["score"], float)

        # Keyword semantic search
        res_sqrt = retriever.search("square root", limit=3)
        assert len(res_sqrt) >= 1
        assert res_sqrt[0]["name"] == "math.sqrt"

        # JSON deserialization search
        res_json = retriever.search("deserialize json document to python object", limit=3)
        assert len(res_json) >= 1
        assert res_json[0]["name"] == "json.loads"
        retriever.close()

    def test_search_result_dict_contract(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "contract_test.db"))
        retriever.index_module("math", sample_docs["math"])

        results = retriever.search("sqrt", limit=1)
        assert len(results) == 1
        item = results[0]

        # Verify all expected keys exist
        assert "name" in item
        assert "symbol" in item
        assert "module" in item
        assert "signature" in item
        assert "doc" in item
        assert "docstring" in item
        assert "score" in item
        assert "rank" in item

        assert item["name"] == "math.sqrt"
        assert item["module"] == "math"
        assert "sqrt" in item["signature"]
        retriever.close()

    def test_search_limits(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "limits_test.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        assert len(retriever.search("path json math", limit=1)) <= 1
        assert len(retriever.search("path json math", limit=2)) <= 2
        assert len(retriever.search("path json math", limit=0)) == 0
        assert len(retriever.search("path json math", limit=-5)) == 0
        retriever.close()


class TestDocRetrieverFormattingAndTokens:
    """Test format_context_snippets and token budget boundaries."""

    def test_format_snippets_within_token_budget(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "format_test.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        snippet = retriever.format_context_snippets("join path segments", max_tokens=250)
        assert isinstance(snippet, str)
        assert "os.path.join" in snippet
        assert len(snippet.split()) <= 250

    def test_format_snippets_zero_token_budget(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "zero_tok.db"))
        retriever.index_module("math", sample_docs["math"])

        snippet = retriever.format_context_snippets("sqrt", max_tokens=0)
        assert snippet == ""
        snippet_neg = retriever.format_context_snippets("sqrt", max_tokens=-10)
        assert snippet_neg == ""

    def test_format_snippets_one_token_budget(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "one_tok.db"))
        retriever.index_module("math", sample_docs["math"])

        snippet = retriever.format_context_snippets("sqrt", max_tokens=1)
        assert len(snippet.split()) <= 5

    def test_format_snippets_large_budget(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "large_tok.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        snippet = retriever.format_context_snippets("json", max_tokens=5000)
        assert "json.loads" in snippet or "json.dumps" in snippet


class TestDocRetrieverRobustnessAndSafety:
    """Test safety against FTS5 special characters, SQL injection, corrupted databases, and empty queries."""

    def test_empty_and_whitespace_queries(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "empty_q.db"))
        retriever.index_module("math", sample_docs["math"])

        assert retriever.search("") == []
        assert retriever.search("   ") == []
        assert retriever.search("\n\t  \r\n") == []
        assert retriever.search("!@#$%^&*()_+=-`~[]{}|;:'\",.<>?/") == []
        assert retriever.format_context_snippets("") == ""
        assert retriever.format_context_snippets("   ") == ""
        retriever.close()

    def test_fts5_special_syntax_sanitization(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "fts5_sanitize.db"))
        retriever.index_module("os.path", sample_docs["os.path"])

        dangerous_queries = [
            'AND OR NOT NEAR() * : ^ ""',
            'MATCH "foo*bar"',
            'path:join OR (exists NOT)',
            '"""',
            "***",
            "(((((((()))))))",
            "SELECT * FROM doc_entries",
            "NEAR(a, b, 10)",
        ]
        for q in dangerous_queries:
            results = retriever.search(q, limit=3)
            assert isinstance(results, list)
            snippets = retriever.format_context_snippets(q, max_tokens=250)
            assert isinstance(snippets, str)
        retriever.close()

    def test_sql_injection_safety(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "sqli.db"))
        retriever.index_module("math", sample_docs["math"])

        sqli_queries = [
            "'; DROP TABLE doc_entries; --",
            "' OR '1'='1",
            "'; DELETE FROM doc_entries; --",
            "1; SELECT * FROM meta",
        ]
        for q in sqli_queries:
            results = retriever.search(q, limit=3)
            assert isinstance(results, list)

        # Verify database is intact and functional
        after = retriever.search("sqrt", limit=3)
        assert len(after) >= 1
        assert after[0]["name"] == "math.sqrt"
        retriever.close()

    def test_corrupt_database_recovery(self, tmp_path: Path):
        db_file = tmp_path / "corrupt.db"
        # Write corrupted garbage bytes to file
        db_file.write_bytes(b"INVALID_SQLITE_HEADER_CORRUPTED_BYTES_1234567890\x00\xff\xfe")

        # DocRetriever must recover cleanly
        retriever = DocRetriever(db_path=str(db_file))
        assert retriever._conn is not None

        # Verify indexing and searching works after recovery
        count = retriever.index_module("math", {"functions": [{"name": "math.cos", "signature": "math.cos(x)", "doc": "Cosine"}]})
        assert count == 1
        res = retriever.search("cos")
        assert len(res) == 1
        assert res[0]["name"] == "math.cos"
        retriever.close()


class TestDocRetrieverStdlibAndPerformance:
    """Test stdlib auto-indexing and sub-5ms query latency performance."""

    def test_index_stdlib_subset(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "stdlib_test.db"))
        modules = ["json", "math", "pathlib"]
        count = retriever.index_stdlib(modules=modules)
        assert count > 10

        # Check retrieval of real signatures
        res_json = retriever.search("json.loads", limit=1)
        assert len(res_json) >= 1
        assert "json.loads" in res_json[0]["name"]

        res_path = retriever.search("Path.exists", limit=1)
        assert len(res_path) >= 1
        assert "exists" in res_path[0]["name"] or "pathlib" in res_path[0]["module"]
        retriever.close()

    def test_search_latency_under_5ms(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "latency_bench.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        latencies = []
        queries = ["os.path.join", "math.sqrt", "json.loads", "exists", "factorial"] * 20
        for q in queries:
            start = time.perf_counter()
            retriever.search(q, limit=3, max_tokens=250)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

        mean_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        assert mean_latency < 5.0, f"Mean latency exceeded 5ms: {mean_latency:.3f} ms"
        assert p95_latency < 10.0, f"P95 latency exceeded 10ms: {p95_latency:.3f} ms"
        retriever.close()

    def test_database_size_and_memory_footprint(self, tmp_path: Path):
        db_file = tmp_path / "size_bench.db"
        retriever = DocRetriever(db_path=str(db_file))
        # Index key common modules
        retriever.index_stdlib(modules=["json", "math", "os", "sys", "re", "collections", "itertools", "dataclasses", "functools"])

        # Check DB file size is < 10MB
        db_size_mb = db_file.stat().st_size / (1024 * 1024)
        assert db_size_mb < 10.0, f"Database file size exceeded 10MB: {db_size_mb:.2f} MB"
        retriever.close()


class TestHybridRetrievalAndCosineRanking:
    """Test BM25 lexical matching combined with semantic cosine similarity ranking."""

    def test_hybrid_search_scoring_contract(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "hybrid_contract.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        results = retriever.search("join path segments", limit=3, hybrid=True, alpha=0.5)
        assert len(results) >= 1
        top = results[0]

        # Verify extended hybrid score fields
        assert "name" in top
        assert "signature" in top
        assert "doc" in top
        assert "score" in top
        assert "rank" in top
        assert "bm25_score" in top
        assert "cosine_sim" in top
        assert "hybrid_score" in top

        assert isinstance(top["bm25_score"], float)
        assert isinstance(top["cosine_sim"], float)
        assert isinstance(top["hybrid_score"], float)
        assert 0.0 <= top["cosine_sim"] <= 1.0
        assert 0.0 <= top["hybrid_score"] <= 1.0
        assert top["name"] == "os.path.join"
        retriever.close()

    def test_hybrid_alpha_weighting(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "alpha_test.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        # Pure BM25 (alpha = 1.0)
        res_bm25 = retriever.search("sqrt", limit=1, hybrid=True, alpha=1.0)
        assert len(res_bm25) == 1
        assert res_bm25[0]["name"] == "math.sqrt"

        # Pure Semantic Cosine (alpha = 0.0)
        res_sem = retriever.search("square root of a float number", limit=1, hybrid=True, alpha=0.0)
        assert len(res_sem) == 1
        assert res_sem[0]["name"] == "math.sqrt"
        assert res_sem[0]["cosine_sim"] > 0.0

        # Balanced Hybrid (alpha = 0.5)
        res_hyb = retriever.search("deserialize json string", limit=1, hybrid=True, alpha=0.5)
        assert len(res_hyb) == 1
        assert res_hyb[0]["name"] == "json.loads"
        retriever.close()

    def test_semantic_matching_on_descriptive_queries(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "semantic_desc.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        # Natural language descriptive query
        res = retriever.search("calculate the factorial of positive integer", limit=1, hybrid=True)
        assert len(res) >= 1
        assert res[0]["name"] == "math.factorial"
        assert res[0]["cosine_sim"] > 0.1
        retriever.close()


class TestOfficialStandardLibrariesIntegration:
    """Test indexing and precision retrieval across official stdlibs and frameworks."""

    def test_index_all_official_libraries(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "official_libs.db"))
        count = retriever.index_official_libraries()
        assert count >= 40

        for lib_key in DEFAULT_OFFICIAL_LIBRARIES:
            res = retriever.search(lib_key, limit=5)
            assert len(res) >= 1
        retriever.close()

    def test_query_python_312_features(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "py312.db"))
        retriever.index_official_libraries(libraries=["python"])

        # TaskGroup (3.11+)
        res_tg = retriever.search("TaskGroup", limit=1)
        assert len(res_tg) == 1
        assert "TaskGroup" in res_tg[0]["name"]

        # Annotated typing
        res_ann = retriever.search("Annotated", limit=1)
        assert len(res_ann) == 1
        assert "Annotated" in res_ann[0]["name"]

        # Self type
        res_self = retriever.search("typing.Self", limit=1)
        assert len(res_self) == 1
        assert "Self" in res_self[0]["name"]
        retriever.close()

    def test_query_cpp23_features(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "cpp23.db"))
        retriever.index_official_libraries(libraries=["cpp"])

        # std::expected
        res_exp = retriever.search("expected", limit=1)
        assert len(res_exp) == 1
        assert "expected" in res_exp[0]["name"]

        # std::print
        res_print = retriever.search("print", limit=1)
        assert len(res_print) == 1
        assert "print" in res_print[0]["name"]

        # std::vector::emplace_back
        res_vec = retriever.search("emplace_back", limit=1)
        assert len(res_vec) == 1
        assert "emplace_back" in res_vec[0]["name"]
        retriever.close()

    def test_query_rust180_features(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "rust180.db"))
        retriever.index_official_libraries(libraries=["rust"])

        # std::sync::Arc
        res_arc = retriever.search("Arc", limit=1)
        assert len(res_arc) == 1
        assert "Arc" in res_arc[0]["name"]

        # tokio::spawn
        res_tokio = retriever.search("tokio::spawn", limit=1)
        assert len(res_tokio) == 1
        assert "tokio::spawn" in res_tokio[0]["name"]

        # Mutex::lock
        res_mutex = retriever.search("Mutex::lock", limit=1)
        assert len(res_mutex) == 1
        assert "Mutex" in res_mutex[0]["name"]
        retriever.close()

    def test_query_linux_syscalls(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "linux_sys.db"))
        retriever.index_official_libraries(libraries=["linux_syscalls"])

        # epoll_create1
        res_epoll = retriever.search("epoll_create1", limit=1)
        assert len(res_epoll) == 1
        assert "epoll_create1" in res_epoll[0]["name"]

        # io_uring_setup
        res_uring = retriever.search("io_uring_setup", limit=1)
        assert len(res_uring) == 1
        assert "io_uring_setup" in res_uring[0]["name"]

        # futex
        res_futex = retriever.search("futex", limit=1)
        assert len(res_futex) == 1
        assert "futex" in res_futex[0]["name"]
        retriever.close()

    def test_query_fastapi_framework(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "fastapi.db"))
        retriever.index_official_libraries(libraries=["fastapi"])

        # Depends
        res_dep = retriever.search("Depends", limit=1)
        assert len(res_dep) == 1
        assert "Depends" in res_dep[0]["name"]

        # HTTPException
        res_exc = retriever.search("HTTPException", limit=1)
        assert len(res_exc) == 1
        assert "HTTPException" in res_exc[0]["name"]

        # BackgroundTasks
        res_bg = retriever.search("BackgroundTasks", limit=1)
        assert len(res_bg) == 1
        assert "BackgroundTasks" in res_bg[0]["name"]
        retriever.close()

    def test_query_redis_and_postgresql(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "data_stores.db"))
        retriever.index_official_libraries(libraries=["redis", "postgresql"])

        # Redis set with NX
        res_redis = retriever.search("Redis.set", limit=1)
        assert len(res_redis) == 1
        assert "Redis.set" in res_redis[0]["name"]

        # PostgreSQL asyncpg create_pool
        res_pg = retriever.search("asyncpg.create_pool", limit=1)
        assert len(res_pg) == 1
        assert "create_pool" in res_pg[0]["name"]
        retriever.close()


class TestQueryExpansionAndContextInjection:
    """Test query expansion rules and context snippet injection into orchestrator prompts."""

    def test_expand_query_synonyms(self):
        exp_fastapi = QueryExpander.expand("fastapi endpoint route")
        assert "APIRouter" in exp_fastapi
        assert "FastAPI" in exp_fastapi

        exp_redis = QueryExpander.expand("redis distributed lock")
        assert "SET NX EX" in exp_redis or "Mutex" in exp_redis

        exp_linux = QueryExpander.expand("linux epoll syscall")
        assert "epoll_create1" in exp_linux
        assert "epoll_ctl" in exp_linux

    def test_format_context_snippets_with_expansion(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "expansion_snip.db"))
        retriever.index_official_libraries(libraries=["fastapi", "redis", "postgresql"])

        snippet = retriever.format_context_snippets("fastapi async endpoint dependency", max_tokens=250)
        assert isinstance(snippet, str)
        assert "Depends" in snippet or "APIRouter" in snippet or "FastAPI" in snippet
        retriever.close()

    def test_inject_doc_snippets_orchestrator_prompt(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "inject_snip.db"))
        retriever.index_official_libraries(libraries=["fastapi", "postgresql"])

        user_prompt = "Build a FastAPI route using dependency injection and PostgreSQL connection pool."
        injected = retriever.inject_doc_snippets(user_prompt, language="python", max_tokens=300)

        assert isinstance(injected, str)
        assert "### DevDocs Reference Snippets" in injected
        assert "Depends" in injected or "create_pool" in injected or "APIRouter" in injected
        assert len(injected.split()) <= 320
        retriever.close()

    def test_inject_doc_snippets_empty_and_zero_budget(self, tmp_path: Path):
        retriever = DocRetriever(db_path=str(tmp_path / "inject_empty.db"))
        retriever.index_official_libraries(libraries=["python"])

        assert retriever.inject_doc_snippets("", max_tokens=250) == ""
        assert retriever.inject_doc_snippets("   ", max_tokens=250) == ""
        assert retriever.inject_doc_snippets("asyncio", max_tokens=0) == ""
        assert retriever.inject_doc_snippets("asyncio", max_tokens=-5) == ""
        retriever.close()


class TestHighEfficiencyLocalCaching:
    """Test thread-safe LRU caching, cache statistics, and sub-millisecond retrieval on cache hits."""

    def test_lru_cache_hits_and_misses(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "cache_hits.db"), enable_cache=True, cache_size=64)
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        retriever.clear_cache()
        stats_initial = retriever.cache_stats()
        assert stats_initial["hits"] == 0
        assert stats_initial["misses"] == 0
        assert stats_initial["size"] == 0

        # First query (miss)
        res1 = retriever.search("os.path.join", limit=2)
        assert len(res1) >= 1
        stats_after_1 = retriever.cache_stats()
        assert stats_after_1["misses"] == 1
        assert stats_after_1["hits"] == 0
        assert stats_after_1["size"] == 1

        # Second query with identical arguments (hit)
        res2 = retriever.search("os.path.join", limit=2)
        assert len(res2) == len(res1)
        assert res2[0]["name"] == res1[0]["name"]
        stats_after_2 = retriever.cache_stats()
        assert stats_after_2["hits"] == 1
        assert stats_after_2["hit_rate"] == 0.5
        retriever.close()

    def test_cache_clearing(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "cache_clear.db"))
        retriever.index_module("math", sample_docs["math"])

        retriever.search("math.sqrt")
        retriever.search("math.sqrt")
        assert retriever.cache_stats()["hits"] >= 1

        retriever.clear_cache()
        stats = retriever.cache_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        retriever.close()

    def test_cache_latency_under_1ms_on_hit(self, tmp_path: Path, sample_docs: Dict[str, Any]):
        retriever = DocRetriever(db_path=str(tmp_path / "cache_lat.db"))
        for mod, data in sample_docs.items():
            retriever.index_module(mod, data)

        # Warmup query into cache
        retriever.search("json.loads", limit=3)

        hit_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            res = retriever.search("json.loads", limit=3)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hit_latencies.append(elapsed_ms)
            assert len(res) >= 1

        mean_hit_ms = sum(hit_latencies) / len(hit_latencies)
        assert mean_hit_ms < 0.5, f"Cache hit latency exceeded 0.5ms: {mean_hit_ms:.3f} ms"
        retriever.close()

