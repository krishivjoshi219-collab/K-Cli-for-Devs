# E2E Test Infra: K-CLI Flagship Refactor

## Test Philosophy
- Opaque-box, requirement-driven. Derives from `ORIGINAL_REQUEST.md`.
- 4-Tier Test Architecture:
  1. Tier 1: Feature Coverage (≥5 per feature in isolation)
  2. Tier 2: Boundary & Corner Cases (≥5 boundary conditions per feature)
  3. Tier 3: Cross-Feature Combinations (Pairwise integration)
  4. Tier 4: Real-World Application Scenarios (Full workflows)
  5. Tier 5: Adversarial Coverage Hardening (White-box gap closing)

## Feature Inventory & Test Matrix
| # | Feature | Requirement | Tier 1 | Tier 2 | Tier 3 |
|---|---------|-------------|:------:|:------:|:------:|
| 1 | Baseline Core Verification | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ |
| 2 | DevDocs SQLite FTS5 Indexing & Search | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 3 | AST Repo Map Generation & Token Limits | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 4 | SEARCH/REPLACE Surgical Patcher & Fuzzy Match | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 5 | Git Safety Net, Atomic Commits & Rollback | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 6 | Multi-Turn Session & Token Pruning | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |
| 7 | REPL Slash Commands Hub | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |
| 8 | CLI Single-Shot Command Execution | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |
| 9 | Performance Benchmarks (RSS Memory, <5ms FTS5, <250ms Map) | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `/home/k/e/bin/pytest tests/test_e2e_suite.py`
- Test case format: Unit/integration pytest functions with rigorous assertions on exit codes, outputs, AST validity, latency, and memory RSS.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Greenfield Module Creation & Test via Single-Shot CLI | F1, F4, F5, F8 | Medium |
| 2 | Multi-Turn Refactor in REPL with `/add`, `/diff`, `/undo` | F4, F5, F6, F7 | High |
| 3 | Precise DevDocs Injection into Failing Test Repair | F1, F2, F4, F5 | High |
| 4 | Repo Map Context Injection in Multi-File Refactor | F3, F4, F5, F6 | High |
| 5 | Complex Syntax Error Rollback via Git Guard | F1, F4, F5, F7 | Medium |

## Coverage Thresholds
- Tier 1: ≥ 45 test cases (5 per feature area)
- Tier 2: ≥ 45 test cases (boundary and corner cases)
- Tier 3: ≥ 10 test cases (cross-feature pairwise interactions)
- Tier 4: ≥ 5 realistic application scenarios
- Tier 5: Adversarial hardening test cases
