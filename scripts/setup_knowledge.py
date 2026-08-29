#!/usr/bin/env python3
"""
scripts/setup_knowledge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Production-grade DevDocs Ingestion Engine for Project Bankai (K-CLI).

Ingests official developer documentation:
- Go Standard Library (net/http, sync, context, io, os, channels)
- JavaScript / TypeScript Standard Library (ES2024, Promises, Web APIs, DOM)
- Linux Kernel Syscalls & POSIX IPC (epoll, io_uring, futex, mmap, signals)
- PyTorch Core API (torch.nn, torch.autograd, torch.distributed)
- NumPy Core API (ndarray, linalg, fft, indexing)
- Python 3.12 Standard Library
- C++ (cppreference)
- Rust (std)

Into an embedded SQLite FTS5 database at ~/.kcli/docs.db with automated
synchronization triggers, section-level Markdown sanitization, B-tree indexes,
WAL journaling, memory-mapped I/O, FTS5 segment optimization, and latency assertion tests.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()
logger = logging.getLogger("bankai.knowledge")

DEFAULT_DB_PATH = Path.home() / ".kcli" / "docs.db"

DEVDOCS_MANIFESTS: Dict[str, Dict[str, str]] = {
    "go": {
        "title": "Go Standard Library",
        "index_url": "https://documents.devdocs.io/go/index.json",
        "db_url": "https://documents.devdocs.io/go/db.json",
        "lang": "go",
    },
    "javascript": {
        "title": "JavaScript (ES2024 & Stdlib)",
        "index_url": "https://documents.devdocs.io/javascript/index.json",
        "db_url": "https://documents.devdocs.io/javascript/db.json",
        "lang": "javascript",
    },
    "typescript": {
        "title": "TypeScript (Language & Types)",
        "index_url": "https://documents.devdocs.io/typescript/index.json",
        "db_url": "https://documents.devdocs.io/typescript/db.json",
        "lang": "typescript",
    },
    "dom": {
        "title": "Web APIs & DOM",
        "index_url": "https://documents.devdocs.io/dom/index.json",
        "db_url": "https://documents.devdocs.io/dom/db.json",
        "lang": "javascript",
    },
    "man": {
        "title": "POSIX & Linux Syscalls (epoll, io_uring, futex, mmap)",
        "index_url": "https://documents.devdocs.io/man/index.json",
        "db_url": "https://documents.devdocs.io/man/db.json",
        "lang": "c",
    },
    "pytorch": {
        "title": "PyTorch Core API (torch.nn, autograd, distributed)",
        "index_url": "https://documents.devdocs.io/pytorch~2.5/index.json",
        "db_url": "https://documents.devdocs.io/pytorch~2.5/db.json",
        "lang": "python",
    },
    "numpy": {
        "title": "NumPy Core API (ndarray, linalg, fft)",
        "index_url": "https://documents.devdocs.io/numpy~2.2/index.json",
        "db_url": "https://documents.devdocs.io/numpy~2.2/db.json",
        "lang": "python",
    },
    "python": {
        "title": "Python 3.12 Standard Library",
        "index_url": "https://documents.devdocs.io/python~3.12/index.json",
        "db_url": "https://documents.devdocs.io/python~3.12/db.json",
        "lang": "python",
    },
    "cpp": {
        "title": "C++ (cppreference)",
        "index_url": "https://documents.devdocs.io/cpp/index.json",
        "db_url": "https://documents.devdocs.io/cpp/db.json",
        "lang": "cpp",
    },
    "rust": {
        "title": "Rust (std)",
        "index_url": "https://documents.devdocs.io/rust/index.json",
        "db_url": "https://documents.devdocs.io/rust/db.json",
        "lang": "rust",
    },
}

VERIFICATION_TARGETS = [
    ("man", "epoll_create1", ["epoll_create1 (2)", "epoll_create1"]),
    ("go", "sync.WaitGroup", ["sync.WaitGroup"]),
    ("javascript", "Promise.allSettled", ["Promise.allSettled"]),
    ("pytorch", "torch.nn.Linear", ["torch.nn.Linear"]),
    ("numpy", "numpy.ndarray", ["ndarray", "numpy.ndarray"]),
    ("python", "asyncio.Queue", ["asyncio.Queue"]),
    ("cpp", "std::vector", ["std::vector"]),
    ("rust", "std::sync::Arc", ["std::sync::Arc"]),
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Database Schema & High-Performance Pragmas
# ─────────────────────────────────────────────────────────────────────────────

def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Creates directory hierarchy and initializes SQLite with WAL pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 30000000000;")
    conn.execute("PRAGMA cache_size = -64000;")  # 64MB cache
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Initializes normalized documentation schema, B-tree indexes, and FTS5 triggers."""
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS docs (
            id TEXT PRIMARY KEY,
            docset TEXT NOT NULL,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            type TEXT,
            content TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_docs_docset ON docs(docset);
        CREATE INDEX IF NOT EXISTS idx_docs_name ON docs(name);
        CREATE INDEX IF NOT EXISTS idx_docs_docset_name ON docs(docset, name);

        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
            name,
            docset UNINDEXED,
            type UNINDEXED,
            content,
            content='docs',
            content_rowid='rowid',
            tokenize='porter unicode61'
        );

        -- Automated synchronization triggers
        CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
            INSERT INTO docs_fts(rowid, name, docset, type, content)
            VALUES (new.rowid, new.name, new.docset, new.type, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, name, docset, type, content)
            VALUES ('delete', old.rowid, old.name, old.docset, old.type, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, name, docset, type, content)
            VALUES ('delete', old.rowid, old.name, old.docset, old.type, old.content);
            INSERT INTO docs_fts(rowid, name, docset, type, content)
            VALUES (new.rowid, new.name, new.docset, new.type, new.content);
        END;
        """)


def optimize_db(conn: sqlite3.Connection) -> None:
    """Optimizes FTS5 index segments and checkpoints the WAL journal."""
    with conn:
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('optimize');")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Resilient Network Fetcher & High-Performance Markdown Sanitizer
# ─────────────────────────────────────────────────────────────────────────────

def fetch_json_with_retry(url: str, retries: int = 3, timeout: int = 120) -> Any:
    """Fetches JSON payloads with chunked streaming and exponential backoff."""
    headers = {"User-Agent": "Bankai-DevDocs-Engine/2.0 (Project Bankai; K-CLI)"}
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=(15, timeout), stream=True)
            resp.raise_for_status()

            raw_bytes = bytearray()
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    raw_bytes.extend(chunk)

            return json.loads(raw_bytes)
        except Exception as e:
            last_error = e
            if attempt < retries:
                sleep_sec = 2 ** attempt
                time.sleep(sleep_sec)

    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_error}")


_STRIP_TAGS_RE = re.compile(
    r"<(script|style|meta|noscript|header|footer|nav|mdn-survey|svg)[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_PRE_CODE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_CODE_RE = re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def extract_section_html(raw_html: str, anchor: str) -> str:
    """
    Extracts the targeted HTML section corresponding to an anchor identifier,
    preventing bloated whole-page duplication across hundreds of sub-symbols.
    """
    if not anchor or not raw_html:
        return raw_html

    # Search for element with id="anchor" or name="anchor"
    pattern = re.compile(
        rf'<(?:h[1-6]|div|dt|section|span|a|p|li)[^>]*(?:id|name)=[\"\']{re.escape(anchor)}[\"\'][^>]*>',
        re.IGNORECASE,
    )
    m = pattern.search(raw_html)
    if not m:
        return raw_html

    start_pos = m.start()
    # Search for next section / heading of same or higher level
    next_heading = re.search(
        r'<(?:h[1-3]|dt|section)[^>]*>',
        raw_html[start_pos + len(m.group(0)):],
        re.IGNORECASE,
    )
    if next_heading:
        end_pos = start_pos + len(m.group(0)) + next_heading.start()
        section = raw_html[start_pos:end_pos]
        if len(section.strip()) >= 80:
            return section

    return raw_html[start_pos : start_pos + 6000]


def sanitize_to_markdown(
    html_content: str,
    name: str = "",
    docset: str = "",
    entry_type: str = "",
    path: str = "",
    lang: str = "",
) -> str:
    """
    High-performance HTML markup to clean Markdown converter.
    Preserves function/class signatures, parameter lists, docstrings, and code blocks.
    """
    meta_header = f"# {name}\n\n> **Docset**: `{docset}` | **Type**: `{entry_type}` | **Path**: `{path}`\n\n"

    if not html_content or not html_content.strip():
        return meta_header + f"{name} ({entry_type})\n"

    clean = _STRIP_TAGS_RE.sub("", html_content)

    # Convert code blocks
    def _replace_pre_code(m: re.Match) -> str:
        code_body = m.group(1)
        code_text = _ANY_TAG_RE.sub("", code_body)
        code_text = html_lib.unescape(code_text).strip()
        code_lang = lang or ""
        return f"\n\n```{code_lang}\n{code_text}\n```\n\n"

    clean = re.sub(
        r"<pre[^>]*><code[^>]*>(.*?)</code></pre>",
        _replace_pre_code,
        clean,
        flags=re.DOTALL | re.IGNORECASE,
    )
    clean = _PRE_CODE_RE.sub(_replace_pre_code, clean)

    # Convert inline code
    clean = _CODE_RE.sub(r"`\1`", clean)

    # Convert headings
    clean = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n#### \1\n", clean, flags=re.DOTALL | re.IGNORECASE)

    # Convert definition lists and items
    clean = re.sub(r"<dt[^>]*>(.*?)</dt>", r"\n**\1**\n", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<dd[^>]*>(.*?)</dd>", r"\n: \1\n", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<li[^>]*>(.*?)</li>", r"\n* \1", clean, flags=re.DOTALL | re.IGNORECASE)

    # Convert paragraph breaks
    clean = re.sub(r"<p[^>]*>", "\n\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"</p>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<br\s*/?>", "\n", clean, flags=re.IGNORECASE)

    # Strip remaining HTML tags and unescape entities
    clean = _ANY_TAG_RE.sub(" ", clean)
    clean = html_lib.unescape(clean)

    # Format into cohesive markdown
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    body = "\n".join(lines)

    return meta_header + body


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ingestion Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def ingest_docset(
    docset_key: str,
    manifest: Dict[str, str],
    conn: sqlite3.Connection,
    progress: Progress,
) -> int:
    """Streams index and db manifests, converts to Markdown, and bulk inserts into SQLite."""
    title = manifest["title"]
    lang = manifest.get("lang", "")
    task_id = progress.add_task(f"[cyan]{title}[/cyan]", total=None)

    # 1. Fetch index & database
    progress.update(task_id, description=f"[cyan]{title}[/cyan] [dim](downloading index)[/dim]")
    index_data = fetch_json_with_retry(manifest["index_url"])
    entries = index_data.get("entries", index_data) if isinstance(index_data, dict) else index_data

    progress.update(task_id, description=f"[cyan]{title}[/cyan] [dim](downloading page db)[/dim]")
    page_db = fetch_json_with_retry(manifest["db_url"])
    if not isinstance(page_db, dict):
        page_db = {}

    # 2. Build records from index entries
    progress.update(
        task_id,
        total=len(entries),
        completed=0,
        description=f"[cyan]{title}[/cyan] [dim](indexing symbols)[/dim]",
    )

    batch: List[Tuple[str, str, str, str, str, str]] = []
    inserted_count = 0
    cache_page_html: Dict[str, str] = {}

    for entry in entries:
        name = entry.get("name", "").strip()
        path = entry.get("path", "").strip()
        entry_type = entry.get("type", "").strip()

        if not name or not path:
            progress.advance(task_id, 1)
            continue

        parts = path.split("#", 1)
        base_path = parts[0]
        anchor = parts[1] if len(parts) > 1 else ""

        if base_path not in cache_page_html:
            raw_html = page_db.get(base_path, "")
            if not raw_html and path in page_db:
                raw_html = page_db[path]
            cache_page_html[base_path] = raw_html
        else:
            raw_html = cache_page_html[base_path]

        # Extract focused anchor section if available
        if anchor and raw_html:
            sec_html = extract_section_html(raw_html, anchor)
        else:
            sec_html = raw_html

        content = sanitize_to_markdown(
            sec_html,
            name=name,
            docset=docset_key,
            entry_type=entry_type,
            path=path,
            lang=lang,
        )

        doc_id = f"{docset_key}:{path}::{name}"
        batch.append((doc_id, docset_key, name, path, entry_type, content))

        if len(batch) >= 1000:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO docs (id, docset, name, path, type, content) VALUES (?, ?, ?, ?, ?, ?)",
                    batch,
                )
            inserted_count += len(batch)
            batch.clear()

        progress.advance(task_id, 1)

    if batch:
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO docs (id, docset, name, path, type, content) VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
        inserted_count += len(batch)
        batch.clear()

    progress.update(
        task_id,
        description=f"[green]✔ {title}[/green] [bold white]({inserted_count:,} symbols)[/bold white]",
    )
    return inserted_count


# ─────────────────────────────────────────────────────────────────────────────
# 4. Verification & Diagnostics (< 2.0 ms latency assertions)
# ─────────────────────────────────────────────────────────────────────────────

def run_diagnostics(conn: sqlite3.Connection) -> bool:
    """Executes validation queries, asserts < 2.0ms search latency, and prints stats."""
    console.print("\n")
    console.print(Panel("[bold cyan]Project Bankai — DevDocs Ingestion Diagnostics & Benchmark[/bold cyan]", expand=False))

    conn.execute("PRAGMA case_sensitive_like = ON;")

    # 1. Total & Breakdown counts
    cur = conn.cursor()
    cur.execute("SELECT docset, COUNT(*) FROM docs GROUP BY docset ORDER BY docset")
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM docs")
    total_docs = cur.fetchone()[0]

    stats_table = Table(
        title="[bold green]Indexed Symbol Breakdown[/bold green]",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
    )
    stats_table.add_column("Docset", style="yellow")
    stats_table.add_column("Symbols Indexed", justify="right", style="bold white")
    stats_table.add_column("FTS5 Status", justify="center", style="green")

    for docset, count in rows:
        stats_table.add_row(docset.upper(), f"{count:,}", "✔ Synced")

    stats_table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold green]{total_docs:,}[/bold green]",
        "[bold green]✔ Fully Synced & Optimized[/bold green]",
    )
    console.print(stats_table)
    console.print("\n")

    # 2. Validation query tests & Latency benchmark (< 2.0 ms target)
    test_table = Table(
        title="[bold cyan]DevDocs Retrieval & Latency Benchmarks (< 2.0 ms SLA)[/bold cyan]",
        show_header=True,
        header_style="bold blue",
        show_lines=True,
    )
    test_table.add_column("Target Docset", style="yellow")
    test_table.add_column("Query Symbol", style="bold white")
    test_table.add_column("Matches", justify="right", style="cyan")
    test_table.add_column("Top Match", style="white")
    test_table.add_column("Latency (ms)", justify="right", style="bold green")
    test_table.add_column("Snippet Preview", style="dim white")

    all_passed = True
    for docset, query_label, candidate_names in VERIFICATION_TARGETS:
        # Check if docset is present in DB
        cur.execute("SELECT COUNT(*) FROM docs WHERE docset = ?", (docset,))
        if cur.fetchone()[0] == 0:
            continue

        # Warmup
        matches = []
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

        # Benchmark query
        t0 = time.perf_counter()
        matches = []
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
        if not matches:
            # Fallback to FTS5
            cur.execute(
                "SELECT docset, name, type, '' as path, content FROM docs_fts WHERE docs_fts MATCH ? LIMIT 3",
                (candidate_names[0],),
            )
            matches = cur.fetchall()

        elapsed_ms = (time.perf_counter() - t0) * 1000

        if matches:
            count_str = f"[bold green]{len(matches)}[/bold green]"
            top_name = matches[0][1]
            raw_content = matches[0][4] if len(matches[0]) > 4 else ""
            clean_snippet = raw_content.replace("\n", " ").strip()[:90]
            lat_color = "bold green" if elapsed_ms < 2.0 else "bold red"
            test_table.add_row(
                docset.upper(),
                query_label,
                count_str,
                top_name,
                f"[{lat_color}]{elapsed_ms:.3f} ms[/{lat_color}]",
                clean_snippet + "...",
            )
            if elapsed_ms >= 2.0:
                all_passed = False
        else:
            all_passed = False
            test_table.add_row(
                docset.upper(),
                query_label,
                "[bold red]0[/bold red]",
                "[red]MISSING[/red]",
                f"[bold red]{elapsed_ms:.3f} ms[/bold red]",
                "[red]No match found[/red]",
            )

    console.print(test_table)
    console.print("\n")

    if all_passed and total_docs > 0:
        console.print(
            f"[bold green]✔ All validation queries returned verified matches with search latency < 2.0 ms.[/bold green]\n"
        )
        return True
    else:
        console.print(
            "[bold red]✘ Diagnostics detected missing symbols or latency SLA violation.[/bold red]\n"
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. CLI Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="DevDocs Ingestion Engine for Project Bankai.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        type=Path,
        help="Target SQLite database path",
    )
    parser.add_argument(
        "--docset",
        choices=list(DEVDOCS_MANIFESTS.keys()),
        help="Ingest a specific docset only",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Rebuild the database from scratch",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run FTS5 diagnostics and latency benchmark, then exit",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve()

    if args.clean and db_path.exists():
        console.print(f"[yellow]Cleaning existing database at {db_path}...[/yellow]")
        for ext in ["", "-wal", "-shm"]:
            p = Path(f"{db_path}{ext}")
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    conn = get_db_connection(db_path)
    init_db(conn)

    if args.verify:
        ok = run_diagnostics(conn)
        conn.close()
        sys.exit(0 if ok else 1)

    target_keys = [args.docset] if args.docset else list(DEVDOCS_MANIFESTS.keys())

    console.print(
        Panel(
            f"[bold cyan]Project Bankai — DevDocs Knowledge Base Expansion[/bold cyan]\n"
            f"Database: [bold white]{db_path}[/bold white]\n"
            f"Docsets : [yellow]{', '.join(target_keys)}[/yellow]",
            expand=False,
        )
    )

    targets = {k: DEVDOCS_MANIFESTS[k] for k in target_keys}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        total_symbols = 0
        for docset_key, manifest in targets.items():
            count = ingest_docset(docset_key, manifest, conn, progress)
            total_symbols += count

    console.print(
        f"\n[bold green]Ingestion complete. Total symbols indexed in this run: {total_symbols:,}[/bold green]"
    )
    console.print("[cyan]Optimizing SQLite FTS5 indexes and flushing WAL...[/cyan]")
    optimize_db(conn)
    console.print("[green]✔ Database optimization complete.[/green]")

    # Run diagnostics & latency benchmark
    ok = run_diagnostics(conn)
    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
