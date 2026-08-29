# K-CLI Architecture & System Design

K-CLI is an agentic AI coding workstation built around **compiler-grounded verification**, **multi-model routing**, and **zero cloud lock-in**.

---

## 1. High-Level Modular Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         1. User Interface & Session Layer                        │
│   k_cli/cli.py (Typer CLI Hub with 20+ commands)                                  │
│   k_cli/tui/tui_app.py (Textual 3-Column Cyber-Workstation)                      │
│   k_cli/tui/tui.py (Streaming REPL) <---> k_cli/tui/tui_animations.py (HUD Engine)│
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
┌────────────────────────────────────────┴─────────────────────────────────────────┐
│                           2. Core AI & Routing Layer                             │
│   k_cli/core/llm_driver.py (Multi-Provider: Ollama, Gemini, Claude, OpenAI)     │
│   k_cli/core/models_hub.py (Model Hub & Speedometer Benchmarks)                  │
│   k_cli/core/smart_router.py (Cost & Latency Optimizer Smart Router)             │
│   k_cli/core/airgap.py (Sovereign Air-Gapped Offline Policy Engine)              │
│   k_cli/core/sdk.py (Universal Programmatic Python API)                          │
└───────────────────┬──────────────────────────────────┬───────────────────────────┘
                    │                                  │
┌───────────────────┴──────────────────┐   ┌───────────┴───────────────────────────┐
│     3. Multi-Agent Swarm Layer       │   │    4. Git & Code Modification Layer   │
│  orchestrator.py (5-Stage Persona)   │   │  conflict_resolver.py (3-Way Merge)   │
│  subagents.py (DAG Swarm Dispatcher) │   │  ai_bisect.py (AI Regression Hunter)  │
│  adversarial_swarm.py (Red/Blue Team)│   │  smart_git.py (Conventional Commits)  │
│  scaffold_engine.py (Full-Stack App) │   │  patcher.py (SEARCH/REPLACE Engine)   │
│  persona.py (Domain System Prompts)  │   │  verifier.py (AST Compiler Guard)     │
└───────────────────┬──────────────────┘   └───────────┬───────────────────────────┘
                    │                                  │
┌───────────────────┴──────────────────────────────────┴───────────────────────────┐
│                    5. Tools, Diagnostics & Knowledge Layer                       │
│  ghost_daemon.py (Terminal Autopilot & Runtime Crash Healer)                     │
│  synapse_graph.py (AST Code Graph & 95%+ Context Compressor)                     │
│  repo_gardener.py (Nightly Maintenance & Dead Code Pruner)                       │
│  codebase_qa.py (Local Natural Language Architecture Search)                     │
│  security_healer.py (Static AST Vulnerability Auto-Healer)                       │
│  incident_triage.py (Traceback & Actions CI Log Parser)                          │
│  diagram_generator.py (Mermaid Flowchart & Architecture Engine)                  │
│  mcp_client.py (Universal Model Context Protocol Hub - stdio/SSE)                │
│  pr_watcher.py (24/7 Autonomous PR Review & Merge Daemon)                        │
│  dedup_engine.py (Anti-Overlap BM25 & AST Scanner)                               │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Package Organization

| Package | Key Modules | Primary Responsibility |
| :--- | :--- | :--- |
| **`k_cli/core/`** | `llm_driver.py`, `models_hub.py`, `smart_router.py`, `airgap.py`, `sdk.py`, `session.py` | Multi-model inference, dynamic cost routing, sovereign air-gap isolation, session state, and top-level Python SDK. |
| **`k_cli/agents/`** | `orchestrator.py`, `subagents.py`, `adversarial_swarm.py`, `scaffold_engine.py`, `persona.py` | Multi-agent DAG task decomposition, Red Team vs Blue Team consensus loops, full-stack scaffolding, and specialized domain personas. |
| **`k_cli/git/`** | `conflict_resolver.py`, `ai_bisect.py`, `smart_git.py`, `patcher.py`, `verifier.py`, `git_guard.py`, `repo_map.py` | 3-way AST merge conflicts, binary git bisect regression hunting, surgical code patch application, and multi-language compiler verification. |
| **`k_cli/github/`** | `github_engine.py`, `github_client.py`, `pr_watcher.py`, `dedup_engine.py` | GitHub REST v3 integration, autonomous issue solving, 24/7 PR review daemon, and BM25 request deduplication. |
| **`k_cli/tools/`** | `ghost_daemon.py`, `synapse_graph.py`, `repo_gardener.py`, `codebase_qa.py`, `security_healer.py`, `incident_triage.py`, `diagram_generator.py`, `mcp_client.py` | Ghost terminal crash interceptor, AST neural code graph, repo hygiene gardener, natural language search, security healing, and MCP client. |
| **`k_cli/tui/`** | `tui_app.py`, `tui.py`, `tui_animations.py`, `diff_viewer.py` | 3-Column Textual Cyber-Workstation, streaming token renderer, cyberpunk ASCII splash banners, and side-by-side diff viewers. |

---

## 3. Ground-Truth Verification Architecture

K-CLI enforces a **strict verification gate** before accepting any generated code:

1. **AST & Syntax Safety**: Python `ast.parse()`, `bash -n`, and `g++ -fsyntax-only` execute in credential-filtered subprocesses.
2. **Adversarial Red Team Probing**: In `k-cli swarm`, the Red Team automatically generates boundary attack tests (null values, concurrency race conditions, integer overflows) to stress-test candidate code.
3. **Execution Guard**: Runs local test runners (`pytest`, `cargo test`, `npm test`, `go test`) with timeout cleanup.
4. **Git Safety Net**: Pre-modification git snapshots allow zero-risk instantaneous rollback (`/rollback` or `kcli.rollback()`).
