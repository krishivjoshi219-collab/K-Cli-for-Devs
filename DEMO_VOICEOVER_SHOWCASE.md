# 🎬 K-CLI Demo & AI Voiceover Production Guide
## Built for AWS *Agents for Humans* Hackathon (Professional Agents Track)
### Project: **K-CLI for Devs** | Developer: **Krishiv Joshi** ([@krishivjoshi](https://github.com/krishivjoshi219-collab))

---

## 🌟 Overview

This guide provides everything needed to record and submit the **5-Minute Championship Demo Video** for the AWS Hackathon, including:
1. **Automated Live Terminal Demo Runner**: Run `k-cli demo` to execute a synchronized visual demo in real-time.
2. **Pre-Synthesized AI Voiceover Audio Tracks (`.mp3`)**: Studio-quality narration files in `demo_assets/voiceover/` ready to drop into any video editor.
3. **Second-by-Second Video Storyboard**: Exact visual cues and narrative timing from `0:00` to `5:00`.

---

## 🚀 1. How to Run the Live Terminal Demo

```bash
# 1. Run the Full 5-Minute Demo at normal speed
k-cli demo

# 2. Run at 1.5x speed (Great for quick screen recordings)
k-cli demo --speed 1.5

# 3. Run a specific Act (1 to 5)
k-cli demo --act 1   # The Hook & UI Tiers
k-cli demo --act 2   # AWS Strands SDK & Closed-Loop Compilers
k-cli demo --act 3   # Amazon Bedrock AgentCore & Background Daemon
k-cli demo --act 4   # 3-Way AST Conflict Studio & Chaos Immunity
k-cli demo --act 5   # Custom Bankai Models & Grand Finale
```

---

## 🎙️ 2. AI Voiceover Audio Files (`demo_assets/voiceover/`)

The following audio files have been synthesized and saved in [`demo_assets/voiceover/`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/):

| File | Timing | Segment Title | Narration Script |
| :--- | :--- | :--- | :--- |
| [`act_1_the_hook.mp3`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/act_1_the_hook.mp3) | **0:00 - 0:45** | **Act 1: The Hook** | *"Every day, software developers and SREs lose hours to small, repetitive, and cryptic tasks: debugging multi-hundred-line stack traces, triaging failing CI/CD pipelines, and resolving merge conflicts. What if your AI didn't just chat about code, but operated as an autonomous engineer in the background? Introducing K-CLI for Devs: Built with the AWS Strands Agents SDK and Amazon Bedrock AgentCore. Whether you work in a full-screen cyberpunk terminal, a modern web dashboard, or a lightweight mouse-enabled REPL, K-CLI adapts fluidly to your workflow."* |
| [`act_2_strands_and_compilers.mp3`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/act_2_strands_and_compilers.mp3) | **0:45 - 2:00** | **Act 2: Strands & Compilers** | *"Under the hood, K-CLI is powered by the AWS Strands Agents SDK. Unlike traditional chatbots that hallucinate unverified code, K-CLI exposes deterministic tools wrapped in strict closed-loop compiler guardrails. Every line of code generated must pass local AST parsing, syntax checks, and sandbox tests before it can ever be committed."* |
| [`act_3_bedrock_and_daemon.mp3`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/act_3_bedrock_and_daemon.mp3) | **2:00 - 3:15** | **Act 3: Bedrock AgentCore & Daemon** | *"K-CLI features native Amazon Bedrock AgentCore integration. With a single command, you can export OpenAPI 3.0 Action Groups and CloudFormation SAM deployment bundles, enabling seamless enterprise deployment on AWS Bedrock. Even better: K-CLI includes an autonomous Background Healer Daemon. It runs quietly in the background of your repo, automatically catches broken tests, heals syntax and dependency regressions, and only interrupts you when a real human decision is required."* |
| [`act_4_conflicts_and_chaos.mp3`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/act_4_conflicts_and_chaos.mp3) | **3:15 - 4:15** | **Act 4: Conflicts & Chaos** | *"Merge conflicts are often nightmares because standard Git tools lack language semantics. K-CLI's Conflict Studio parses AST scope trees for 2-way and 3-way conflicts, understands intent, and automatically synthesizes verified merges without losing upstream or local logic. And with the Chaos Immunity Shield, K-CLI proactively probes your codebase for brittle edge cases, generating adversarial test suites and applying defensive inoculations before code ever hits production."* |
| [`act_5_bankai_models_and_finale.mp3`](file:///home/k/K-Cli-for-Devs/demo_assets/voiceover/act_5_bankai_models_and_finale.mp3) | **4:15 - 5:00** | **Act 5: Bankai Models & Finale** | *"To deliver world-class precision, developer Krishiv Joshi fine-tuned the custom Bankai-14B and Bankai-7B frontier models on Hugging Face, optimized specifically for compiler-verified coding, AST healing, and architectural reasoning. Combined with sub-millisecond adaptive intent sensing and 100% offline SQLite FTS5 documentation search, K-CLI gives developers their time back. Fully open source under the MIT License."* |

---

## 🎥 3. How to Record & Produce the Video

1. **Step 1 — Screen Capture**:
   * Open your terminal in full screen (or 1920x1080 resolution).
   * Start your screen recorder (OBS Studio, SimpleScreenRecorder, QuickTime, or Loom).
   * Run `k-cli demo` (or launch the web UI with `k-cli web ui` and switch between tabs).
2. **Step 2 — Drop Voiceover Audio**:
   * Import your video recording into your video editor of choice (CapCut, DaVinci Resolve, Premiere, iMovie).
   * Drag the 5 MP3 files from `demo_assets/voiceover/` onto the audio timeline.
   * Align each track with its corresponding scene on the timeline.
3. **Step 3 — Export & Upload**:
   * Export the video in 1080p (MP4 format).
   * Upload to YouTube (Public or Unlisted) or Loom.
   * Add the link to your Devpost hackathon submission form!
