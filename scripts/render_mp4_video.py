#!/usr/bin/env python3
"""
render_mp4_video.py - 1080p 5-Minute Championship Video Generator for K-CLI
Project Bankai v1.0.0 — Built for AWS "Agents for Humans" Hackathon (Professional Agents Track)
Developer: Krishiv Joshi (@krishivjoshi)

Combines live terminal rendering, syntax diffs, HUD telemetry, and AI voiceover audio
into a master 1080p 30fps MP4 video: demo_assets/recordings/k_cli_5min_championship_demo.mp4
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path("/home/k/K-Cli-for-Devs").resolve()
ASSETS_DIR = ROOT_DIR / "demo_assets"
VOICEOVER_DIR = ASSETS_DIR / "voiceover"
RECORDINGS_DIR = ASSETS_DIR / "recordings"

WIDTH, HEIGHT = 1920, 1080
FPS = 30
TOTAL_DURATION_SEC = 300  # Exactly 5:00 minutes (300 seconds)

# Color Palette (Dark Cyberpunk Theme)
BG_COLOR = (13, 17, 23)
TEXT_COLOR = (240, 246, 252)
CYAN = (88, 166, 255)
GREEN = (63, 185, 80)
YELLOW = (210, 153, 34)
RED = (255, 123, 114)
PURPLE = (188, 140, 255)
DIM_GRAY = (110, 118, 129)
PANEL_BG = (22, 27, 34)
BORDER_COLOR = (48, 54, 61)


def find_mono_font(size: int = 22):
    font_candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf",
    ]
    for c in font_candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def find_bold_font(size: int = 24):
    font_candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
    ]
    for c in font_candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return find_mono_font(size)


def build_master_audio(output_audio_path: Path):
    """Concatenates all 5 voiceover tracks with timeline alignment into a single 5-minute MP3."""
    print("🎧 Assembling master 5-minute audio track...")
    
    # Act 1: 0:00 - 0:50
    # Act 2: 0:50 - 2:05 (start at 50s)
    # Act 3: 2:05 - 3:15 (start at 125s)
    # Act 4: 3:15 - 4:15 (start at 195s)
    # Act 5: 4:15 - 5:00 (start at 255s)
    
    a1 = VOICEOVER_DIR / "act_1_the_hook.mp3"
    a2 = VOICEOVER_DIR / "act_2_strands_and_compilers.mp3"
    a3 = VOICEOVER_DIR / "act_3_bedrock_and_daemon.mp3"
    a4 = VOICEOVER_DIR / "act_4_conflicts_and_chaos.mp3"
    a5 = VOICEOVER_DIR / "act_5_bankai_models_and_finale.mp3"

    ffmpeg_bin = "/home/k/.local/bin/ffmpeg" if os.path.exists("/home/k/.local/bin/ffmpeg") else "ffmpeg"

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(a1),
        "-i", str(a2),
        "-i", str(a3),
        "-i", str(a4),
        "-i", str(a5),
        "-filter_complex",
        (
            "[0:a]adelay=0|0,apad=pad_dur=300[a0];"
            "[1:a]adelay=50000|50000,apad=pad_dur=300[a1];"
            "[2:a]adelay=125000|125000,apad=pad_dur=300[a2];"
            "[3:a]adelay=195000|195000,apad=pad_dur=300[a3];"
            "[4:a]adelay=255000|255000,apad=pad_dur=300[a4];"
            "[a0][a1][a2][a3][a4]amix=inputs=5:duration=longest:dropout_transition=0,volume=1.8[outa]"
        ),
        "-map", "[outa]",
        "-t", "300",
        str(output_audio_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"✔ Master audio created: {output_audio_path}")


def draw_panel(draw, x, y, w, h, title="", border_color=BORDER_COLOR, bg_color=PANEL_BG, title_color=CYAN, font=None, bold_font=None):
    """Draws a rounded cyberpunk window panel with title bar."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=bg_color, outline=border_color, width=2)
    # Window controls (red, yellow, green dots)
    draw.ellipse([x + 15, y + 12, x + 25, y + 22], fill=(255, 95, 86))
    draw.ellipse([x + 32, y + 12, x + 42, y + 22], fill=(255, 189, 46))
    draw.ellipse([x + 49, y + 12, x + 59, y + 22], fill=(39, 201, 63))
    
    if title:
        draw.text((x + 75, y + 8), title, fill=title_color, font=bold_font)
    draw.line([x, y + 36, x + w, y + 36], fill=border_color, width=1)


def draw_subtitles(draw, text, font):
    """Draws voiceover narration banner at bottom."""
    sub_y = HEIGHT - 110
    draw.rounded_rectangle([60, sub_y, WIDTH - 60, sub_y + 80], radius=8, fill=(20, 24, 32), outline=YELLOW, width=2)
    draw.text((80, sub_y + 10), "🔊 AI VOICEOVER NARRATION", fill=YELLOW, font=font)
    draw.text((80, sub_y + 40), f'"{text}"', fill=(255, 255, 255), font=font)


def render_full_mp4():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    master_audio = RECORDINGS_DIR / "demo_audio_master.mp3"
    output_mp4 = RECORDINGS_DIR / "k_cli_5min_championship_demo.mp4"

    build_master_audio(master_audio)

    font_sm = find_mono_font(18)
    font_md = find_mono_font(21)
    font_lg = find_mono_font(24)
    font_bold = find_bold_font(22)
    font_title = find_bold_font(32)

    ffmpeg_bin = "/home/k/.local/bin/ffmpeg" if os.path.exists("/home/k/.local/bin/ffmpeg") else "ffmpeg"

    # Start ffmpeg process reading raw frames from stdin
    ffmpeg_cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(master_audio),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_mp4)
    ]

    print(f"🎬 Rendering 1080p Video to '{output_mp4}' at {FPS} FPS (Total: {TOTAL_DURATION_SEC * FPS} frames)...")
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    total_frames = TOTAL_DURATION_SEC * FPS

    # Pre-render scene logic per second
    for frame_idx in range(total_frames):
        t = frame_idx / FPS  # Time in seconds (0.0 to 300.0)

        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Header Bar
        draw.rectangle([0, 0, WIDTH, 50], fill=(18, 22, 30))
        draw.text((30, 10), "⚡ K-CLI FOR DEVS — AUTONOMOUS ENGINEERING AGENT (AWS STRANDS & BEDROCK)", fill=CYAN, font=font_title)
        draw.text((WIDTH - 380, 14), f"TIME: {int(t//60):02d}:{int(t%60):02d} / 05:00  [REC ●]", fill=RED, font=font_bold)
        draw.line([0, 50, WIDTH, 50], fill=BORDER_COLOR, width=2)

        # =====================================================================
        # ACT 1: 0:00 - 0:50 (The Cold Open & 3 UI Tiers)
        # =====================================================================
        if t < 50:
            if t < 15:
                # Scene 1A: Pain Montage
                draw_panel(draw, 60, 80, 560, 420, "❌ CI/CD Pipeline Crash (11:47 PM)", RED, font=font_md, bold_font=font_bold)
                draw.text((80, 130), "FAILED test_auth.py::test_token_validation\n  AttributeError: 'NoneType' object\n  has no attribute 'decode'", fill=RED, font=font_md)
                draw.text((80, 230), "FAILED test_router.py::test_dispatch\n  RuntimeError: Lock never released", fill=RED, font=font_md)
                draw.text((80, 310), "========== 47 failed in 61.3s ==========", fill=(255, 80, 80), font=font_bold)

                draw_panel(draw, 660, 80, 580, 420, "⚠️ 3-Way AST Merge Conflict", YELLOW, font=font_md, bold_font=font_bold)
                draw.text((680, 130), "<<<<<<< HEAD (your feature: async pay)\n  def process_payment(self, amount: Decimal):\n      return self._stripe.charge(...)\n||||||| base\n  def process_payment(self, amount): ...\n=======\n  def process_payment(self, amount, retries=3):\n>>>>>>> upstream/main", fill=TEXT_COLOR, font=font_sm)

                draw_panel(draw, 1280, 80, 580, 420, "🚨 Rust Compiler Mismatch", RED, font=font_md, bold_font=font_bold)
                draw.text((1300, 130), "error[E0308]: mismatched types\n  --> src/consensus/coordinator.rs:214\n   | expected `Arc<Mutex<State>>`\n   |    found `Mutex<State>`\n\nPipeline aborted. On-call paged.", fill=RED, font=font_md)

                draw_subtitles(draw, "Three AM. 47 failing tests. A 3-way merge conflict that makes no sense. None of this is hard engineering — it is all noise.", font_md)
            else:
                # Scene 1B: K-CLI Reveal & 3 UI Tiers
                draw_panel(draw, 60, 80, 1800, 850, "⚡ K-CLI FOR DEVS — 3 UNIFIED UI TIERS (SOVEREIGN ENGINE)", CYAN, font=font_md, bold_font=font_bold)
                
                # Tier 1 Card
                draw.rounded_rectangle([100, 150, 620, 750], radius=8, fill=(20, 26, 36), outline=CYAN, width=2)
                draw.text((120, 180), "TIER 1: FLAGSHIP CYBER TUI", fill=CYAN, font=font_bold)
                draw.text((120, 230), "• 3-Pane full-screen layout\n• Live RAM & Token HUD telemetry\n• Thinking Radar & Subagent swarm\n• Zero-freeze asynchronous workers\n• Full keyboard hotkeys & modals\n\nLaunch: $ k-cli ui", fill=TEXT_COLOR, font=font_md)

                # Tier 2 Card
                draw.rounded_rectangle([660, 150, 1180, 750], radius=8, fill=(20, 26, 36), outline=PURPLE, width=2)
                draw.text((680, 180), "TIER 2: CYBER STATION WEB UI", fill=PURPLE, font=font_bold)
                draw.text((680, 230), "• Modern glassmorphism dashboard\n• Real-time WebSocket token stream\n• Secure API Credentials Vault\n• Interactive Multi-Model Hub\n• Responsive auto-scaling engine\n\nLaunch: $ k-cli web ui", fill=TEXT_COLOR, font=font_md)

                # Tier 3 Card
                draw.rounded_rectangle([1220, 150, 1740, 750], radius=8, fill=(20, 26, 36), outline=GREEN, width=2)
                draw.text((1240, 180), "TIER 3: STREAMLINED REPL", fill=GREEN, font=font_bold)
                draw.text((1240, 230), "• Sub-50ms instant boot time\n• Full mouse & scroll wheel support\n• SQLite persistent command history\n• Direct terminal pipe workflows\n• Ultra-lightweight footprint (<15MB)\n\nLaunch: $ k-cli simple", fill=TEXT_COLOR, font=font_md)

                draw_subtitles(draw, "Introducing K-CLI for Devs: Built with the AWS Strands Agents SDK and Amazon Bedrock AgentCore. 3 complete UIs, 1 sovereign engine.", font_md)

        # =====================================================================
        # ACT 2: 0:50 - 2:05 (AWS Strands Agent & Closed-Loop Compilers)
        # =====================================================================
        elif t < 125:
            draw_panel(draw, 60, 80, 1800, 850, "🧠 AWS STRANDS AGENTS SDK — CLOSED-LOOP COMPILER GUARDRAILS", CYAN, font=font_md, bold_font=font_bold)
            
            # Prompt Box
            draw.rounded_rectangle([100, 140, 1760, 240], radius=6, fill=(18, 22, 30), outline=GREEN, width=1)
            prompt_text = "k-cli > /strands Architect a distributed lock-free consensus coordinator in Python with heartbeat failover, atomic state transitions, and adversarial chaos tests."
            chars_to_show = int(min(len(prompt_text), (t - 50) * 35))
            draw.text((120, 160), prompt_text[:chars_to_show], fill=TEXT_COLOR, font=font_bold)

            # Tool Execution Graph (after 60s)
            if t >= 58:
                draw.text((100, 260), "🧠 [Strands Agent] Executing Deterministic Tool Pipeline with Closed-Loop Proof:", fill=YELLOW, font=font_bold)
                
                tools = [
                    ("🔍 TOOL 1/4: triage_and_heal_incident", "Isolated scope: coordinator.py, state.py", GREEN),
                    ("⚙️ TOOL 2/4: verify_code_file (AST Scan)", "Clean syntax graph verified", GREEN),
                    ("🛡️ TOOL 3/4: verify_code_file (py_compile)", "Caught missing return type annotation on attempt 1 -> Auto-healed to 100% PASS!", GREEN),
                    ("🩹 TOOL 4/4: apply_surgical_patch", "Line-accurate fuzzy patch staged to git index", GREEN),
                ]
                for idx, (tname, tdesc, col) in enumerate(tools):
                    tool_y = 310 + idx * 65
                    draw.rounded_rectangle([100, tool_y, 1760, tool_y + 55], radius=6, fill=(20, 26, 36), outline=col, width=1)
                    draw.text((120, tool_y + 12), tname, fill=col, font=font_bold)
                    draw.text((700, tool_y + 14), tdesc, fill=TEXT_COLOR, font=font_md)

            # Diff Window (after 85s)
            if t >= 80:
                draw_panel(draw, 100, 600, 1660, 290, "✔ Surgical Verified Diff (py_compile: PASS | pytest: 3/3 PASS)", GREEN, font=font_md, bold_font=font_bold)
                diff_lines = [
                    "--- a/src/coordinator.py",
                    "+++ b/src/coordinator.py",
                    "@@ -44,7 +44,12 @@",
                    "-    def propose_state(self, new_state):",
                    "+    def propose_state(self, new_state: NodeState) -> ConsensusState:",
                    "+        '''Atomic state transition with lock-free CAS and heartbeat guard.'''",
                    "+        if not self._heartbeat.is_alive(): raise HeartbeatTimeoutError()",
                    "+        if self._cas.compare_and_swap(self._state, new_state): return ConsensusState(accepted=True)",
                ]
                for d_idx, d_line in enumerate(diff_lines):
                    col = GREEN if d_line.startswith("+") else (RED if d_line.startswith("-") else DIM_GRAY)
                    draw.text((130, 650 + d_idx * 24), d_line, fill=col, font=font_md)

            draw_subtitles(draw, "K-CLI catches its own compiler error on attempt 1, self-heals the type annotation, and ONLY THEN stages the verified patch.", font_md)

        # =====================================================================
        # ACT 3: 2:05 - 3:15 (Background Healer Daemon & Bedrock AgentCore)
        # =====================================================================
        elif t < 195:
            draw_panel(draw, 60, 80, 1800, 850, "🔄 AUTONOMOUS BACKGROUND HEALER DAEMON & BEDROCK AGENTCORE", GREEN, font=font_md, bold_font=font_bold)
            
            # Left Pane: Developer Editor
            draw.rounded_rectangle([100, 140, 880, 580], radius=8, fill=(18, 22, 30), outline=CYAN, width=2)
            draw.text((130, 165), "💻 PANE 1: DEVELOPER WORKING IN IDE", fill=CYAN, font=font_bold)
            draw.text((130, 220), "Editing: src/auth_service.py\n\n1 | from typing import Optional\n2 | from dataclasses import dataclass\n3 | from auth imprt validate  # <-- TYPO INTRODUCED AT 2:31 PM\n4 | \n5 | def handle_login(req):\n6 |     return validate(req.token)\n\n[Developer continues typing in another file...]", fill=TEXT_COLOR, font=font_md)

            # Right Pane: Background Daemon
            draw.rounded_rectangle([920, 140, 1760, 580], radius=8, fill=(18, 22, 30), outline=GREEN, width=2)
            draw.text((950, 165), "🤖 PANE 2: K-CLI DAEMON IN BACKGROUND", fill=GREEN, font=font_bold)
            draw.text((950, 220), "Status: 🟢 HEALTHY — Monitoring 47 test suites\n\n🚨 [2:31:02] TEST FAILURE DETECTED in src/auth_service.py\n   Error: ImportError — cannot import name 'validate'\n\n🔄 [2:31:03] Auto-healing via Strands Agent...\n   ✔ Triage: Line 3 typo `imprt` -> `import`\n   ✔ Verify: py_compile PASS | pytest: 12/12 PASS\n   ✔ Commit: 'fix(auth): correct import typo [auto-healed]'\n\n✅ [2:31:05] REPOSITORY HEALTHY (0 Interruptions to Developer!)", fill=GREEN, font=font_md)

            # Bedrock Export Bar
            if t >= 165:
                draw_panel(draw, 100, 600, 1660, 290, "☁️ Amazon Bedrock AgentCore Export (OpenAPI 3.0 + SAM Template)", CYAN, font=font_md, bold_font=font_bold)
                draw.text((130, 650), "✔ Exported OpenAPI 3.0 Action Groups -> openapi_schema.json (7 Actions)\n✔ Exported CloudFormation SAM Template -> template.yaml (Stack: K-CLI-AgentCore-Production)\n✔ Ready for instant enterprise deployment: $ aws bedrock deploy", fill=TEXT_COLOR, font=font_md)

            draw_subtitles(draw, "Three seconds. One regression. Zero interruptions. The developer kept building. This is what Agents for Humans actually means.", font_md)

        # =====================================================================
        # ACT 4: 3:15 - 4:15 (3-Way Conflict Studio & Chaos Immunity Shield)
        # =====================================================================
        elif t < 255:
            draw_panel(draw, 60, 80, 1800, 850, "⚔️ 3-WAY AST CONFLICT STUDIO & PROACTIVE CHAOS IMMUNITY SHIELD", PURPLE, font=font_md, bold_font=font_bold)

            # Conflict Studio Card
            draw.rounded_rectangle([100, 140, 900, 750], radius=8, fill=(20, 26, 36), outline=YELLOW, width=2)
            draw.text((130, 170), "🧩 3-WAY AST CONFLICT STUDIO", fill=YELLOW, font=font_bold)
            draw.text((130, 220), "$ k-cli conflict src/payment_service.py\n\n🔍 Parsing 3-way AST conflict...\n   Scope: class PaymentService -> def process_payment()\n   Yours:  async retry wrapper + Decimal typing\n   Theirs: retry logic with exponential backoff\n   Base:   original synchronous blocking call\n\n🧩 Semantic Merge Strategy:\n   → Your Decimal typing: KEPT\n   → Their retry backoff: INTEGRATED\n   → Base blocking code: REMOVED\n\n✔ Merged cleanly. py_compile: PASS. git add: STAGED.", fill=TEXT_COLOR, font=font_md)

            # Chaos Immunity Card
            draw.rounded_rectangle([940, 140, 1760, 750], radius=8, fill=(20, 26, 36), outline=RED, width=2)
            draw.text((970, 170), "☠️ CHAOS IMMUNITY SHIELD", fill=RED, font=font_bold)
            draw.text((970, 220), "$ k-cli immune src/engine.py\n\n🛡️ Scanning AST for brittle production hazards:\n\n⚠️ VULN 1: Unguarded None dereference (Line 89)\n   → Inoculated: Added `if result is None: raise ...`\n\n⚠️ VULN 2: Bare except clause (Line 134)\n   → Inoculated: `except Exception as e: log(e)`\n\n⚠️ VULN 3: Missing HTTP timeout (Line 201)\n   → Inoculated: `requests.get(..., timeout=30)`\n\n📝 Synthesized: tests/chaos/test_engine_adversarial.py\n✔ 4/4 Adversarial Chaos Tests PASS! Code is immune.", fill=TEXT_COLOR, font=font_md)

            draw_subtitles(draw, "Standard git sees text — K-CLI sees Python AST. And before bugs find you, Chaos Immunity Shield inoculates vulnerabilities proactively.", font_md)

        # =====================================================================
        # ACT 5: 4:15 - 5:00 (Bankai-10B & 7B Models, Intent Sensor & Finale)
        # =====================================================================
        else:
            draw_panel(draw, 60, 80, 1800, 850, "🚀 KRISHIV JOSHI BANKAI MODELS & CHAMPIONSHIP SCORECARD", CYAN, font=font_md, bold_font=font_bold)

            # Bankai Model Cards
            draw.rounded_rectangle([100, 140, 900, 380], radius=8, fill=(20, 26, 36), outline=CYAN, width=2)
            draw.text((130, 165), "⚡ BANKAI-10B FRONTIER CODER", fill=CYAN, font=font_bold)
            draw.text((130, 205), "Fine-tuned by Krishiv Joshi on Hugging Face\nBase: Qwen2.5-Coder | Trained: Dual Tesla T4 GPUs\nOptimized for: surgical diffs & compiler proof\nURL: huggingface.co/krishivjoshi/bankai-10b", fill=TEXT_COLOR, font=font_md)

            draw.rounded_rectangle([940, 140, 1760, 380], radius=8, fill=(20, 26, 36), outline=YELLOW, width=2)
            draw.text((970, 165), "🧠 BANKAI-7B ULTRA-FAST CODER", fill=YELLOW, font=font_bold)
            draw.text((970, 205), "Fine-tuned by Krishiv Joshi on Hugging Face\nBase: Qwen2.5-Coder | Trained: Dual Tesla T4 GPUs\nOptimized for: sub-100ms chat & instant repairs\nURL: huggingface.co/krishivjoshi/bankai-7b", fill=TEXT_COLOR, font=font_md)

            # Grand Scorecard Table
            draw.rounded_rectangle([100, 410, 1760, 770], radius=8, fill=(18, 22, 30), outline=GREEN, width=2)
            draw.text((130, 435), "🏆 CHAMPIONSHIP SUBMISSION SCORECARD", fill=GREEN, font=font_bold)
            
            score_text = (
                "• AWS Strands Agents SDK Integration:  ✔ Closed-Loop Deterministic Multi-Tool Orchestration\n"
                "• Amazon Bedrock AgentCore Deployment:  ✔ OpenAPI 3.0 Action Groups & SAM CloudFormation Templates\n"
                "• Autonomous Background Healer Daemon:  ✔ Silent Real-Time Monitoring & Zero-Interruption Regressions Heal\n"
                "• Sovereign UI Tiers:                   ✔ Flagship Cyber TUI · Cyber Station Web UI · Streamlined REPL\n"
                "• Automated Test Suite:                ✔ 70/70 Unit & Integration Tests Passing (100% Green)\n"
                "• Open Source Status:                  ✔ MIT License on GitHub: github.com/krishivjoshi219-collab/K-Cli-for-Devs"
            )
            draw.text((130, 480), score_text, fill=TEXT_COLOR, font=font_md)

            draw_subtitles(draw, "Built in six weeks. Open source. MIT licensed. K-CLI for Devs — give your developers their hours back. Clone the repo today!", font_md)

        # Write raw frame to ffmpeg stdin
        proc.stdin.write(img.tobytes())

        if frame_idx % (FPS * 15) == 0:
            pct = (frame_idx / total_frames) * 100
            print(f"  Rendering Progress: {pct:.1f}% ({int(t//60):02d}:{int(t%60):02d} / 05:00)")

    proc.stdin.close()
    proc.wait()

    if output_mp4.exists():
        size_mb = output_mp4.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 80)
        print("✔ [SUCCESS] 5-MINUTE CHAMPIONSHIP MP4 VIDEO GENERATED!")
        print(f"🎬 Video File: {output_mp4} ({size_mb:.2f} MB)")
        print(f"⏱️ Duration:   5:00 (300 seconds @ 30 FPS)")
        print(f"📺 Resolution: 1920x1080 Full HD")
        print("=" * 80)


if __name__ == "__main__":
    render_full_mp4()
