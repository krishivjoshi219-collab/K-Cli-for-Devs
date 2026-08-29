# TEST_READY: K-CLI Flagship E2E Test Suite Specification & Runner Guide

## Overview
The comprehensive 4-Tier End-to-End (E2E) test suite for the K-CLI flagship refactor and evolution project is fully designed, implemented, and verified in `/home/k/k_cli/tests/test_e2e_suite.py`.

The suite provides exhaustive, opaque-box, requirement-driven verification of all system layers defined in `ORIGINAL_REQUEST.md` and `PROJECT.md`. It supports **Progressive Testability**: tests for available modules execute immediately, while tests for downstream milestone modules (`doc_retriever.py`, `repo_map.py`, `patcher.py`, `git_guard.py`, `session.py`) automatically activate and execute as each milestone implements them.

---

## Test Execution Command
```bash
/home/k/e/bin/pytest tests/test_e2e_suite.py -v
```

To run all test suites across the repository:
```bash
/home/k/e/bin/pytest tests/ -v
```

---

## Comprehensive Test Inventory & Coverage Matrix

### Total Test Cases: 109 Test Cases across 4 Tiers

### Tier 1: Feature Coverage in Isolation (45 Tests)
| Feature Area | Module / Class | Test Methods | Focus / Interface Contract |
|---|---|---|---|
| **F1: Baseline Core Verification** | `verifier.py` (`Verifier`, `CodeExtractor`) | `test_t1_f1_verifier_valid_python_ast`<br>`test_t1_f1_verifier_syntax_error_with_line`<br>`test_t1_f1_code_extractor_markdown_fences`<br>`test_t1_f1_code_extractor_raw_fallback`<br>`test_t1_f1_verifier_result_dataclass_to_dict` | Static AST validation, error line extraction, markdown fence extraction, VerificationResult serialization. |
| **F2: DevDocs Precision Retrieval** | `doc_retriever.py` (`DocRetriever`) | `test_t1_f2_doc_retriever_initialization`<br>`test_t1_f2_doc_retriever_index_module`<br>`test_t1_f2_doc_retriever_search_bm25`<br>`test_t1_f2_doc_retriever_format_context_snippets`<br>`test_t1_f2_doc_retriever_token_budget_bound` | SQLite FTS5 table schema, BM25 ranking, exact signature extraction, formatted snippets strictly < 250 tokens. |
| **F3: AST Codebase Repository Map** | `repo_map.py` (`RepoMap`) | `test_t1_f3_repo_map_extract_symbols_functions_classes`<br>`test_t1_f3_repo_map_get_repo_map_hierarchy`<br>`test_t1_f3_repo_map_token_limit_budget`<br>`test_t1_f3_repo_map_focus_files_prioritization`<br>`test_t1_f3_repo_map_multi_file_workspace` | AST symbol extraction (classes/methods/functions), hierarchical tree formatting < 400 tokens, `focus_files` prioritization. |
| **F4: SEARCH/REPLACE Surgical Patcher** | `patcher.py` (`Patcher`) | `test_t1_f4_patcher_parse_single_block`<br>`test_t1_f4_patcher_parse_multiple_blocks`<br>`test_t1_f4_patcher_apply_patch_exact`<br>`test_t1_f4_patcher_apply_file_patches`<br>`test_t1_f4_patcher_ast_validation_prevents_syntax_error` | Unified `<<<<<<< SEARCH ... ======= ... >>>>>>>` block parser, file patching on disk, pre-commit AST syntax validation. |
| **F5: Git Safety Net & Rollback** | `git_guard.py` (`GitGuard`) | `test_t1_f5_git_guard_is_git_repo`<br>`test_t1_f5_git_guard_ensure_repo`<br>`test_t1_f5_git_guard_create_snapshot`<br>`test_t1_f5_git_guard_commit_success`<br>`test_t1_f5_git_guard_rollback_restores_file` | Git repo detection, `ensure_repo`, snapshot checkpoints, atomic commits with semantic messages, rollback restoration. |
| **F6: Multi-Turn Session Management** | `session.py` (`SessionManager`) | `test_t1_f6_session_add_context_file`<br>`test_t1_f6_session_remove_context_file`<br>`test_t1_f6_session_clear_history`<br>`test_t1_f6_session_get_status`<br>`test_t1_f6_session_process_turn_streaming` | Context file tracking, rolling conversation memory, status introspection (RAM/tokens/files), streaming turn generator. |
| **F7: REPL Slash Commands Hub** | `session.py` / `cli.py` | `test_t1_f7_slash_help_command`<br>`test_t1_f7_slash_add_command`<br>`test_t1_f7_slash_diff_command`<br>`test_t1_f7_slash_undo_command`<br>`test_t1_f7_slash_status_and_clear` | Slash commands dispatch (`/add`, `/undo`, `/diff`, `/clear`, `/status`, `/model`, `/help`). |
| **F8: CLI Command Execution** | `cli.py` (`Typer app`) | `test_t1_f8_cli_app_help`<br>`test_t1_f8_cli_status_command`<br>`test_t1_f8_cli_doc_command`<br>`test_t1_f8_cli_map_command`<br>`test_t1_f8_cli_run_command_mock` | Typer CLI commands invocation (`--help`, `status`, `doc`, `map`, `run`). |
| **F9: Performance Budgets** | All Modules | `test_t1_f9_perf_rss_memory_under_1024mb`<br>`test_t1_f9_perf_fts5_latency_under_5ms`<br>`test_t1_f9_perf_repo_map_latency_under_250ms`<br>`test_t1_f9_perf_ast_parse_latency_under_1ms`<br>`test_t1_f9_perf_patcher_latency_under_10ms` | Strict RSS memory < 1024 MB, FTS5 latency < 5ms, RepoMap latency < 250ms, AST latency < 1ms, Patcher latency < 10ms. |

---

### Tier 2: Boundary & Corner Cases (46 Tests)
- **B1: Empty & Null Inputs (8 tests)**: `test_t2_doc_retriever_empty_query_search`, `test_t2_doc_retriever_empty_index`, `test_t2_doc_retriever_whitespace_query`, `test_t2_repo_map_empty_workspace`, `test_t2_repo_map_empty_file`, `test_t2_patcher_empty_patch_string`, `test_t2_patcher_empty_search_block_handling`, `test_t2_session_empty_prompt_handling`.
- **B2: Missing Files & Non-Git Environments (6 tests)**: `test_t2_doc_retriever_missing_db_dir_auto_create`, `test_t2_repo_map_missing_file_extract_symbols`, `test_t2_patcher_missing_target_file_error`, `test_t2_session_add_missing_file_returns_false`, `test_t2_git_guard_non_git_workspace_no_crash`, `test_t2_git_guard_rollback_missing_file`.
- **B3: Malformed & Corrupted Patch Blocks (7 tests)**: `test_t2_patcher_malformed_missing_divider`, `test_t2_patcher_malformed_missing_end_marker`, `test_t2_patcher_search_block_not_matching`, `test_t2_patcher_replace_block_invalid_python_ast`, `test_t2_patcher_file_unchanged_on_ast_failure`, `test_t2_patcher_multiple_blocks_partial_failure`, `test_t2_patcher_overlapping_search_blocks`.
- **B4: Whitespace & Indentation Fuzzy Matcher (6 tests)**: `test_t2_patcher_fuzzy_whitespace_trailing_spaces`, `test_t2_patcher_fuzzy_newline_crlf_vs_lf`, `test_t2_patcher_fuzzy_indentation_shift`, `test_t2_patcher_exact_mode_rejects_mismatch`, `test_t2_patcher_unicode_emojis_in_source`, `test_t2_patcher_blank_lines_fuzzy_matching`.
- **B5: Extreme Token Constraints & Budgets (6 tests)**: `test_t2_doc_retriever_max_tokens_zero`, `test_t2_doc_retriever_max_tokens_one`, `test_t2_repo_map_max_tokens_small_limit`, `test_t2_repo_map_huge_symbols_pruning`, `test_t2_session_token_budget_prunes_old_turns`, `test_t2_doc_retriever_large_token_budget`.
- **B6: Corrupted Files & AST Robustness (6 tests)**: `test_t2_repo_map_skip_syntax_error_file`, `test_t2_repo_map_skip_binary_and_hidden_files`, `test_t2_repo_map_deeply_nested_tree`, `test_t2_verifier_multiline_syntax_error_line_number`, `test_t2_verifier_empty_string_ast`, `test_t2_verifier_comments_only_ast`.
- **B7: SQL Injection, Sanitization & Session Robustness (7 tests)**: `test_t2_doc_retriever_fts5_special_tokens_sanitization`, `test_t2_doc_retriever_sql_injection_safety`, `test_t2_doc_retriever_reindex_same_module`, `test_t2_session_undo_with_no_prior_edits`, `test_t2_session_remove_untracked_file`, `test_t2_session_add_duplicate_file_idempotent`, `test_t2_git_guard_diff_empty_when_clean`.

---

### Tier 3: Cross-Feature Combinations & Integrations (10 Tests)
1. `test_t3_patcher_git_guard_rollback_on_ast_failure`: Patcher detects syntax error during file modification -> triggers GitGuard instant rollback -> file stays pristine.
2. `test_t3_patcher_git_guard_atomic_commit_on_verified_success`: Verified patch applied cleanly -> GitGuard commits changes with semantic message.
3. `test_t3_doc_retriever_session_context_injection`: User query triggers DocRetriever search -> exact snippets injected into active session prompt context.
4. `test_t3_repo_map_patcher_symbol_update_reflection`: RepoMap maps symbols -> Patcher renames symbol -> RepoMap immediately reflects updated symbol table.
5. `test_t3_session_undo_restores_file_via_git_guard`: File added to session -> patched on disk -> SessionManager `/undo` executes GitGuard rollback restoring original content.
6. `test_t3_repo_map_doc_retriever_session_budget_coordination`: Combined prompt injection of RepoMap (< 400 tokens) and DocRetriever (< 250 tokens) strictly stays under 650 tokens total.
7. `test_t3_orchestrator_verifier_auto_debug_loop`: Orchestrator coordinates persona transitions and compiler verifier auto-debug loops.
8. `test_t3_cli_doc_and_map_subcommands_output`: Validates CLI Typer subcommands `k doc` and `k map`.
9. `test_t3_multi_file_patch_atomic_safety`: Multi-file patch where one file fails AST validation triggers atomic rollback across all files.
10. `test_t3_session_file_tracking_with_git_diff`: Session tracks modified file and produces accurate git diff.

---

### Tier 4: Real-World Scenarios & Benchmarks (8 Tests)
1. `test_t4_scenario_greenfield_module_creation_and_test`: End-to-end greenfield module creation (`algorithms/sort.py`), AST verification, and atomic commit via GitGuard.
2. `test_t4_scenario_multi_turn_repl_refactor`: Full interactive REPL session simulation (`/add` -> surgical SEARCH/REPLACE -> `/diff` -> `/undo` -> `/status`).
3. `test_t4_scenario_precise_doc_injection_repair`: Realistic failing test repair grounded by DocRetriever exact stdlib API signature injection.
4. `test_t4_scenario_multi_file_repo_map_refactor`: Multi-file refactor guided by hierarchical AST RepoMap context.
5. `test_t4_scenario_syntax_error_rollback_safety`: Syntax-error induced rollback preserves untouched git history.
6. `test_t4_benchmark_peak_rss_ram`: Rigorous system RSS RAM benchmark across all domain modules asserting RSS < 1024 MB.
7. `test_t4_benchmark_doc_retriever_fts5_latency`: 100-query FTS5 latency benchmark asserting mean search time < 5.0ms.
8. `test_t4_benchmark_repo_map_latency`: Multi-module AST RepoMap extraction benchmark asserting runtime < 250.0ms.

---

## Verification Status
- **Historical milestone result:** 17 passed, 0 failed, 92 skipped while M2-M5 modules were incomplete.
- **Current authoritative command:** `python -m pytest -q`
- **Current local result:** 613 passed, 0 failed on Python 3.12.3 in the maintained environment.
- **Environment:** Python 3.12.3, pytest 9.1.1.
