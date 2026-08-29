#!/usr/bin/env python3
"""
record_demo.py - Generates an ultra-sleek, pixel-perfect asciicast v2 demo recording for K-CLI.
Produces assets/demo.cast which is converted by `agg` to assets/demo.gif and by `ffmpeg` to assets/demo.mp4.
"""

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
ASSETS_DIR = REPO_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
CAST_FILE = ASSETS_DIR / "demo.cast"

# Cyberpunk & Neon ANSI Escape Codes
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_DIM = "\x1b[2m"
C_CYAN = "\x1b[36m"
C_BRIGHT_CYAN = "\x1b[96m"
C_GREEN = "\x1b[32m"
C_BRIGHT_GREEN = "\x1b[92m"
C_YELLOW = "\x1b[33m"
C_BRIGHT_YELLOW = "\x1b[93m"
C_RED = "\x1b[31m"
C_BRIGHT_RED = "\x1b[91m"
C_MAGENTA = "\x1b[35m"
C_BRIGHT_MAGENTA = "\x1b[95m"
C_BLUE = "\x1b[34m"
C_BRIGHT_BLUE = "\x1b[94m"
C_GRAY = "\x1b[90m"
BG_DARK = "\x1b[40m"


class CastRecorder:
    def __init__(self, width: int = 100, height: int = 30):
        self.width = width
        self.height = height
        self.events = []
        self.current_time = 0.0

    def sleep(self, seconds: float):
        self.current_time += seconds

    def emit(self, text: str, delay_after: float = 0.0):
        # text should have \r\n for terminal newlines
        clean_text = text.replace("\n", "\r\n")
        self.events.append([round(self.current_time, 3), "o", clean_text])
        if delay_after > 0:
            self.sleep(delay_after)

    def type_command(self, prompt: str, command: str, char_delay: float = 0.035, post_delay: float = 0.5):
        self.emit(prompt)
        for char in command:
            self.sleep(char_delay)
            self.emit(char)
        self.sleep(post_delay)
        self.emit("\r\n")

    def save(self, filepath: Path):
        header = {
            "version": 2,
            "width": self.width,
            "height": self.height,
            "timestamp": int(time.time()),
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
            "title": "K-CLI Project Bankai — Flagship Agentic AI Workstation"
        }
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            for ev in self.events:
                f.write(json.dumps(ev) + "\n")


def build_demo_recording():
    rec = CastRecorder(width=104, height=32)
    prompt = f"{C_BRIGHT_CYAN}dev@workstation{C_RESET}:{C_BRIGHT_BLUE}~/projects/api{C_RESET}$ "

    # 0. Initial clear & pause
    rec.emit("\x1b[2J\x1b[H", delay_after=0.3)

    # 1. Title Banner Splash
    banner = f"""
{C_BRIGHT_CYAN}██╗  ██╗      ██████╗██╗     ██╗
██║ ██╔╝     ██╔════╝██║     ██║
█████╔╝      ██║     ██║     ██║
██╔═██╗      ██║     ██║     ██║
██║  ██╗     ╚██████╗███████╗██║
╚═╝  ╚═╝      ╚═════╝╚══════╝╚═╝{C_RESET}  {C_BOLD}{C_BRIGHT_GREEN}Project Bankai v1.0.0 — Agentic AI Workstation{C_RESET}
{C_GRAY}────────────────────────────────────────────────────────────────────────────────────────────{C_RESET}
"""
    rec.emit(banner, delay_after=0.8)

    # 2. Command 1: Dynamic 5-Model Swarm Audit
    rec.type_command(prompt, "k-cli audit 'implement lock-free MPMC queue' --models 'gemini,claude,deepseek,gpt-4o,qwen'", char_delay=0.03, post_delay=0.4)

    rec.emit(f"\n{C_BOLD}{C_BRIGHT_YELLOW}⚡ K-CLI Multi-Model Swarm Audit & Consensus (5 Models in Parallel){C_RESET}\n", delay_after=0.2)
    rec.emit(f"{C_GRAY}Task:{C_RESET} implement lock-free MPMC queue\n", delay_after=0.1)
    rec.emit(f"{C_CYAN}Dispatching 5 candidate generations concurrently across cloud & local endpoints...{C_RESET}\n\n", delay_after=0.5)

    # Model Generation Telemetry Table
    table_header = f"{C_BOLD}{C_GRAY}┌──────────────────────┬─────────────┬────────────┬──────────────┬──────────┬────────┬─────────┐{C_RESET}\n"
    table_header += f"{C_BOLD}{C_GRAY}│{C_RESET} {C_BOLD}Model ID             {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Provider    {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}AST Syntax {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Verification {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Latency  {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Tokens {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Score   {C_RESET}{C_GRAY}│{C_RESET}\n"
    table_header += f"{C_BOLD}{C_GRAY}├──────────────────────┼─────────────┼────────────┼──────────────┼──────────┼────────┼─────────┤{C_RESET}\n"
    rec.emit(table_header, delay_after=0.2)

    rows = [
        ("gemini-2.0-flash     ", "Google Cloud ", f"{C_BRIGHT_GREEN}✔ PASS    {C_RESET}", f"{C_BRIGHT_GREEN}✔ 18/18 PASS {C_RESET}", "0.78s   ", "  942 ", f"{C_BOLD}9.1/10 {C_RESET}"),
        ("claude-3-7-sonnet    ", "Anthropic    ", f"{C_BRIGHT_GREEN}✔ PASS    {C_RESET}", f"{C_BRIGHT_GREEN}✔ 18/18 PASS {C_RESET}", "1.12s   ", " 1,180", f"{C_BOLD}9.4/10 {C_RESET}"),
        ("deepseek-reasoner    ", "DeepSeek     ", f"{C_BRIGHT_GREEN}✔ PASS    {C_RESET}", f"{C_BRIGHT_GREEN}✔ 18/18 PASS {C_RESET}", "1.85s   ", " 2,410", f"{C_BOLD}{C_BRIGHT_GREEN}9.8/10*{C_RESET}"),
        ("gpt-4o               ", "OpenAI       ", f"{C_BRIGHT_GREEN}✔ PASS    {C_RESET}", f"{C_BRIGHT_GREEN}✔ 18/18 PASS {C_RESET}", "0.95s   ", " 1,024", f"{C_BOLD}9.0/10 {C_RESET}"),
        ("qwen2.5-coder:7b     ", "Ollama (Free)", f"{C_BRIGHT_GREEN}✔ PASS    {C_RESET}", f"{C_BRIGHT_GREEN}✔ 18/18 PASS {C_RESET}", "2.40s   ", "   890", f"{C_BOLD}8.9/10 {C_RESET}"),
    ]

    for model_id, prov, ast_st, ver_st, lat, toks, scr in rows:
        row_str = f"{C_GRAY}│{C_RESET} {C_BRIGHT_CYAN}{model_id}{C_RESET}{C_GRAY}│{C_RESET} {prov}{C_GRAY}│{C_RESET} {ast_st}{C_GRAY}│{C_RESET} {ver_st}{C_GRAY}│{C_RESET} {lat}{C_GRAY}│{C_RESET} {toks}{C_GRAY}│{C_RESET} {scr}{C_GRAY}│{C_RESET}\n"
        rec.emit(row_str, delay_after=0.2)

    table_footer = f"{C_BOLD}{C_GRAY}└──────────────────────┴─────────────┴────────────┴──────────────┴──────────┴────────┴─────────┘{C_RESET}\n"
    rec.emit(table_footer, delay_after=0.3)

    # Consensus Callout
    rec.emit(f"\n{C_BOLD}{C_BRIGHT_GREEN}🛡️ Consensus Achieved (100% Agreement on Memory Model & ABA Prevention){C_RESET}\n", delay_after=0.1)
    rec.emit(f"👑 {C_BOLD}Winning Implementation:{C_RESET} {C_BRIGHT_YELLOW}deepseek-reasoner{C_RESET} (Score: 9.8/10 | Zero race conditions)\n", delay_after=0.2)
    rec.emit(f"{C_GRAY}Code synthesized & verified via AST compiler gate in 2.14s.{C_RESET}\n\n", delay_after=1.2)

    # 3. Command 2: Ghost Terminal Autopilot
    rec.type_command(prompt, "k-cli ghost 'pytest tests/test_auth.py'", char_delay=0.03, post_delay=0.4)
    rec.emit(f"{C_GRAY}running tests/test_auth.py ...{C_RESET}\n", delay_after=0.2)
    rec.emit(f"{C_BRIGHT_RED}FAILED tests/test_auth.py::test_jwt_decode - TypeError: decode() missing 'algorithms' kwarg{C_RESET}\n\n", delay_after=0.3)

    ghost_box = f"""{C_BOLD}{C_BRIGHT_MAGENTA}👻 GHOST AUTOPILOT INTERCEPTED CRASH{C_RESET}
{C_GRAY}────────────────────────────────────────────────────────────────────────────────────────────{C_RESET}
  {C_BOLD}Culprit File:{C_RESET}    {C_CYAN}src/auth/jwt_handler.py:42{C_RESET}
  {C_BOLD}Root Cause:{C_RESET}      PyJWT 2.0+ requires explicit algorithms list in jwt.decode()
  {C_BOLD}Confidence:{C_RESET}      {C_BRIGHT_GREEN}99.4%{C_RESET}
  {C_BOLD}Surgical Patch:{C_RESET}  {C_BRIGHT_GREEN}+ algorithms=['HS256']{C_RESET} (1 line addition)
  {C_BOLD}Verification:{C_RESET}    {C_BRIGHT_GREEN}✔ AST Validated · Pytest 14/14 Passing{C_RESET}

  {C_BOLD}[ Y  Apply Patch ]{C_RESET}  [ D  View Diff ]  [ N  Skip ]  [ S  Open TUI ]
"""
    rec.emit(ghost_box, delay_after=0.8)
    rec.type_command(f"{C_BRIGHT_YELLOW}Choice: {C_RESET}", "Y", char_delay=0.1, post_delay=0.3)
    rec.emit(f"{C_BRIGHT_GREEN}✔ Patch applied cleanly to src/auth/jwt_handler.py. Tests re-run and 100% green.{C_RESET}\n\n", delay_after=1.0)

    # 4. Command 3: Dynamic Model Discovery (Asking Ollama directly)
    rec.type_command(prompt, "k-cli models list", char_delay=0.03, post_delay=0.4)
    rec.emit(f"\n{C_BOLD}{C_BRIGHT_CYAN}🤖 Dynamically Discovered Models (Live Query of Ollama daemon & Cloud APIs){C_RESET}\n\n", delay_after=0.2)

    mod_header = f"{C_BOLD}{C_GRAY}┌─────────────────────────┬──────────────┬────────────┬───────────┬──────────────┬─────────────┐{C_RESET}\n"
    mod_header += f"{C_BOLD}{C_GRAY}│{C_RESET} {C_BOLD}Model ID                {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Provider     {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Parameters {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Quant Level{C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Size on Disk {C_RESET}{C_GRAY}│{C_RESET} {C_BOLD}Status      {C_RESET}{C_GRAY}│{C_RESET}\n"
    mod_header += f"{C_BOLD}{C_GRAY}├─────────────────────────┼──────────────┼────────────┼───────────┼──────────────┼─────────────┤{C_RESET}\n"
    rec.emit(mod_header, delay_after=0.1)

    m_rows = [
        ("qwen2.5-coder:7b        ", "Ollama Local ", "7.6B        ", "Q4_K_M     ", "4.7 GB        ", f"{C_BRIGHT_GREEN}● Ready     {C_RESET}"),
        ("llama3.2:3b             ", "Ollama Local ", "3.2B        ", "Q4_K_M     ", "2.0 GB        ", f"{C_BRIGHT_GREEN}● Ready     {C_RESET}"),
        ("deepseek-coder-v2:16b   ", "Ollama Local ", "16.0B       ", "Q4_K_M     ", "9.1 GB        ", f"{C_BRIGHT_GREEN}● Ready     {C_RESET}"),
        ("gemini-2.0-flash        ", "Google Cloud ", "Frontier    ", "FP16 Cloud ", "Remote API    ", f"{C_BRIGHT_GREEN}● Connected {C_RESET}"),
        ("claude-3-7-sonnet       ", "Anthropic    ", "Frontier    ", "FP16 Cloud ", "Remote API    ", f"{C_BRIGHT_GREEN}● Connected {C_RESET}"),
        ("llama-3.3-70b-versatile ", "Groq LPU     ", "70.0B       ", "FP8 Fast   ", "Remote API    ", f"{C_BRIGHT_GREEN}● 320 tok/s {C_RESET}"),
    ]
    for m_id, p_id, prm, qnt, sz, st in m_rows:
        rec.emit(f"{C_GRAY}│{C_RESET} {C_BRIGHT_YELLOW}{m_id}{C_RESET}{C_GRAY}│{C_RESET} {p_id}{C_GRAY}│{C_RESET} {prm}{C_GRAY}│{C_RESET} {qnt}{C_GRAY}│{C_RESET} {sz}{C_GRAY}│{C_RESET} {st}{C_GRAY}│{C_RESET}\n", delay_after=0.1)

    rec.emit(f"{C_BOLD}{C_GRAY}└─────────────────────────┴──────────────┴────────────┴───────────┴──────────────┴─────────────┘{C_RESET}\n", delay_after=0.2)
    rec.emit(f"{C_GRAY}Note: Zero rigid locking. Type ANY custom model (e.g. `ollama/qwen2.5:32b`, `openai/o3-mini`).{C_RESET}\n\n", delay_after=1.0)

    # 5. Command 4: Launching the Cyber Workstation
    rec.type_command(prompt, "k", char_delay=0.04, post_delay=0.5)

    # TUI Flash
    tui_screen = f"""\x1b[2J\x1b[H{C_BOLD}{C_BRIGHT_CYAN}⚡ K-CLI AGENT{C_RESET} │ {C_BRIGHT_YELLOW}🤖 gemini-2.0-flash{C_RESET} │ {C_CYAN} main (+1 ~0){C_RESET} │ {C_GREEN}💾 184MB RSS{C_RESET} │ {C_BRIGHT_YELLOW}🏎️ 185 tok/s{C_RESET} │ {C_GREEN}💰 $0.002{C_RESET} │ {C_BRIGHT_GREEN}🛡️ AST OK ●{C_RESET}
{C_CYAN}════════════════════════════════════════════════════════════════════════════════════════════════════{C_RESET}
{C_GRAY}┌─ 🚀 1-CLICK LAUNCHER ───┬─ 💬 K-CLI AGENTIC WORKSTATION ──────────────────┬─ 📜 TELEMETRY & DIFFS ──┐{C_RESET}
{C_GRAY}│{C_RESET} {C_BRIGHT_YELLOW}[⚡ 5-Model Swarm Audit]{C_RESET}  {C_GRAY}│{C_RESET} # ⚡ K-CLI · Project Bankai                       {C_GRAY}│{C_RESET} {C_BOLD}Active Model:{C_RESET}            {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} {C_CYAN}[🤖 Dynamic Model Hub ]{C_RESET}  {C_GRAY}│{C_RESET} > The AI agent that lives in your terminal,     {C_GRAY}│{C_RESET}   gemini-2.0-flash        {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} {C_CYAN}[📖 Codex Setup Hub   ]{C_RESET}  {C_GRAY}│{C_RESET}   watches crashes, and ships verified code.     {C_GRAY}│{C_RESET} {C_BOLD}Session Tokens:{C_RESET}          {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🔑 API Key Vault     ]  {C_GRAY}│{C_RESET}                                                  {C_GRAY}│{C_RESET}   2,847 tokens            {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [👻 Ghost Autopilot   ]  {C_GRAY}│{C_RESET} ╔══ 🧠 Thinking (1.2s)...                        {C_GRAY}│{C_RESET} {C_BOLD}Uptime:{C_RESET}                  {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🐝 Adversarial Swarm ]  {C_GRAY}│{C_RESET} ║ • Dispatched 5 models across cloud & Ollama    {C_GRAY}│{C_RESET}   00:04:18                {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [⚔️ Merge Conflicts   ]  {C_GRAY}│{C_RESET} ║ • Running cross-model adversarial peer review  {C_GRAY}│{C_RESET}                           {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🐙 GitHub Center     ]  {C_GRAY}│{C_RESET} ║ • 100% AST compiler verification pass          {C_GRAY}│{C_RESET} {C_BOLD}Live Diffs:{C_RESET}               {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🛡️ Security Healer   ]  {C_GRAY}│{C_RESET} ╚════════════════════════════════════════════════ {C_GRAY}│{C_RESET}   • auth/jwt.py (+1 -1)   {C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🎯 AI Git Bisect     ]  {C_GRAY}│{C_RESET}                                                  {C_GRAY}│{C_RESET}   • queue/mpmc.py (+84 -0){C_GRAY}│{C_RESET}
{C_GRAY}│{C_RESET} [🌿 Repo Gardener     ]  {C_GRAY}│{C_RESET} ✅ Consensus code synthesized & AST validated.  {C_GRAY}│{C_RESET}   • tests/       (+42 -0) {C_GRAY}│{C_RESET}
{C_GRAY}└─────────────────────────┴─────────────────────────────────────────────────┴─────────────────────────┘{C_RESET}
{C_GRAY} [ 📖 Codex ]  [ ⚡ 5-Model Audit ]  [ 🤖 Models ]  [ 🔑 Keys ]  [ ⚔️ Conflicts ]  [ 🐙 GitHub ]  [ 🛡️ Security ]{C_RESET}
{C_BRIGHT_CYAN}❯ Type a task, ask a question, or press Ctrl+O for Codex setup...{C_RESET}
"""
    rec.emit(tui_screen, delay_after=3.5)

    rec.save(CAST_FILE)
    print(f"✔ Recorded asciicast saved to: {CAST_FILE}")


if __name__ == "__main__":
    build_demo_recording()
