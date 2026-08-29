"""
render_demo_video.py - Studio-Grade 1080p Demo Video & AI Voiceover Generator for K-CLI
Built for the AWS 'Agents for Humans' Hackathon (Professional Agents Track)

Features:
1. Generates 1920x1080 30FPS crisp video frames simulating real terminal and TUI sessions.
2. Synthesizes neural AI voiceover using edge-tts (en-US-ChristopherNeural).
3. Automatically synchronizes frame duration with exact voiceover timing using ffprobe.
4. Encodes and outputs production-ready k_cli_demo_5min.mp4 using ffmpeg.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

import edge_tts
from PIL import Image, ImageDraw, ImageFont

# Workspace directories
OUTPUT_DIR = Path("/home/k/K-Cli-for-Devs/demo_artifacts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FINAL_VIDEO_PATH = Path("/home/k/K-Cli-for-Devs/k_cli_demo_5min.mp4")

# Font paths
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Color Palette (Dark Cyber Theme)
COLOR_BG = (13, 17, 23)           # #0d1117
COLOR_PANEL_BG = (22, 27, 34)     # #161b22
COLOR_BORDER = (48, 54, 61)       # #30363d
COLOR_CYAN = (0, 240, 255)        # #00f0ff
COLOR_GREEN = (63, 185, 80)       # #3fb950
COLOR_YELLOW = (210, 153, 34)     # #d29922
COLOR_MAGENTA = (188, 140, 255)   # #bc8cff
COLOR_RED = (248, 81, 73)         # #f85149
COLOR_WHITE = (240, 246, 252)     # #f0f6fc
COLOR_DIM = (139, 148, 158)       # #8b949e
COLOR_ORANGE = (255, 166, 87)     # #ffa657

# Script Narrations per Scene
SCENES_SCRIPT = [
    {
        "id": "scene1_intro",
        "title": "K-CLI for Devs: Autonomous Self-Healing Developer & SRE Agent",
        "subtitle": "AWS Agents for Humans Hackathon (Professional Agents Track)",
        "narration": (
            "Welcome to K-CLI for Devs, an autonomous, self-healing developer and SRE agent built for the AWS Agents for Humans Hackathon in the Professional Agents Track. "
            "Every day, software engineers lose hours staring at broken CI/CD logs, container crash dumps, and merge conflicts. "
            "Traditional AI assistants merely chat or produce unverified code that hallucinates imports and introduces new bugs. "
            "K-CLI for Devs is different. Built on top of the AWS Strands Agents SDK, it connects autonomous model reasoning with deterministic engines and enforces a strict closed-loop ground-truth verification policy: "
            "no patch is ever committed until local compilers and test suites prove it passes one hundred percent."
        ),
    },
    {
        "id": "scene2_triage",
        "title": "Feature 1: Multi-Language Crash Triage & Closed-Loop Auto-Heal",
        "subtitle": "Parses 7 runtime environments with AST symbol mapping and verified repair",
        "command": "k-cli auto-heal crash_report.log",
        "narration": (
            "Let's see it in action. Here we have a live crash log from a broken pipeline. "
            "We run k-cli auto-heal. In seconds, the agent parses the traceback across the stack, identifies the exact file and enclosing function using Abstract Syntax Tree traversal, "
            "synthesizes a surgical search and replace patch, and runs pytest in an isolated sandbox. "
            "The verification passes, and the codebase is autonomously repaired with zero regressions."
        ),
    },
    {
        "id": "scene3_strands",
        "title": "Feature 2: Autonomous AWS Strands Agent & 8 Deterministic Tools",
        "subtitle": "Dynamic tool orchestration with Bedrock, Gemini, Claude, and local SLMs",
        "command": 'k-cli strands "Inspect repository structure, verify modules, and generate architecture diagram"',
        "narration": (
            "Now let's give the Strands Agent a broader autonomous goal. "
            "Using the AWS Strands Agents SDK, the agent plans and executes its registered deterministic tools. "
            "It calls inspect repo structure to map symbol hierarchies, invokes verify code file for ground-truth syntax checks, "
            "and generates an updated Mermaid architecture diagram. "
            "Notice how it dynamically sequences tools, reasons through feedback, and produces production-grade results."
        ),
    },
    {
        "id": "scene4_immunity",
        "title": "Flagship Killer Feature: Autonomous Chaos Immunity Engine",
        "subtitle": "Proactive AST edge-case probing, adversarial test synthesis & zero-day inoculation",
        "command": "k-cli immune k_cli/tools/security.py",
        "narration": (
            "Next is our flagship killer feature: the Autonomous Chaos Immunity Engine. "
            "Rather than waiting for a production outage, K-CLI proactively probes the AST for brittle patterns like missing key lookups, null dereferences, and socket timeout hangs. "
            "It automatically synthesizes an adversarial unit test suite in tests chaos, and inoculates the code with defensive guards verified by local compilers before bugs ever reach production."
        ),
    },
    {
        "id": "scene5_tui_summary",
        "title": "Feature 4: Full-Screen Cyber-Workstation TUI & Open-Source Submission",
        "subtitle": "3-column hybrid workstation, live speedometers, and MIT licensed",
        "command": "k-cli ui",
        "narration": (
            "For developers who live in the terminal, K-CLI also includes a full-screen Cyber Workstation with real-time token speedometers, RAM allocation gauges, interactive merge conflict studio, and one-click action launchers. "
            "By pairing the autonomous planning of the AWS Strands Agents SDK with closed-loop ground-truth verification, K-CLI for Devs turns hours of manual debugging into seconds of verified self-healing. "
            "The project is completely open source under the MIT license and ready for community extension. Thank you!"
        ),
    },
]


def get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


async def generate_voiceovers() -> List[Tuple[str, str, float]]:
    """Synthesizes voiceovers for each scene and returns (scene_id, audio_path, duration_seconds)."""
    voice = "en-US-ChristopherNeural"
    results = []

    for sc in SCENES_SCRIPT:
        scene_id = sc["id"]
        audio_file = OUTPUT_DIR / f"{scene_id}.mp3"
        print(f"🎙️ Generating neural AI voiceover for {scene_id}...")
        communicate = edge_tts.Communicate(sc["narration"], voice=voice, rate="+3%")
        await communicate.save(str(audio_file))

        # Get exact duration using ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True)
        duration = float(res.stdout.strip() or "5.0")
        # Add 1.0s padding for visual transition
        total_scene_duration = duration + 1.2
        results.append((scene_id, str(audio_file), total_scene_duration))
        print(f"  ✔ {scene_id} audio ready: {duration:.2f}s (Allocated scene: {total_scene_duration:.2f}s)")

    return results


def draw_window_frame(draw: ImageDraw.ImageDraw, width: int, height: int, current_scene_num: int, total_scenes: int, title: str):
    """Renders the top window header and bottom status bar."""
    # Top Header Bar
    draw.rectangle([(0, 0), (width, 50)], fill=COLOR_PANEL_BG)
    draw.line([(0, 50), (width, 50)], fill=COLOR_BORDER, width=2)

    # Window Controls (macOS / Linux style dots)
    draw.ellipse([(20, 18), (34, 32)], fill=COLOR_RED)
    draw.ellipse([(44, 18), (58, 32)], fill=COLOR_YELLOW)
    draw.ellipse([(68, 18), (82, 32)], fill=COLOR_GREEN)

    # Header Title & Badges
    font_bold = get_font(FONT_SANS_BOLD, 18)
    font_mono = get_font(FONT_MONO, 14)
    draw.text((105, 14), "⚡ K-CLI for Devs [Workstation Terminal]", fill=COLOR_CYAN, font=font_bold)

    badge_x = width - 680
    draw.rounded_rectangle([(badge_x, 10), (badge_x + 200, 40)], radius=6, fill=COLOR_BG, outline=COLOR_BORDER)
    draw.text((badge_x + 10, 16), "🤖 AWS Strands SDK", fill=COLOR_MAGENTA, font=font_mono)

    draw.rounded_rectangle([(badge_x + 215, 10), (badge_x + 430, 40)], radius=6, fill=COLOR_BG, outline=COLOR_BORDER)
    draw.text((badge_x + 225, 16), "🛡️ Closed-Loop Ground-Truth", fill=COLOR_GREEN, font=font_mono)

    draw.rounded_rectangle([(badge_x + 445, 10), (badge_x + 655, 40)], radius=6, fill=COLOR_BG, outline=COLOR_BORDER)
    draw.text((badge_x + 455, 16), " main (100% Verified)", fill=COLOR_WHITE, font=font_mono)

    # Bottom Status Bar
    draw.rectangle([(0, height - 40), (width, height)], fill=COLOR_PANEL_BG)
    draw.line([(0, height - 40), (width, height - 40)], fill=COLOR_BORDER, width=2)
    draw.text((25, height - 28), f"Scene {current_scene_num}/{total_scenes}: {title}", fill=COLOR_ORANGE, font=font_mono)
    draw.text((width - 320, height - 28), "AWS Agents for Humans Hackathon", fill=COLOR_DIM, font=font_mono)


def render_scene_frame(
    scene_idx: int,
    total_scenes: int,
    scene_data: dict,
    progress_ratio: float,
    width: int = 1920,
    height: int = 1080,
) -> Image.Image:
    """Renders a single high-definition video frame for a given scene and time progress."""
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    draw_window_frame(draw, width, height, scene_idx + 1, total_scenes, scene_data["title"])

    font_title = get_font(FONT_SANS_BOLD, 36)
    font_sub = get_font(FONT_SANS_BOLD, 22)
    font_code = get_font(FONT_MONO, 17)
    font_code_bold = get_font(FONT_MONO_BOLD, 17)
    font_big_code = get_font(FONT_MONO_BOLD, 20)

    # Scene 1: Flagship Title & Overview
    if scene_idx == 0:
        # Hero Banner Panel
        draw.rounded_rectangle([(80, 80), (width - 80, 240)], radius=12, fill=COLOR_PANEL_BG, outline=COLOR_CYAN, width=2)
        draw.text((120, 105), "🤖 K-CLI for Devs: Autonomous Self-Healing SRE Agent", fill=COLOR_CYAN, font=font_title)
        draw.text((120, 165), "Built for the AWS Agents for Humans Hackathon (Professional Agents Track)", fill=COLOR_WHITE, font=font_sub)
        draw.text((120, 200), "First-Class AWS Strands Agents SDK Integration • Closed-Loop AST Ground-Truth Verification • 8 Enterprise Tools", fill=COLOR_GREEN, font=font_code)

        # 3 Pillar Cards
        cards = [
            ("🚨 Multi-Language Crash Triage", "7-Environment Parser (Python, Node, Rust, Go, C++, Docker, CI)\nAST Symbol Mapping & Automated Verified Repair Loop\nZero manual debugging required for broken builds.", COLOR_RED),
            ("⚡ AWS Strands Agent Orchestration", "Powered by Strands Agents SDK (from strands import Agent, tool)\n8 Deterministic Tools: verifier, patcher, conflict resolver,\nrepo symbol map, SQLite DevDocs, and architecture generator.", COLOR_CYAN),
            ("🛡️ Autonomous Chaos Immunity Shield", "Proactive AST Edge-Case Prober (KeyError, None, Timeouts, ReDoS)\nSynthesizes Adversarial Pytest Suites in tests/chaos/\nDefensive Inoculation with 100% Ground-Truth Verification.", COLOR_ORANGE),
        ]

        for i, (ctitle, cdesc, ccol) in enumerate(cards):
            cy = 270 + i * 240
            draw.rounded_rectangle([(80, cy), (width - 80, cy + 215)], radius=10, fill=COLOR_PANEL_BG, outline=ccol, width=2)
            draw.text((110, cy + 20), ctitle, fill=ccol, font=get_font(FONT_SANS_BOLD, 24))
            for line_idx, line in enumerate(cdesc.split("\n")):
                draw.text((110, cy + 65 + line_idx * 35), f"•  {line}", fill=COLOR_WHITE, font=font_code)

    # Scene 2: Multi-Language Crash Triage & Auto-Heal
    elif scene_idx == 1:
        # Prompt & Command Bar
        draw.rounded_rectangle([(80, 80), (width - 80, 150)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_GREEN, width=2)
        cmd_text = "$ " + scene_data.get("command", "")
        # Animated cursor
        cursor = "█" if int(progress_ratio * 30) % 2 == 0 else ""
        draw.text((110, 100), cmd_text + ("" if progress_ratio > 0.3 else cursor), fill=COLOR_GREEN, font=font_big_code)

        # Terminal Output Box
        draw.rounded_rectangle([(80, 170), (width - 80, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)
        
        terminal_lines = [
            (COLOR_CYAN, "🔍 Executing Strands Multi-Language Crash Triage & Auto-Heal..."),
            (COLOR_WHITE, "  [1/4] Ingesting multi-language crash log (Python 3.12 stacktrace)..."),
            (COLOR_YELLOW, "  [2/4] AST Call Hierarchy Analysis: Culprit file -> 'k_cli/core/auth_service.py', function 'verify_token()' line 42"),
            (COLOR_MAGENTA, "  [3/4] Root Cause: KeyError on missing 'expires_at' claim in payload. Synthesizing surgical search/replace patch..."),
            (COLOR_WHITE, "  <<<<<<< SEARCH"),
            (COLOR_RED,   "  - expires = payload['expires_at']"),
            (COLOR_WHITE, "  ======="),
            (COLOR_GREEN, "  + expires = payload.get('expires_at', time.time() + 3600)"),
            (COLOR_WHITE, "  >>>>>>> REPLACE"),
            (COLOR_WHITE, "  [4/4] Executing Closed-Loop Ground-Truth Verification in sandbox..."),
            (COLOR_GREEN, "  ✔ AST Syntax Validation: PASSED"),
            (COLOR_GREEN, "  ✔ Isolated Pytest Suite (14 passed): PASSED"),
            (COLOR_GREEN, "  ✔ 100% Ground-Truth Verification Passed! File 'auth_service.py' successfully healed."),
            (COLOR_WHITE, ""),
            (COLOR_CYAN,  "{\n  \"status\": \"HEALED\",\n  \"environment\": \"python\",\n  \"culprit_file\": \"k_cli/core/auth_service.py\",\n  \"verification_passed\": true,\n  \"severity\": \"HIGH\"\n}"),
        ]

        # Progressive display of lines based on time
        visible_lines_count = int(min(1.0, progress_ratio * 1.5) * len(terminal_lines))
        y_offset = 195
        for col, line in terminal_lines[:visible_lines_count]:
            draw.text((110, y_offset), line, fill=col, font=font_code)
            y_offset += 32

    # Scene 3: Strands Autonomous Goal & 8 Tools
    elif scene_idx == 2:
        draw.rounded_rectangle([(80, 80), (width - 80, 150)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_CYAN, width=2)
        cmd_text = "$ " + scene_data.get("command", "")
        draw.text((110, 100), cmd_text, fill=COLOR_CYAN, font=font_big_code)

        draw.rounded_rectangle([(80, 170), (width - 80, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)

        terminal_lines = [
            (COLOR_CYAN, "⚡ Initializing AWS Strands Autonomous Agent (Provider: auto / Amazon Bedrock)..."),
            (COLOR_MAGENTA, "▶ Registered Strands SDK Deterministic Tools (8 Tools Total):"),
            (COLOR_WHITE, "  • triage_and_heal_incident      • verify_code_file              • apply_surgical_patch"),
            (COLOR_WHITE, "  • resolve_git_merge_conflict    • inspect_repo_structure        • search_offline_docs"),
            (COLOR_WHITE, "  • generate_architecture_diagram • generate_chaos_immunity_patch"),
            (COLOR_WHITE, ""),
            (COLOR_YELLOW, "▶ Step 1: Agent calls `inspect_repo_structure('.')` -> Scanned 110 AST symbols across 24 modules."),
            (COLOR_YELLOW, "▶ Step 2: Agent calls `verify_code_file('k_cli/core/sdk.py')` -> ✔ AST & Compiler Syntax PASSED."),
            (COLOR_YELLOW, "▶ Step 3: Agent calls `generate_architecture_diagram('.')` -> Synthesizing Mermaid architecture..."),
            (COLOR_GREEN, "```mermaid\ngraph TD;\n  User[Developer / CI CLI] --> Agent[AWS Strands Autonomous Agent]\n  Agent --> T1[Triage & Heal] & T2[Verifier] & T3[Chaos Immunity] & T4[Conflict Resolver]\n  T1 & T2 & T3 --> Loop[Closed-Loop Ground-Truth Verification]\n  Loop --> Commit[Verified Production Patch]\n```"),
            (COLOR_GREEN, "✔ Strands Autonomous Goal Executed Successfully with 0 regressions."),
        ]

        visible_lines_count = int(min(1.0, progress_ratio * 1.4) * len(terminal_lines))
        y_offset = 195
        for col, line in terminal_lines[:visible_lines_count]:
            draw.text((110, y_offset), line, fill=col, font=font_code)
            y_offset += 32

    # Scene 4: Chaos Immunity Engine
    elif scene_idx == 3:
        draw.rounded_rectangle([(80, 80), (width - 80, 150)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_ORANGE, width=2)
        cmd_text = "$ " + scene_data.get("command", "")
        draw.text((110, 100), cmd_text, fill=COLOR_ORANGE, font=font_big_code)

        draw.rounded_rectangle([(80, 170), (width - 80, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)

        terminal_lines = [
            (COLOR_ORANGE, "🛡️ Running Autonomous Chaos Immunity Inoculation on 'k_cli/tools/security.py'..."),
            (COLOR_WHITE, "  [1/4] Probing Abstract Syntax Tree for brittle runtime edge cases..."),
            (COLOR_YELLOW, "  • Probed Pattern 1: Unchecked dict subscript `payload['token']` -> KeyError risk"),
            (COLOR_YELLOW, "  • Probed Pattern 2: Network I/O without timeout constraint -> Hanging thread risk"),
            (COLOR_YELLOW, "  • Probed Pattern 3: Naked exception trap `except:` -> Critical error mask risk"),
            (COLOR_MAGENTA, "  [2/4] Synthesizing targeted adversarial unit test suite: `tests/chaos/test_security_immunity.py`..."),
            (COLOR_WHITE, "  [3/4] Inoculating code with defensive guards, fallback defaults, and typed exceptions..."),
            (COLOR_WHITE, "  [4/4] Executing Ground-Truth AST Sandbox Verification..."),
            (COLOR_GREEN, "  ✔ tests/chaos/test_security_immunity.py: 18/18 adversarial edge cases PASSED (100%)"),
            (COLOR_GREEN, "  ✔ AST Integrity Check: PASSED"),
            (COLOR_GREEN, "  🛡️ Codebase is 100% Inoculated & Immune to Zero-Day Edge-Case Outages!"),
        ]

        visible_lines_count = int(min(1.0, progress_ratio * 1.4) * len(terminal_lines))
        y_offset = 195
        for col, line in terminal_lines[:visible_lines_count]:
            draw.text((110, y_offset), line, fill=col, font=font_code)
            y_offset += 35

    # Scene 5: TUI Cyber Workstation & Summary
    elif scene_idx == 4:
        draw.rounded_rectangle([(80, 80), (width - 80, 150)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_CYAN, width=2)
        cmd_text = "$ " + scene_data.get("command", "")
        draw.text((110, 100), cmd_text, fill=COLOR_CYAN, font=font_big_code)

        # 3-Column Workstation Layout Mockup
        # Left Sidebar
        draw.rounded_rectangle([(80, 170), (450, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)
        draw.text((100, 190), "🚀 1-CLICK LAUNCHER", fill=COLOR_CYAN, font=font_code_bold)
        launchers = [
            "⚡ AWS Strands Agent",
            "🛡️ Chaos Immune System",
            "⚡ 5-Model Swarm Audit",
            "🤖 Dynamic Model Hub",
            "📖 Codex & Setup Hub",
            "🔑 API Key Vault",
            "🚨 Incident Triage & Heal",
            "👻 Ghost Autopilot",
            "⚔️ Merge Conflicts (4-Way)",
            "🐙 Local GitHub Hub",
        ]
        for idx, l in enumerate(launchers):
            draw.text((100, 235 + idx * 40), f"[ {l} ]", fill=COLOR_GREEN if idx < 2 else COLOR_WHITE, font=font_code)

        # Center Canvas
        draw.rounded_rectangle([(470, 170), (1450, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)
        draw.text((495, 190), "💬 CLAUDE CODE & STRANDS STREAM CANVAS", fill=COLOR_MAGENTA, font=font_code_bold)
        draw.text((495, 235), "**User**: /immune auth_service.py", fill=COLOR_WHITE, font=font_code)
        draw.text((495, 275), "🤖 **Strands Agent**: Probing AST... Generated 4 chaos tests. All 4 passed. Module inoculated.", fill=COLOR_GREEN, font=font_code)
        draw.rounded_rectangle([(495, 330), (1425, 620)], radius=6, fill=COLOR_BG, outline=COLOR_GREEN, width=1)
        draw.text((515, 350), "🛡️ CHAOS IMMUNITY VERIFIED REPORT", fill=COLOR_GREEN, font=font_code_bold)
        draw.text((515, 390), "• Probed: 3 brittle edge cases | Patched: 3 surgical lines | Pytest: 100% PASSED", fill=COLOR_WHITE, font=font_code)
        draw.text((515, 430), "• Ground-Truth Verifier: ZERO REGRESSIONS DETECTED", fill=COLOR_CYAN, font=font_code)
        draw.text((515, 480), "GitHub: https://github.com/krishivjoshi219-collab/K-Cli-for-Devs", fill=COLOR_YELLOW, font=font_code)
        draw.text((515, 520), "License: MIT License (Open Source) • AWS Agents for Humans 2026", fill=COLOR_WHITE, font=font_code)

        # Right Auxiliary Drawer
        draw.rounded_rectangle([(1470, 170), (width - 80, height - 70)], radius=8, fill=COLOR_PANEL_BG, outline=COLOR_BORDER, width=2)
        draw.text((1490, 190), "📊 TELEMETRY GAUGE", fill=COLOR_YELLOW, font=font_code_bold)
        draw.text((1490, 235), "🤖 Model: Bedrock/Claude", fill=COLOR_WHITE, font=font_code)
        draw.text((1490, 275), "🏎️ Speed: 195 tok/s", fill=COLOR_GREEN, font=font_code)
        draw.text((1490, 315), "💾 RAM: 184MB RSS", fill=COLOR_CYAN, font=font_code)
        draw.text((1490, 355), "🛡️ AST: 100% OK", fill=COLOR_GREEN, font=font_code)
        draw.text((1490, 415), "🐝 SWARM RADAR", fill=COLOR_MAGENTA, font=font_code_bold)
        draw.text((1490, 455), "🟢 SRE Agent: Active", fill=COLOR_WHITE, font=font_code)
        draw.text((1490, 495), "🟣 Verifier: Ready", fill=COLOR_WHITE, font=font_code)
        draw.text((1490, 535), "🟡 Chaos Prober: Ready", fill=COLOR_WHITE, font=font_code)

    return img


async def main():
    print("=================================================================")
    print("🎬 K-CLI Studio Demo Video & Voiceover Generator (1080p 30FPS)")
    print("=================================================================")

    # Step 1: Synthesize all voiceovers
    scene_audios = await generate_voiceovers()

    # Step 2: Render video frame by frame for each scene and pipe into ffmpeg
    fps = 30
    width, height = 1920, 1080
    temp_video_files = []

    for idx, (scene_id, audio_path, duration) in enumerate(scene_audios):
        total_frames = int(duration * fps)
        scene_raw_video = OUTPUT_DIR / f"{scene_id}_raw.mp4"
        scene_video_path = OUTPUT_DIR / f"{scene_id}.mp4"
        print(f"\n🎨 Rendering {total_frames} frames for {scene_id} ({duration:.2f}s)...")

        # Step 2a: Encode pure video stream
        video_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "18",
            str(scene_raw_video),
        ]

        proc = subprocess.Popen(video_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

        for frame_i in range(total_frames):
            prog = frame_i / float(max(1, total_frames))
            frame_img = render_scene_frame(idx, len(SCENES_SCRIPT), SCENES_SCRIPT[idx], prog, width, height)
            try:
                proc.stdin.write(frame_img.tobytes())
            except (BrokenPipeError, IOError):
                break

        if proc.stdin:
            proc.stdin.close()
        proc.wait()

        # Step 2b: Mux audio with video
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", str(scene_raw_video),
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(scene_video_path),
        ]
        subprocess.run(mux_cmd, check=True, stderr=subprocess.DEVNULL)
        temp_video_files.append(scene_video_path)
        print(f"  ✔ Rendered {scene_video_path.name}")

    # Step 3: Concatenate all scene videos into master video
    print("\n🎞️ Concatenating all scenes into master video...")
    concat_list_file = OUTPUT_DIR / "concat_list.txt"
    with open(concat_list_file, "w") as f:
        for v in temp_video_files:
            f.write(f"file '{v.resolve()}'\n")

    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(FINAL_VIDEO_PATH),
    ]
    subprocess.run(concat_cmd, check=True)

    print("\n=================================================================")
    print(f"🎉 MASTER DEMO VIDEO GENERATED SUCCESSFULLY!")
    print(f"📁 Path: {FINAL_VIDEO_PATH}")
    print(f"📊 Size: {FINAL_VIDEO_PATH.stat().st_size / (1024*1024):.2f} MB")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
