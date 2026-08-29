# ⚡ K-CLI for Devs: Autonomous Self-Healing DevOps Agent
### Built for the AWS *Agents for Humans* Hackathon — Professional Agents Track

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](https://python.org)
[![AWS Strands Agents](https://img.shields.io/badge/AWS-Strands%20Agents%20SDK-orange.svg)](https://strandsagents.com)
[![Amazon Bedrock Ready](https://img.shields.io/badge/Amazon-Bedrock-purple.svg)](https://aws.amazon.com/bedrock/)

> **An autonomous, self-healing developer and SRE agent built with the AWS Strands Agents SDK. It ingests runtime crashes, broken CI/CD pipelines, and merge conflicts, diagnoses root causes with AST precision, and executes verified surgical fixes end-to-end.**

---

## 🎯 The Pitch (Agents for Humans Hackathon)

### 1. The Problem We're Solving
Modern software engineering teams waste countless hours triaging obscure CI/CD failures, parsing multi-language crash logs, and manually fixing merge conflicts. Traditional AI assistants only "chat" about bugs or generate unverified code snippets that hallucinate imports and introduce new regressions.

### 2. Who It's For
* **Software Engineers & SREs**: Who want instant, automated root-cause diagnosis and verified fixes for build failures.
* **DevOps Teams**: Automating CI/CD incident healing for GitHub Actions, Docker containers, and test suites.
* **Open Source Maintainers**: Resolving complex 3-way Git merge conflicts and regressions autonomously.

### 3. Why It Matters
**K-CLI for Devs does real work end-to-end, not just conversational advice.** 
Powered by the **AWS Strands Agents SDK**, it autonomously connects model reasoning (via Amazon Bedrock, Claude, Gemini, or local models) to heavy-duty deterministic engines. It enforces a strict **closed-loop ground-truth verification rule**: code is never committed until local compilers and test suites prove it works.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
  subgraph Input ["📥 Incident & Task Ingestion"]
    User["👨‍💻 Developer Goal"]
    CI["🚨 CI/CD Failure (GitHub Actions)"]
    Crash["💥 Runtime Crash / Docker Log"]
  end

  subgraph Brain ["🧠 AWS Strands Agent Orchestrator"]
    SA["StrandsDevAgent\n(from strands import Agent, tool)"]
    Models["Model Provider Layer\n• Amazon Bedrock (Claude 3.5 / Nova)\n• Google Gemini 2.0 Flash\n• Anthropic Claude / OpenAI GPT-4o\n• Local Ollama Qwen 2.5"]
    SA <--> Models
  end

  subgraph Tools ["🛠️ Registered Deterministic Tools (@tool)"]
    T1["🔍 triage_and_heal_incident\n(7 Language Crash Parser & AST Locator)"]
    T2["🛡️ verify_code_file\n(AST Syntax + Compiler + Pytest)"]
    T3["🩹 apply_surgical_patch\n(Fuzzy Search/Replace Block Patcher)"]
    T4["🔀 resolve_git_merge_conflict\n(3-Way Semantic Conflict Resolver)"]
    T5["🗺️ inspect_repo_structure\n(Topological AST Symbol Map)"]
    T6["📚 search_offline_docs\n(Embedded SQLite FTS5 DevDocs)"]
    T7["📊 generate_architecture_diagram\n(Mermaid Diagram Generator)"]
    T8["🛡️ generate_chaos_immunity_patch\n(Edge-Case Prober & Inoculator)"]
  end

  subgraph Loop ["🔁 Closed-Loop Verification & Execution"]
    AST["AST Parse & Syntax Check"]
    Comp["Local Compiler / Pytest Execution"]
    Retry{"Tests Passed?"}
    SelfHeal["Auto-Repair & Re-verify (Max 3 Retries)"]
  end

  subgraph Output ["✅ Production-Ready Output"]
    Patched["✔ Verified Surgical Patch Applied"]
    Commit["✔ Git Staged & Conventional Commit"]
    Report["✔ Rich TUI Triage & Health Report"]
  end

  Input --> SA
  SA --> Tools
  Tools --> Loop
  AST --> Comp --> Retry
  Retry -- No --> SelfHeal --> Tools
  Retry -- Yes --> Output
```

---

## 🚀 Key Features

### 1. Multi-Language Crash & Traceback Parser
Parses and localizes stack traces across **7 distinct environments**:
* **Python**: Standard tracebacks & pytest assertion failures.
* **Node.js / TypeScript**: V8 stack traces and unhandled promises.
* **Rust**: Panics and backtraces.
* **Go**: Goroutine runtime panics.
* **C++**: ASAN/UBSAN memory error reports and core dump signals.
* **Docker**: OOMKilled (Exit Code 137) and container startup panics.
* **GitHub Actions CI**: `##[error]` log annotations and failing pipeline steps.

### 2. Closed-Loop Ground-Truth Verification (`verifier.py`)
Code generated or patched by the agent is strictly validated before final acceptance:
* **Python**: Static `ast.parse()` check + isolated `py_compile` and `pytest`.
* **Bash**: Subprocess `bash -n` syntax linting.
* **C++ / Rust / Go**: Isolated compiler syntax validation (`g++ -fsyntax-only`, `cargo check`).

### 3. Surgical Search/Replace Patching (`patcher.py`)
Applies line-accurate `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` modifications without rewriting entire files, eliminating hallucinated deletions and reducing latency.

### 4. 3-Way Git Conflict Resolver (`conflict_resolver.py`)
Parses Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`), evaluates `BASE`, `OURS`, and `THEIRS` in AST context, and generates syntactically valid resolutions.

### 5. Autonomous Chaos Immunity & Edge-Case Self-Healing (`chaos_immunity.py`)
Proactively probes brittle AST patterns (KeyError, None dereference, socket/HTTP timeout hangs, ReDoS), synthesizes adversarial pytest suites in `tests/chaos/`, and applies verified defensive inoculation patches with zero regressions.

### 6. Pluggable Cloud & Local Models
Configured to run natively with:
* **Amazon Bedrock** (Anthropic Claude 3.5 Sonnet / Amazon Nova Pro)
* **Google Gemini** (Gemini 2.5 Flash / Pro)
* **Anthropic / OpenAI APIs**
* **Local Ollama** (100% offline air-gapped mode with embedded FTS5 DevDocs)

---

## 📦 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/krishivjoshi219-collab/K-Cli-for-Devs.git
cd K-Cli-for-Devs
```

### 2. Install Dependencies
```bash
pip install -e .
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and set your preferred provider credentials:

```bash
# Option A: Amazon Bedrock (Recommended for Hackathon)
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
export BEDROCK_MODEL_ID="anthropic.claude-3-5-sonnet-20241022-v2:0"

# Option B: Google Gemini
export GEMINI_API_KEY="your-gemini-api-key"

# Option C: OpenAI / Anthropic
export OPENAI_API_KEY="your-openai-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

---

## 💻 Usage & CLI Reference

### 1. Autonomous Strands Agent Goal
Let the Strands Agent inspect your codebase, plan, and solve a task autonomously:
```bash
k-cli strands "Diagnose and fix the test failure in auth_service.py"
```

### 2. Deep Crash Triage & Closed-Loop Auto-Heal
Feed a raw stacktrace or CI/CD log file directly to the agent:
```bash
# From a log file
k-cli auto-heal crash_report.log

# Or pipe live output from a broken build
pytest | k-cli auto-heal
```

### 3. Autonomous Chaos Immunity & Zero-Day Inoculation
Probe edge cases, synthesize adversarial tests, and inoculate your code with defensive guards:
```bash
# Inoculate a specific module
k-cli immune src/handler.py

# Or sweep and inoculate the entire repository
k-cli immune
```

### 4. Standalone Ground-Truth Code Verification
Verify any source file against local compilers and AST checks:
```bash
k-cli verify src/handler.py
```

### 5. Interactive Full-Screen Terminal Workstation (TUI)
Launch the full Textual dashboard with real-time token speedometers and RAM monitors:
```bash
k-cli ui
```

---

## 🧪 Running the Test Suite

Execute the full suite of unit and integration tests:

```bash
pytest tests/ -v
```

All 13 Strands Agent and tool verification tests run in isolated sandboxes and validate end-to-end functionality.

---

## 📄 License & Open Source Compliance

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details. Open source, transparent, and ready for community extension.
