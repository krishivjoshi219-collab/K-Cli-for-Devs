# 🎬 Video Pitch & Demonstration Script (Max 5 Minutes)
### For AWS *Agents for Humans* Hackathon Submission

> **Video Upload Destination**: Upload to YouTube or Vimeo as **Public** or **Unlisted**.  
> **Target Duration**: 3:30 – 4:30 minutes (Rule limit: Max 5 minutes).

---

## 🎙️ Section 1: The Pitch (1:00 – 1:30)

### Visual:
* Title slide or camera introducing yourself and the project name: **K-CLI for Devs: Autonomous Self-Healing DevOps Agent**.

### Script / Voiceover:
> *"Hi everyone! I'm presenting **K-CLI for Devs**, an autonomous, self-healing developer and SRE agent built for the AWS Agents for Humans Hackathon in the **Professional Agents Track**.*
>
> *(1) **The Problem**: Every single day, software engineers, DevOps teams, and SREs lose hours staring at broken CI/CD logs, obscure Docker crash dumps, and merge conflicts. Traditional AI coding assistants only chat or spit out unverified code snippets that hallucinate imports and introduce new bugs into production.*
>
> *(2) **Who It's For**: It's built for software engineers, DevOps professionals, and open-source maintainers who want automated, trustworthy incident resolution.*
>
> *(3) **Why It Matters**: K-CLI for Devs doesn't just chat about errors — it **does the real work end-to-end**. Built on top of the **AWS Strands Agents SDK**, it connects autonomous model reasoning (via Amazon Bedrock, Claude, or Gemini) to heavy-duty deterministic engines. Most importantly, it enforces a strict **closed-loop ground-truth verification policy**: no patch is ever committed until local compilers and test suites prove it works 100%."*

---

## 💻 Section 2: Live Demonstration (2:00 – 2:30)

### Step 1: Deep Incident Triage & Auto-Heal
**Terminal Command:**
```bash
k-cli auto-heal tests/fixtures/sample_crash.log
```
**Voiceover:**
> *"Let's see it in action. Here we have a messy crash log from a broken pipeline. We pass it to `k-cli auto-heal`. In seconds, the Strands Agent parses the traceback across the stack, identifies the exact file and enclosing function using AST traversal, generates a surgical search/replace patch, runs `pytest` in an isolated loop to verify the fix, and confirms the repair."*

### Step 2: Autonomous Strands Goal Execution
**Terminal Command:**
```bash
k-cli strands "Inspect the repository structure, find any unverified modules, and generate an updated Mermaid architecture diagram"
```
**Voiceover:**
> *"Now let's give the Strands Agent a broader engineering goal. The agent uses its registered tools — calling `inspect_repo_structure`, `verify_code_file`, and `generate_architecture_diagram`. Notice how it autonomously sequences the tools, reasons through the output, and returns production-grade verified results."*

### Step 3: Autonomous Chaos Immunity & Edge-Case Inoculation
**Terminal Command:**
```bash
k-cli immune k_cli/tools/security.py
```
**Voiceover:**
> *"Next is our killer feature: the Autonomous Chaos Immunity Engine. It probes brittle AST patterns like unhandled KeyErrors or socket timeout hangs, automatically synthesizes adversarial test suites, and inoculates your codebase with defensive guards before bugs ever hit production."*

### Step 4: Full-Screen Developer Terminal Workstation
**Terminal Command:**
```bash
k-cli ui
```
**Voiceover:**
> *"For developers who live in the terminal, K-CLI also includes a full-screen Textual dashboard with real-time token speedometers, RAM allocation gauges, interactive 1-click launchers, and the new Chaos Immunity Hub (Ctrl+I)."*

---

## 🏆 Section 3: Conclusion & Architecture Summary (0:30)

### Visual:
* Architecture Diagram from `README.md` on screen.

### Script / Voiceover:
> *"To summarize: by combining the autonomous planning of the **AWS Strands Agents SDK** with closed-loop ground-truth AST verification, K-CLI for Devs turns hours of manual debugging into seconds of verified automated healing.*
>
> *The project is open source under the MIT License on GitHub, fully tested, and ready for deployment with Amazon Bedrock. Thank you!"*
