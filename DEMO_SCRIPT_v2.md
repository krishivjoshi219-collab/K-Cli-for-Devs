# 🎬 K-CLI FOR DEVS — CHAMPIONSHIP 5-MINUTE DEMO SCRIPT
## AWS "Agents for Humans" Hackathon | Professional Agents Track
### Developer: Krishiv Joshi | Bankai-10B & 7B Fine-Tuned Models

---

> JUDGING RUBRIC CHECKLIST before every line of this script was written:
> - Problem clearly shown (not just stated)
> - Audience identified on-screen
> - Why it matters FELT, not just explained
> - Agent running autonomously in the background (the track theme)
> - End-to-end flow with no dead screens, no passive slides
> - AWS Strands SDK + Bedrock AgentCore integrated authentically
> - Easy to follow even for a non-technical judge

---

## PRODUCTION NOTES (Read Before Recording)

- Voice: en-US-ChristopherNeural at +10% rate. Energetic but NOT salesy. Like a senior dev showing a friend the coolest thing they built at 2am and cannot stop smiling about it.
- Music: Lo-fi techno pulse under Acts 1 and 5. Silence (just terminal sounds) during Acts 2-4 to make the live execution feel real and raw.
- Screen: 1920x1080. Terminal font size 16. Dark background. No desktop clutter. Cursor always visible.
- Editing: Jump cuts on waiting. No dead air over 2 seconds. Every second on screen earns its place.
- Golden Rule: If a screen is just text sitting there, add a zoom or cursor movement. NEVER a passive screen.

---
---

# ACT 1: THE COLD OPEN — FEEL THE PAIN, THEN THE RELIEF
## 0:00 – 0:50 (50 seconds)

---

### SCENE 1A — The Pain Montage (0:00 – 0:15)

ON SCREEN — Show 3 rapid-fire terminal crash screens. Each lingers 4 seconds.

SCREEN 1: pytest failure wall
  FAILED tests/test_auth.py::test_token_validation - AttributeError: 'NoneType' object has no attribute 'decode'
  FAILED tests/test_router.py::test_dispatch_under_load - RuntimeError: Lock acquired but never released
  FAILED tests/test_payment.py::test_charge_idempotency - AssertionError: Expected 200, got 500
  ========== 47 failed, 3 passed in 61.3s ==========

SCREEN 2: git 3-way merge conflict
  <<<<<<< HEAD (your feature: async payment gateway)
      def process_payment(self, amount: Decimal) -> Receipt:
          return self._stripe.charge(amount, idempotency_key=uuid4())
  ||||||| base
      def process_payment(self, amount):
          return stripe.charge(amount)
  =======
      def process_payment(self, amount: Decimal, retries: int = 3) -> Receipt:
  >>>>>>> upstream/main (Tariq's refactor: retry logic)

SCREEN 3: CI/CD log at 11:47pm
  [23:47:12] BUILD FAILED — cargo build error: mismatched types
  [23:47:12]  --> src/consensus/coordinator.rs:214:18
  [23:47:12]   |  expected Arc<Mutex<State>>, found Mutex<State>
  [23:47:12] Pipeline aborted. 14 downstream jobs cancelled. On-call engineer paged.

NARRATION:
  "Three AM. Forty-seven failing tests. A three-way merge conflict that makes no sense. A Rust 
   compiler screaming at you in a language nobody taught in school. If you've shipped code 
   professionally, you've lived this nightmare.

   And the worst part? None of this is hard engineering. It is all noise. Repetitive, 
   soul-crushing, machine-solvable noise that steals hours from the work that actually matters."

[HARD CUT — dramatic musical sting]

---

### SCENE 1B — The Reveal: K-CLI Boots Up (0:15 – 0:35)

ON SCREEN: Terminal clears. Cursor blinks once. User types:
  $ k-cli ui

Flagship TUI launches full-screen — 3-pane cyberpunk workstation.
Camera ZOOMS slowly into telemetry panel. Mouse clicks quickly across:
Model Hub → Credentials Vault → GitHub Center. Each modal opens and closes fast.

NARRATION:
  "This is K-CLI for Devs. An autonomous background engineering agent built with the 
   AWS Strands Agents SDK and Amazon Bedrock AgentCore.

   It runs in your terminal as a full cyberpunk workstation, in your browser as a 
   glassmorphism web dashboard, or as a lightning-fast REPL — three complete UIs, 
   one sovereign engine underneath."

---

### SCENE 1C — The 3-Tier Flash Tour (0:35 – 0:50)

ON SCREEN: Fast 3-panel montage. Each UI gets 5 seconds with live mouse movement.
  Tier 1: k-cli ui  — Cyber TUI, cursor scrolling through live chat history
  Tier 2: k-cli web ui → browser shows glassmorphism dashboard with token stream visible
  Tier 3: k-cli simple — lightweight REPL, 42ms boot shown, live question typed

NARRATION:
  "Whether you're a terminal purist, a browser person, or just want blazing-fast answers — 
   K-CLI meets you exactly where you work."

---
---

# ACT 2: THE AGENT IN ACTION — LIVE ENGINEERING, NOT CHATTING
## 0:50 – 2:10 (80 seconds)

---

### SCENE 2A — The Complex Engineering Prompt (0:50 – 1:10)

ON SCREEN: Back in Cyber TUI. User types into chat arena with typing animation:
  > /strands Architect a distributed lock-free consensus coordinator in Python
    with heartbeat failover, atomic state transitions, and adversarial chaos tests.
    The implementation must pass py_compile and pytest before any code is staged.

Agent status bar changes: READY → PLANNING → EXECUTING
Thinking Radar lights up: tool nodes glow cyan → orange → green in sequence.

NARRATION:
  "I'm not giving it a toy prompt. I'm asking for a distributed systems architecture — 
   something that would take a mid-level engineer a full afternoon.

   Watch what K-CLI does with it."

---

### SCENE 2B — Strands Agent Tool Orchestration Live (1:10 – 1:45)

ON SCREEN: Rich progress bars appear in TUI output panel. Real execution visible.

  [Strands Agent] Planning execution graph...
     Task decomposed into 4 deterministic tool invocations.

  [TOOL 1/4] triage_and_heal_incident
     ████████████████████ 100%  Scope isolated: coordinator.py, state.py

  [TOOL 2/4] verify_code_file (Pre-generation AST scan)
     ████████████████████ 100%  No syntax conflicts in scope

  [TOOL 3/4] verify_code_file (Post-generation compiler check)
     Patching: coordinator.py — running py_compile...
     COMPILER FAILURE CAUGHT:
         Line 47: SyntaxError — missing return type annotation on propose_state()
     Auto-healing: Adding -> ConsensusState return annotation...
     Re-compiling...
     ████████████████████ 100%  COMPILER PASS (attempt 2)

  [TOOL 4/4] apply_surgical_patch
     ████████████████████ 100%  Patch staged. 0 regressions.

NARRATION:
  "This is what sets K-CLI apart from every other AI code tool. It does not just generate 
   code and hope for the best.

   It catches its own compiler error on the first attempt, self-heals the type annotation, 
   recompiles to a confirmed green pass, and ONLY THEN stages the patch. No hallucinated 
   imports. No broken syntax reaching your repo. Closed-loop, compiler-verified engineering."

---

### SCENE 2C — The Verified Code Diff (1:45 – 2:10)

ON SCREEN: Syntax-highlighted diff with line numbers. Camera gently zooms in.

  --- a/src/coordinator.py
  +++ b/src/coordinator.py
  @@ -44,7 +44,12 @@
       class ConsensusCoordinator:
  -        def propose_state(self, new_state):
  -            self._lock.acquire()
  -            self._state = new_state
  +        def propose_state(self, new_state: NodeState) -> ConsensusState:
  +            """Atomic state transition with lock-free CAS and heartbeat guard."""
  +            if not self._heartbeat.is_alive():
  +                raise HeartbeatTimeoutError("Leader lease expired")
  +            if self._cas.compare_and_swap(self._state, new_state):
  +                return ConsensusState(accepted=True, epoch=self._epoch)
  +            return ConsensusState(accepted=False, reason="CAS conflict")

  Compiler: PASSED   Tests: 3/3   Staged to git index

NARRATION:
  "Compiler verified. Tests passing. And every decision — the heartbeat guard, the CAS 
   operation, the return type — is traceable back to the original prompt."

---
---

# ACT 3: THE BACKGROUND HERO — AUTONOMOUS DAEMON + BEDROCK AGENTCORE
## 2:10 – 3:20 (70 seconds)

---

### SCENE 3A — Launch the Daemon (2:10 – 2:30)

ON SCREEN: SPLIT TERMINAL — two panes side by side.
  LEFT: Developer editing code in their editor normally
  RIGHT: User types:
    $ k-cli daemon --repo .

    K-CLI Background Healer Daemon — ACTIVE
       Watching: /home/krishiv/startup-api/
       Mode: AUTONOMOUS — surfaces only for architectural decisions
       Status: HEALTHY — monitoring 47 test suites

LEFT PANE: Developer introduces a real bug — broken import:
  `from auth imprt validate`  (typo: "imprt" instead of "import")
  File saved. Editor shows no warning.

NARRATION:
  "This is the feature the Professional Agents track was built for. The daemon runs 
   silently in the background while you focus on building.

   I am going to introduce a real bug right now. A broken import in auth_service.py. 
   Watch what happens."

---

### SCENE 3B — Daemon Catches and Heals Silently (2:30 – 3:05)

ON SCREEN:
  LEFT: Developer still typing, completely unaware.
  RIGHT: Daemon activates:

    [2:31] TEST FAILURE DETECTED
       Error: ImportError — cannot import name 'validate' from 'auth'
       Affected: 12 downstream tests

    [2:31] Auto-healing via Strands Agent...
       Triage: Line 3 — typo 'imprt' → 'import'
       Patch: Applied
       Verify: py_compile PASS  pytest: 12/12 PASS
       Commit: "fix(auth): correct import typo [auto-healed by K-CLI daemon]"

    [2:34] REPOSITORY HEALTHY
       1 regression auto-healed. 0 interruptions. 
       Human sign-off NOT required (confidence: 99.1%)

  LEFT: Developer is STILL TYPING. They never knew it happened.
  [Let 2 full seconds of silence breathe here before narration continues]

NARRATION:
  "Three seconds. One regression. Zero interruptions. The developer kept building. 
   They will never know it happened.

   This is what 'Agents for Humans' actually means — an agent that handles the noise 
   so humans can focus on the signal."

---

### SCENE 3C — Bedrock AgentCore Export (3:05 – 3:20)

ON SCREEN: Terminal. User types:
  $ k-cli bedrock export

    Exported OpenAPI 3.0 Action Group Schema → openapi_schema.json
      Actions: triage_and_heal_incident, verify_code_file, apply_surgical_patch,
               resolve_git_merge_conflict, immunity_probe, audit_swarm, scaffold_project

    Exported CloudFormation SAM Template → template.yaml
      Stack: K-CLI-AgentCore-Production | Runtime: python3.12 | Region: us-east-1

    Bedrock AgentCore Bundle ready for: aws bedrock deploy

NARRATION:
  "For enterprise teams — one command exports a complete Amazon Bedrock AgentCore bundle: 
   OpenAPI action groups and CloudFormation templates, ready for AWS in minutes."

---
---

# ACT 4: THE KILLER FEATURES — CONFLICT STUDIO AND CHAOS IMMUNITY
## 3:20 – 4:15 (55 seconds)

---

### SCENE 4A — 3-Way AST Conflict Resolution Live (3:20 – 3:50)

ON SCREEN: Terminal. User types:
  $ k-cli conflict src/payment_service.py

  Parsing 3-way AST conflict in: src/payment_service.py
     Scope: class PaymentService → def process_payment()
     Yours:    async retry wrapper + Decimal typing
     Theirs:   retry logic with exponential backoff
     Base:     original synchronous implementation

  Semantic merge strategy: BOTH sides preserved
     → Your Decimal type annotation: KEPT
     → Their retry logic with backoff: INTEGRATED
     → Base synchronous blocking: REMOVED

  Merged. py_compile: PASS. git add: STAGED.

Then show the clean merged function — no conflict markers, both features present.

NARRATION:
  "Standard git merge tools see text. K-CLI sees Python. It parses the abstract syntax 
   tree of all three versions and semantically merges both feature branches — keeping what 
   matters from each side.

   Merge conflict resolved in 30 seconds. No manual editing. Both features ship."

---

### SCENE 4B — Chaos Immunity Shield (3:50 – 4:15)

ON SCREEN: Terminal. User types:
  $ k-cli immune src/engine.py

  CHAOS IMMUNITY SHIELD — scanning src/engine.py

     VULNERABILITY 1: Unguarded None dereference
        Line 89: result.data.decode() — result could be None on timeout
        Inoculating: Adding `if result is None: raise TimeoutError(...)`

     VULNERABILITY 2: Bare except clause swallowing errors silently  
        Line 134: except: pass
        Inoculating: except Exception as e: logger.error(f"Engine error: {e}")

     VULNERABILITY 3: Missing timeout on external HTTP call
        Line 201: requests.get(endpoint) — no timeout, blocks indefinitely
        Inoculating: requests.get(endpoint, timeout=30)

  Generated: tests/chaos/test_engine_adversarial.py (4 adversarial test cases)
  All 4 chaos tests PASS against inoculated code.
  Patches staged. Your code is now chaos-immune.

NARRATION:
  "Before bugs find you, K-CLI finds them first. The Chaos Immunity Shield scans for 
   brittle patterns, writes real adversarial pytest suites against those exact scenarios, 
   and patches the vulnerabilities proactively.

   Not reactive debugging. Proactive immunity."

---
---

# ACT 5: THE FINALE — BANKAI MODELS, INTENT SENSING, CALL TO ACTION
## 4:15 – 5:00 (45 seconds)

---

### SCENE 5A — Model Hub and Bankai Spotlight (4:15 – 4:35)

ON SCREEN: Web UI at http://localhost:8000 — Model Hub tab.
Camera pans to the two Bankai model cards.

  BANKAI-10B FRONTIER CODER
    Fine-tuned by Krishiv Joshi | Qwen2.5-Coder base | Dual Tesla T4
    Optimized for: surgical diffs, compiler verification
    huggingface.co/krishivjoshi/bankai-10b

  BANKAI-7B ULTRA-FAST CODER
    Fine-tuned by Krishiv Joshi | Rapid responses, sub-100ms
    huggingface.co/krishivjoshi/bankai-7b

Then switch to TUI — show Intent Sensor routing in real time:
  User types: "hey what does this function do"
  STATUS: → CHAT intent → Bankai-7B selected [<0.1ms]

  User types: "refactor the consensus module to use Raft algorithm"
  STATUS: → BUILD intent → Bankai-10B + Strands selected [<0.1ms]

NARRATION:
  "Krishiv Joshi fine-tuned two custom models on Hugging Face — Bankai-10B for deep 
   architectural reasoning and Bankai-7B for sub-100ms rapid responses.

   Combined with a sub-millisecond adaptive intent sensor, K-CLI automatically routes 
   casual questions to the fast model and complex engineering to the frontier model.
   Always the right intelligence, instantly."

---

### SCENE 5B — The Grand Finale Scorecard (4:35 – 5:00)

ON SCREEN: Terminal clears. A final summary panel fills the entire screen.
Hold this for 20 full seconds. URL large and visible.

  ╔══════════════════════════════════════════════════════════════╗
  ║           K-CLI FOR DEVS — WHAT WE BUILT                    ║
  ╠══════════════════════════════════════════════════════════════╣
  ║  AWS Strands Agents SDK        ✔ Multi-tool orchestration   ║
  ║  Amazon Bedrock AgentCore      ✔ OpenAPI + CloudFormation    ║
  ║  Autonomous Background Daemon  ✔ Zero-interruption healing   ║
  ║  Closed-Loop Compiler Guard    ✔ py_compile + cargo check    ║
  ║  3-Way AST Conflict Studio     ✔ Semantic merge, both kept   ║
  ║  Chaos Immunity Shield         ✔ Proactive adversarial fix   ║
  ║  Bankai-10B & 7B Models        ✔ Fine-tuned on HuggingFace   ║
  ║  Sub-ms Intent Sensor          ✔ <0.1ms model routing        ║
  ║  Three Complete UI Tiers       ✔ TUI · Web · REPL            ║
  ╠══════════════════════════════════════════════════════════════╣
  ║  Tests: 70/70 passing   License: MIT   Built in: 6 weeks    ║
  ╠══════════════════════════════════════════════════════════════╣
  ║  github.com/krishivjoshi219-collab/K-Cli-for-Devs           ║
  ║  huggingface.co/krishivjoshi                                  ║
  ╚══════════════════════════════════════════════════════════════╝

NARRATION — SLOW DOWN, EACH LINE LANDS FULLY:
  "Developers lose hours every day to noise.

   K-CLI eliminates the noise. It works in the background. It proves its own code compiles.
   It heals regressions before you notice them.
   And it does it all autonomously — surfacing only when a human decision truly matters.

   Built in six weeks. Open source. MIT licensed.

   K-CLI for Devs — give your developers their hours back.

   Clone the repo today."

---
---

# VOICEOVER RECORDING CHEAT SHEET

Act | File                              | Duration | Tone
----|-----------------------------------|----------|----------------------------------
1   | act_1_the_hook.mp3                | 0:50     | Empathetic pain → Excited reveal
2   | act_2_strands_and_compilers.mp3   | 1:20     | Confident, technical but clear
3   | act_3_bedrock_and_daemon.mp3      | 1:10     | Quiet awe → "did you see that?"
4   | act_4_conflicts_and_chaos.mp3     | 0:55     | Fast, punchy, zero filler
5   | act_5_bankai_models_and_finale.mp3| 0:45     | Warm, memorable, leave it with them

---

# RECORDING CHECKLIST

[ ] Terminal: 1920x1080, font 16, dark background, no desktop clutter
[ ] TUI: launched with k-cli ui — cursor always moving during narration
[ ] Web UI: launched with k-cli web ui at http://localhost:8000
[ ] REPL: launched with k-cli simple for Tier 3 flash
[ ] Daemon: run in split terminal — real k-cli daemon in right pane
[ ] All 5 MP3s playing in sync in OBS or DaVinci audio track
[ ] Export 1080p 30fps MP4
[ ] No desktop icons visible, no notification popups
[ ] Every prompt typed live with typing animation — no copy-paste

---

Script Version 2.0 — Active Demo with Zero Passive Screens
Author: Krishiv Joshi | Project Bankai | AWS Agents for Humans Hackathon
