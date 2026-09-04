# 🏆 AWS *Agents for Humans* Hackathon Submission Packet
## Project: K-CLI for Devs — Autonomous Self-Healing DevOps & Engineering Agent
### Track: Professional Agents Track | Built with AWS Strands Agents SDK & Amazon Bedrock AgentCore
### Author: Krishiv Joshi ([@krishivjoshi](https://github.com/krishivjoshi219-collab))

---

## 🎯 1. The Pitch

### 1. The Problem We're Solving
Software developers and SREs lose hours every single day to repetitive, high-friction busywork:
* Parsing multi-hundred-line cryptic stack traces across 7 different runtimes (Python, Node, Rust, Go, C++, Docker, GitHub Actions CI).
* Triaging failing CI/CD pipelines caused by subtle environment shifts or dependency conflicts.
* Manually resolving 3-way Git merge conflicts where AST context is lost.
* Applying unverified AI suggestions that introduce syntax errors, broken imports, or security regressions.

### 2. Who It's For
* **Software Engineers, SREs, and DevOps Maintainers**: Who want an autonomous assistant that triages broken builds and repairs code with closed-loop compiler proof.
* **Makers, Small Teams, and Open-Source Contributors**: Who need high-velocity engineering workflows without getting bogged down in triage chores.

### 3. Why It Matters
**K-CLI does real work end-to-end instead of just chatting about bugs.**
Powered by the **AWS Strands Agents SDK** and **Amazon Bedrock AgentCore**, K-CLI operates as an autonomous background engineer. It runs quietly in the background, continuously monitors repository health, synthesizes verified fixes, and **only surfaces when a critical architectural decision or developer sign-off is needed**.

---

## 🏛️ 2. System Architecture & AWS Tech Stack

```mermaid
flowchart TD
  subgraph Ingestion ["📥 Incident & Multi-Interface Ingestion"]
    UI1["🖥️ Tier 1: Flagship Cyber TUI (`k-cli ui`)"]
    UI2["🌐 Tier 2: Cyber Station Web UI (`k-cli web ui`)"]
    UI3["⌨️ Tier 3: Streamlined Simple REPL (`k-cli simple`)"]
    Daemon["🔄 Background Healer Daemon (`k-cli daemon`)"]
    CI["🚨 CI/CD Logs / GitHub Actions Failure"]
  end

  subgraph AWSBrain ["🧠 AWS Strands Agent & Amazon Bedrock Layer"]
    Strands["StrandsDevAgent\n(`from strands import Agent, tool`)"]
    Bedrock["Amazon Bedrock Models\n• Anthropic Claude 3.5 Sonnet v2\n• Amazon Nova Pro\n• Amazon Nova Micro"]
    AgentCore["Amazon Bedrock AgentCore\n(OpenAPI 3.0 Action Groups & SAM Bundle)"]
    Strands <--> Bedrock
    Strands <--> AgentCore
  end

  subgraph Tools ["🛠️ Registered Deterministic Engines (@tool)"]
    T1["🔍 triage_and_heal_incident\n(7 Language Crash Parser & AST Locator)"]
    T2["🛡️ verify_code_file\n(Closed-Loop AST + py_compile + pytest + g++ + cargo)"]
    T3["🩹 apply_surgical_patch\n(Line-Accurate Fuzzy Block Patcher)"]
    T4["⚔️ resolve_git_merge_conflict\n(3-Way Semantic AST Conflict Resolver)"]
    T5["🗺️ inspect_repo_structure\n(Topological AST Symbol Map)"]
    T6["📚 search_offline_docs\n(Embedded SQLite FTS5 DevDocs)"]
    T7["🛡️ generate_chaos_immunity_patch\n(Adversarial Edge-Case Prober)"]
  end

  subgraph Loop ["🔁 Closed-Loop Verification Guardrail"]
    AST["AST Parse & Syntax Trees"]
    Comp["Local Compilers (py_compile, g++, cargo check)"]
    Test["Pytest Sandbox Execution"]
    Pass{"Verification Passed?"}
    Retry["Self-Heal Retry Loop (Max 3 Attempts)"]
  end

  subgraph Output ["✅ Production-Ready Delivery"]
    Patch["✔ Verified Surgical Patch"]
    Git["✔ Staged & Conventional Commit"]
    Report["✔ Rich Triage & Health Diagnostics"]
  end

  Ingestion --> Strands
  Strands --> Tools
  Tools --> Loop
  AST --> Comp --> Test --> Pass
  Pass -- No --> Retry --> Tools
  Pass -- Yes --> Output
```

---

## 📊 3. Hackathon Judging Criteria Alignment

| Judging Criteria | Implementation in K-CLI |
| :--- | :--- |
| **1. Technological Implementation** | • First-class integration with **AWS Strands Agents SDK** (`from strands import Agent, tool`).<br>• Full **Amazon Bedrock AgentCore** integration with OpenAPI 3.0 Action Groups and CloudFormation SAM deployment templates (`k-cli bedrock export / deploy`).<br>• Closed-loop AST compiler verification enforcing zero regressions before any patch is accepted. |
| **2. Design** | • **3 Unified UI Tiers**: Flagship 3-pane TUI (`k-cli ui`), Cyber Station Web Dashboard with WebSocket streaming (`k-cli web ui`), and Streamlined Text REPL with mouse support (`k-cli simple`).<br>• Real-time Auto-Adjusting Viewport Engine adapting fluidly across all terminal sizes and screen geometries. |
| **3. Potential Impact** | • Directly solves repetitive developer busywork: automated stack trace triage, 3-way merge conflict resolution, CI/CD auto-healing, and chaos immunity.<br>• **Background Daemon Mode (`k-cli daemon`)**: Runs silently in the background and only surfaces when a human decision is needed. |
| **4. Creativity & Originality** | • Sub-millisecond (<0.1ms) Adaptive Intent Sensor that dynamically optimizes model routing between fast conversational models and frontier reasoning models.<br>• Custom fine-tuned **Bankai-14B** & **Bankai-7B** coding models by Krishiv Joshi on Hugging Face.<br>• 100% offline DevDocs SQLite FTS5 search index. |
| **5. Presentation** | • Complete CLI reference, 5-minute video presentation script, live web server, and structured documentation ready for review. |

---

## 🎥 4. 5-Minute Demo Video & Presentation

- **▶️ Watch Live on YouTube**: [**https://youtu.be/RxT5tUYN9gc**](https://youtu.be/RxT5tUYN9gc)
- **Duration**: `00:05:00.00` (Exact 300.0s Full HD 1080p @ 30fps)
- **Embedded Soft Subtitles**: English Closed Captions (CC)


* **[0:00 - 0:45] The Hook & Pitch**:
  * "Every developer loses hours to broken CI pipelines, cryptic error traces, and merge conflicts. Welcome to **K-CLI for Devs**, the autonomous self-healing agent built with the **AWS Strands Agents SDK** and **Amazon Bedrock**."
  * Show the 3 unified UI tiers (TUI, Web UI, Simple REPL).
* **[0:45 - 2:00] AWS Strands Agent in Action (`k-cli strands`)**:
  * Trigger an autonomous multi-step engineering task.
  * Show the Strands agent dynamically invoking registered deterministic tools (`triage_and_heal_incident`, `verify_code_file`, `apply_surgical_patch`).
  * Highlight closed-loop compiler verification: the agent refuses to commit code until local compilers prove it passes.
* **[2:00 - 3:15] Amazon Bedrock AgentCore & Background Daemon (`k-cli daemon`)**:
  * Demonstrate `k-cli bedrock export` generating OpenAPI 3.0 Action Groups and CloudFormation SAM bundles.
  * Show `k-cli daemon` running quietly in the background, monitoring broken test runs and self-healing regressions without bothering the user.
* **[3:15 - 4:15] 3-Way AST Conflict Studio & Chaos Immunity**:
  * Run `k-cli conflict` resolving a 3-way merge conflict in AST context.
  * Run `k-cli immune` generating adversarial pytest suites for edge cases.
* **[4:15 - 5:00] Summary & Value**:
  * "K-CLI gives developers their time back by handling the busywork end-to-end. Built for the AWS *Agents for Humans* Hackathon."

---

## 📝 5. `builder.aws.com` Publication Draft

**Title**: *Agents for Humans: How We Built K-CLI with the AWS Strands Agents SDK & Amazon Bedrock*

**Article Outline**:
1. **Introduction**: The vision for autonomous developer agents that run in the background.
2. **Why the AWS Strands Agents SDK**: How Strands makes building multi-tool, deterministic agents straightforward with `@tool` and `Agent`.
3. **Connecting Amazon Bedrock**: Leveraging Claude 3.5 Sonnet and Amazon Nova via Bedrock AgentCore for surgical code generation.
4. **The Closed-Loop Verification Pattern**: Why compilers and test suites are essential guardrails for autonomous agents.
5. **Open Source & Next Steps**: Available on GitHub under the MIT License.

---

## 📦 6. Verification & Public Repository Deliverables

* **GitHub Repository**: [`https://github.com/krishivjoshi219-collab/K-Cli-for-Devs`](https://github.com/krishivjoshi219-collab/K-Cli-for-Devs)
* **License**: MIT License (Public in root and About section)
* **Author**: Krishiv Joshi (`@krishivjoshi`, `krishivjoshi219-collab`)
