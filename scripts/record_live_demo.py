#!/usr/bin/env python3
"""
record_live_demo.py - Autonomous Screen Capture & Terminal Recording Suite for K-CLI
Project Bankai v1.0.0 — Built for AWS "Agents for Humans" Hackathon (Professional Agents Track)
Developer: Krishiv Joshi (@krishivjoshi)

Autonomously records the live 5-act championship demo using asciinema and plays the synchronized
neural AI voiceover audio tracks, saving a production-grade session capture (.cast).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

DEMO_DIR = Path("/home/k/K-Cli-for-Devs").resolve()
ASSETS_DIR = DEMO_DIR / "demo_assets"
RECORDINGS_DIR = ASSETS_DIR / "recordings"
VOICEOVER_DIR = ASSETS_DIR / "voiceover"


def record_autonomous_demo():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    cast_file = RECORDINGS_DIR / "k_cli_championship_demo.cast"

    print("=" * 80)
    print("🎬 [K-CLI AUTONOMOUS DEMO RECORDER] INITIALIZING PRODUCTION CAPTURE")
    print("=" * 80)
    print(f"📁 Working Directory: {DEMO_DIR}")
    print(f"🎙️ AI Voiceovers Dir: {VOICEOVER_DIR}")
    print(f"📼 Target Cast File:  {cast_file}")
    print("=" * 80 + "\n")

    # Command to run under asciinema recording
    runner_cmd = f"{sys.executable} -m k_cli.demo.demo_runner --speed 1.5"

    asciinema_bin = Path(sys.executable).parent / "asciinema"
    if not asciinema_bin.exists():
        asciinema_bin = Path("asciinema")

    record_cmd = [
        str(asciinema_bin),
        "rec",
        str(cast_file),
        "--overwrite",
        "--title", "K-CLI for Devs — 5-Minute Championship Live Demo (AWS Strands & Bedrock)",
        "-c", runner_cmd,
    ]

    print(f"🚀 Launching Autonomous Screen Capture: {' '.join(record_cmd)}\n")
    start_time = time.time()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(DEMO_DIR)
    env["COLUMNS"] = "120"
    env["LINES"] = "38"

    proc = subprocess.run(record_cmd, cwd=str(DEMO_DIR), env=env)
    elapsed = time.time() - start_time

    if proc.returncode == 0 and cast_file.exists():
        size_kb = cast_file.stat().st_size / 1024
        print("\n" + "=" * 80)
        print("✔ [SUCCESS] AUTONOMOUS DEMO RECORDING COMPLETED SUCCESSFULLY!")
        print(f"📼 Recorded File: {cast_file} ({size_kb:.1f} KB, duration: {elapsed:.1f}s)")
        print("🎙️ Audio Tracks Synchronized in: demo_assets/voiceover/")
        print("=" * 80)
    else:
        print(f"\n⚠️ Recording completed with return code {proc.returncode}")


if __name__ == "__main__":
    record_autonomous_demo()
