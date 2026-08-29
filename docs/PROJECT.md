# Project: K-CLI Flagship Refactor and Evolution

## Architecture
K-CLI is refactored into a 4-layer modular architecture with clean separation of concerns:

```
+-----------------------------------------------------------------------+
|                4. User Interface & Session Layer                      |
|   cli.py (Typer CLI + REPL shell) <---> session.py (Session Manager)  |
+-----------------------------------+-----------------------------------+
                                    |
+-----------------------------------+-----------------------------------+
|                       1. Core Engine Layer                            |
|   orchestrator.py (Pipeline/Memory) <-> llm_driver.py (GGUF/Ollama)   |
|   verifier.py (AST / Pytest / Compilers)                              |
+-------------------+-------------------------------+-------------------+
                    |                               |
+-------------------+---------------+   +-----------+-------------------+
|  2. Knowledge & Context Layer     |   | 3. Modification & Safety Net  |
|  doc_retriever.py (SQLite FTS5)   |   |  patcher.py (SEARCH/REPLACE)  |
|  repo_map.py (AST Symbol Map)     |   |  git_guard.py (Git Rollback)  |
+-----------------------------------+   +-------------------------------+
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Baseline Test Fixes | Fix stream_callback mock & mock context to pass all 45 tests | M1 | Survey |
| 2 | Core Engine Layering | Refactor verifier, orchestrator, llm_driver interface contracts | M1 | R1 |
| 3 | SQLite FTS5 Schema | SQLite virtual table with BM25 ranking for DevDocs | M2 | R2 |
| 4 | Stdlib & Framework Indexing | Built-in offline index of standard library API signatures | M2 | R2 |
| 5 | Precision Doc Retrieval | Exact signature extraction < 250 tokens, < 5ms latency | M2 | R2 |
| 6 | CLI `k doc` Command | Command-line and programmatic doc querying | M2 | R2 |
| 7 | AST Symbol Extraction | Parse workspace .py files for classes, methods, functions | M3 | R3 |
| 8 | Symbol Ranking & Tree View | Token-bounded hierarchical repo map < 400 tokens, < 250ms | M3 | R3 |
| 9 | CLI `k map` Command | CLI and session-injected codebase map | M3 | R3 |
| 10 | SEARCH/REPLACE Block Parser | Parse `<<<<<<< SEARCH ... ======= ... >>>>>>>` blocks | M4 | R4 |
| 11 | Fuzzy Indentation Matcher | Indentation-tolerant and whitespace-normalized patch application | M4 | R4 |
| 12 | Pre-Application AST Validation | Validate syntax before committing edits to disk | M4 | R4 |
| 13 | Git Safety Snapshot | Create git workspace checkpoints before edits | M4 | R4 |
| 14 | Atomic Git Commit | Commit with semantic message on verified success | M4 | R4 |
| 15 | Automatic Git Rollback | Instant `git restore` on verification failure | M4 | R4 |
| 16 | Multi-Turn Session State | Rolling token-budgeted conversation history | M5 | R5 |
| 17 | Slash Command `/add` | Add files to active session context | M5 | R5 |
| 18 | Slash Command `/undo` | Roll back last modification via git guard | M5 | R5 |
| 19 | Slash Command `/diff` | View active git diff / uncommitted changes | M5 | R5 |
| 20 | Slash Command `/clear` | Reset conversation memory and active files | M5 | R5 |
| 21 | Slash Command `/status` | View model, active files, token usage, RSS RAM | M5 | R5 |
| 22 | Slash Command `/model` | Switch model / backend dynamically | M5 | R5 |
| 23 | Slash Command `/help` | List available slash commands and usage | M5 | R5 |
| 24 | Interactive REPL (`k`) | Polished interactive shell with history and syntax highlighting | M5 | R5 |
| 25 | Single-Shot CLI (`k "..."`) | Direct prompt execution with verification and auto-git | M5 | R5 |
| 26 | Performance: RAM Budget | Peak RSS strictly < 1024 MB with GC threshold at 85% | M6 | Acceptance |
| 27 | Performance: FTS5 Latency | Doc search latency < 5ms | M6 | Acceptance |
| 28 | Performance: Repo Map Latency | AST repo map generation < 250ms | M6 | Acceptance |
| 29 | 100% Existing Tests Pass | All original unit & integration tests pass | M6 | Acceptance |
| 30 | Comprehensive New Test Suites | 100% pass on all new domain test suites | M6 | Acceptance |
| 31 | Full E2E Workflow Pass | End-to-end multi-turn & single-shot validation | M6 | Acceptance |
| 32 | Adversarial Hardening (Tier 5) | White-box stress testing and boundary validation | M6 | Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Engine Baseline Fixes | Fix 4 failing baseline tests in llm_driver, test_llm_driver, test_cli, orchestrator; clean 45/45 pass | none | DONE |
| M2 | DevDocs SQLite Indexer & Precision Retriever | Implement `doc_retriever.py` with FTS5, BM25, stdlib indexing, `k doc` command, and unit tests | M1 | DONE |
| M3 | AST Codebase Repository Map | Implement `repo_map.py` with AST symbol extraction, ranking, tree view, `k map` command, and unit tests | M1 | DONE |
| M4 | Surgical Patch Engine & Git Safety Net | Implement `patcher.py` and `git_guard.py` with block parsing, fuzzy match, git commits/rollback, and unit tests | M1 | DONE |
| M5 | Interactive Session & Command Hub | Implement `session.py` and refactor `cli.py` for slash commands, REPL, single-shot, and unit tests | M2, M3, M4 | DONE |
| M6 | Final Milestone: 100% E2E Pass & Adversarial Hardening | Pass 100% E2E test suite (Tiers 1-4), Tier 5 adversarial hardening, latency and RAM budget benchmarks | M5 | DONE |

## Interface Contracts

### `doc_retriever.py` (Knowledge Layer)
```python
class DocRetriever:
    def __init__(self, db_path: Optional[str] = None): ...
    def index_module(self, module_name: str, doc_data: Dict[str, Any]) -> int: ...
    def search(self, query: str, limit: int = 3, max_tokens: int = 250) -> List[Dict[str, Any]]: ...
    def format_context_snippets(self, query: str, max_tokens: int = 250) -> str: ...
```

### `repo_map.py` (Knowledge Layer)
```python
class RepoMap:
    def __init__(self, root_dir: str = "."): ...
    def get_repo_map(self, max_tokens: int = 400, focus_files: Optional[List[str]] = None) -> str: ...
    def extract_symbols(self, file_path: str) -> List[Dict[str, Any]]: ...
```

### `patcher.py` (Modification Layer)
```python
class Patcher:
    @staticmethod
    def parse_search_replace_blocks(text: str) -> List[Tuple[str, str]]: ...
    @staticmethod
    def apply_patch(original_code: str, search_block: str, replace_block: str, fuzzy: bool = True) -> Tuple[bool, str, str]: ...
    @staticmethod
    def apply_file_patches(file_path: str, patch_text: str, validate_ast: bool = True) -> Tuple[bool, str]: ...
```

### `git_guard.py` (Safety Net Layer)
```python
class GitGuard:
    def __init__(self, repo_dir: str = "."): ...
    def is_git_repo(self) -> bool: ...
    def ensure_repo(self) -> bool: ...
    def create_snapshot(self) -> str: ...
    def commit_success(self, message: str, files: Optional[List[str]] = None) -> Optional[str]: ...
    def rollback(self, files: Optional[List[str]] = None) -> bool: ...
    def get_diff(self, cached: bool = False) -> str: ...
```

### `session.py` (UI & Session Layer)
```python
class SessionManager:
    def __init__(self, workspace_dir: str = ".", model_name: Optional[str] = None, max_tokens: int = 4096): ...
    def add_file(self, file_path: str) -> bool: ...
    def remove_file(self, file_path: str) -> bool: ...
    def get_context_files(self) -> List[str]: ...
    def clear_history(self) -> None: ...
    def undo_last_edit(self) -> Tuple[bool, str]: ...
    def get_status(self) -> Dict[str, Any]: ...
    def process_turn(self, prompt: str) -> Generator[str, None, Dict[str, Any]]: ...
```

## Code Layout
- Core Engine: `/home/k/k_cli/verifier.py`, `/home/k/k_cli/orchestrator.py`, `/home/k/k_cli/llm_driver.py`
- Knowledge Layer: `/home/k/k_cli/doc_retriever.py`, `/home/k/k_cli/repo_map.py`
- Modification Layer: `/home/k/k_cli/patcher.py`, `/home/k/k_cli/git_guard.py`
- UI / Session: `/home/k/k_cli/session.py`, `/home/k/k_cli/cli.py`
- Tests: `/home/k/k_cli/tests/test_*.py`
- Environment binaries: `/home/k/e/bin/pytest`, `/home/k/e/bin/python`
