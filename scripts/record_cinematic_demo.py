#!/usr/bin/env python3
"""
record_cinematic_demo.py - Flagship High-Definition Cinematic Terminal Recorder for K-CLI.
Renders a stunning, pixel-perfect developer experience that turns casual viewers into GitHub starrers.
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

# 24-bit TrueColor & 256-color ANSI Palette (Dracula / Tokyo Night Cyberpunk)
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"
UNDERLINE = "\x1b[4m"

# Text Colors
CYAN = "\x1b[38;2;0;240;255m"         # #00f0ff
NEON_GREEN = "\x1b[38;2;80;250;123m"   # #50fa7b
PINK = "\x1b[38;2;255;121;198m"       # #ff79c6
PURPLE = "\x1b[38;2;189;147;249m"     # #bd93f9
YELLOW = "\x1b[38;2;241;250;140m"     # #f1fa8c
ORANGE = "\x1b[38;2;255;184;108m"     # #ffb86c
RED = "\x1b[38;2;255;85;85m"          # #ff5555
WHITE = "\x1b[38;2;248;248;242m"      # #f8f8f2
GRAY = "\x1b[38;2;98;114;164m"        # #6272a4
DARK_GRAY = "\x1b[38;2;68;71;90m"     # #44475a
MUTED = "\x1b[38;2;120;125;145m"

# Background Accents
BG_DARK = "\x1b[48;2;24;25;38m"
BG_SELECTION = "\x1b[48;2;40;42;54m"
BG_DIFF_ADD = "\x1b[48;2;20;60;35m"
BG_DIFF_DEL = "\x1b[48;2;70;20;25m"


class CinematicRecorder:
    def __init__(self, cols: int = 100, rows: int = 30):
        self.cols = cols
        self.rows = rows
        self.events = []
        self.t = 0.0

    def sleep(self, duration: float):
        self.t += duration

    def emit(self, text: str, delay: float = 0.0):
        clean_text = text.replace("\n", "\r\n")
        self.events.append([round(self.t, 3), "o", clean_text])
        if delay > 0:
            self.sleep(delay)

    def type_cmd(self, prompt: str, command: str, char_speed: float = 0.028, post_pause: float = 0.4):
        self.emit(prompt)
        for char in command:
            # Subtle natural keystroke jitter
            jitter = (len(char) % 3) * 0.005
            self.sleep(char_speed + jitter)
            self.emit(char)
        self.sleep(post_pause)
        self.emit("\r\n")

    def animate_spinner(self, message: str, frames_count: int = 8, step_delay: float = 0.07):
        spin_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for i in range(frames_count):
            char = spin_chars[i % len(spin_chars)]
            self.emit(f"\r\x1b[K{CYAN}{char}{RESET} {message}")
            self.sleep(step_delay)
        self.emit(f"\r\x1b[K{NEON_GREEN}✔{RESET} {message}\r\n")
        self.sleep(0.1)

    def save(self, filepath: Path):
        header = {
            "version": 2,
            "width": self.cols,
            "height": self.rows,
            "timestamp": int(time.time()),
            "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
            "title": "K-CLI Project Bankai — Flagship Agentic AI Workstation"
        }
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            for ev in self.events:
                f.write(json.dumps(ev) + "\n")


def build_cinematic_recording():
    rec = CinematicRecorder(cols=102, rows=32)
    prompt = f"{CYAN}❯{PINK}❯{RESET} {PURPLE}k-cli{RESET}:{CYAN}~/rate-limiter{RESET} {GRAY}on{RESET} {PINK} main{RESET} {NEON_GREEN}●{RESET} "

    # 1. Clear terminal
    rec.emit("\x1b[2J\x1b[H", delay=0.2)

    # 2. Header Banner
    logo = f"""{CYAN}██╗  ██╗      ██████╗██╗     ██╗{RESET}
{CYAN}██║ ██╔╝     ██╔════╝██║     ██║{RESET}  {BOLD}{WHITE}K-CLI · Project Bankai v1.0.0{RESET}
{CYAN}█████╔╝      ██║     ██║     ██║{RESET}  {MUTED}Agentic AI Developer Workstation — 5-Model Swarm Engine{RESET}
{CYAN}██╔═██╗      ██║     ██║     ██║{RESET}  {GRAY}Ollama (Local) + Gemini + Claude + DeepSeek + Groq{RESET}
{CYAN}██║  ██╗     ╚██████╗███████╗██║{RESET}
{CYAN}╚═╝  ╚═╝      ╚═════╝╚══════╝╚═╝{RESET}
{DARK_GRAY}──────────────────────────────────────────────────────────────────────────────────────────────────────{RESET}
"""
    rec.emit(logo, delay=0.6)

    # 3. Action 1: 5-Model Parallel Swarm Audit
    rec.type_cmd(prompt, "k \"build a high-performance token bucket rate limiter with redis + local fallback\"", char_speed=0.024, post_pause=0.35)

    rec.animate_spinner(f"{BOLD}{WHITE}Analyzing AST codebase context & dependencies...{RESET}", frames_count=6, step_delay=0.06)
    rec.animate_spinner(f"{BOLD}{YELLOW}Dispatching 5-Model Parallel Consensus Swarm (Local + Frontier)...{RESET}", frames_count=8, step_delay=0.06)

    rec.emit(f"\n{BOLD}{CYAN}⚡ 5-Model Consensus Swarm — Parallel Benchmark Telemetry{RESET}\n", delay=0.15)

    # Table
    t_top = f"{DARK_GRAY}┌─────────────────────────┬──────────────┬──────────────┬──────────────┬──────────┬───────────┐{RESET}\n"
    t_hdr = f"{DARK_GRAY}│{RESET} {BOLD}Model ID                {RESET}{DARK_GRAY}│{RESET} {BOLD}Provider     {RESET}{DARK_GRAY}│{RESET} {BOLD}AST Syntax   {RESET}{DARK_GRAY}│{RESET} {BOLD}Verification {RESET}{DARK_GRAY}│{RESET} {BOLD}Latency  {RESET}{DARK_GRAY}│{RESET} {BOLD}Score     {RESET}{DARK_GRAY}│{RESET}\n"
    t_mid = f"{DARK_GRAY}├─────────────────────────┼──────────────┼──────────────┼──────────────┼──────────┼───────────┤{RESET}\n"
    rec.emit(t_top + t_hdr + t_mid, delay=0.1)

    models_data = [
        ("gemini-2.5-flash        ", "Google Cloud ", f"{NEON_GREEN}✔ PASS (AST) {RESET}", f"{NEON_GREEN}✔ 14/14 PASS {RESET}", "0.64s   ", f"{YELLOW}9.2/10   {RESET}"),
        ("claude-3-7-sonnet       ", "Anthropic    ", f"{NEON_GREEN}✔ PASS (AST) {RESET}", f"{NEON_GREEN}✔ 14/14 PASS {RESET}", "1.05s   ", f"{YELLOW}9.5/10   {RESET}"),
        ("deepseek-reasoner       ", "DeepSeek     ", f"{NEON_GREEN}✔ PASS (AST) {RESET}", f"{NEON_GREEN}✔ 14/14 PASS {RESET}", "1.42s   ", f"{BOLD}{NEON_GREEN}9.8/10 👑 {RESET}"),
        ("gpt-4o                  ", "OpenAI       ", f"{NEON_GREEN}✔ PASS (AST) {RESET}", f"{NEON_GREEN}✔ 14/14 PASS {RESET}", "0.89s   ", f"{YELLOW}9.1/10   {RESET}"),
        ("qwen2.5-coder:32b       ", "Ollama (Free)", f"{NEON_GREEN}✔ PASS (AST) {RESET}", f"{NEON_GREEN}✔ 14/14 PASS {RESET}", "1.75s   ", f"{YELLOW}9.0/10   {RESET}"),
    ]

    for m_id, prov, ast_st, ver_st, lat, scr in models_data:
        row = f"{DARK_GRAY}│{RESET} {BOLD}{WHITE}{m_id}{RESET}{DARK_GRAY}│{RESET} {prov}{DARK_GRAY}│{RESET} {ast_st}{DARK_GRAY}│{RESET} {ver_st}{DARK_GRAY}│{RESET} {lat}{DARK_GRAY}│{RESET} {scr}{DARK_GRAY}│{RESET}\n"
        rec.emit(row, delay=0.12)

    t_bot = f"{DARK_GRAY}└─────────────────────────┴──────────────┴──────────────┴──────────────┴──────────┴───────────┘{RESET}\n"
    rec.emit(t_bot, delay=0.2)

    # Peer Review Callout
    rec.emit(f"{NEON_GREEN}🛡️ Cross-Model Peer Review Consensus:{RESET} {WHITE}Zero lock contention · ABA safe · In-memory LRU fallback valid{RESET}\n", delay=0.15)
    rec.emit(f"{YELLOW}👑 Selected Winning Solution:{RESET} {BOLD}{CYAN}deepseek-reasoner{RESET} (Consensus Agreement: 100.0%)\n\n", delay=0.4)

    # 4. Surgical Diff Preview
    rec.emit(f"{BOLD}{WHITE}📜 Surgical Diff Card — {CYAN}src/rate_limiter.py{RESET} {MUTED}(+28, -6 lines){RESET}\n", delay=0.15)
    diff_box = f"""{DARK_GRAY}┌────────────────────────────────────────────────────────────────────────────────────────────────────┐{RESET}
{DARK_GRAY}│{RESET} {MUTED}@@ -14,6 +14,28 @@ class TokenBucketLimiter:{RESET}
{DARK_GRAY}│{RESET} {RED}-    def allow_request(self, key: str) -> bool:{RESET}
{DARK_GRAY}│{RESET} {RED}-        # Slow sequential in-memory lock{RESET}
{DARK_GRAY}│{RESET} {RED}-        with self.lock:{RESET}
{DARK_GRAY}│{RESET} {RED}-            return self._consume_token(key){RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+    async def allow_request(self, key: str) -> bool:{RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+        \"\"\"Atomic Token Bucket with distributed Redis Lua & zero-lock memory fallback.\"\"\"{RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+        try:{RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+            res = await self.redis.evalsha(self._lua_sha, 1, key, self.capacity, self.rate){RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+            return bool(res){RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+        except (ConnectionError, TimeoutError):{RESET}
{DARK_GRAY}│{RESET} {NEON_GREEN}+            return self._local_fast_lru_fallback(key){RESET}
{DARK_GRAY}└────────────────────────────────────────────────────────────────────────────────────────────────────┘{RESET}
"""
    rec.emit(diff_box, delay=0.5)
    rec.emit(f"{NEON_GREEN}✔ AST Verification: Clean Syntax{RESET} │ {NEON_GREEN}✔ Pytest: 14/14 tests pass (0.04s){RESET} │ {CYAN}💰 Cost Saved: $0.038{RESET}\n\n", delay=0.8)

    # 5. Action 2: Ghost Terminal Autopilot
    rec.type_cmd(prompt, "k-cli ghost 'pytest tests/'", char_speed=0.024, post_pause=0.35)
    rec.emit(f"{MUTED}pytest running against test suite...{RESET}\n", delay=0.15)
    rec.emit(f"{RED}FAILED tests/test_auth.py::test_jwt_decode - TypeError: decode() missing 'algorithms' kwarg{RESET}\n\n", delay=0.25)

    ghost_panel = f"""{PINK}👻 GHOST AUTOPILOT INTERCEPTED EXCEPTION{RESET}
{DARK_GRAY}──────────────────────────────────────────────────────────────────────────────────────────────────────{RESET}
  {BOLD}{WHITE}Exception:{RESET}      {RED}TypeError at src/auth/jwt.py:42{RESET}
  {BOLD}{WHITE}Root Cause:{RESET}     PyJWT v2.0+ requires explicit algorithms list in jwt.decode()
  {BOLD}{WHITE}Surgical Patch:{RESET} {NEON_GREEN}+ algorithms=['HS256']{RESET} (1-line addition)
  {BOLD}{WHITE}Verification:{RESET}   {NEON_GREEN}✔ AST Validated · Pytest 28/28 Passing{RESET}

  {BOLD}{YELLOW}[ Y  Apply Patch ]{RESET}   {MUTED}[ D  View Diff ]   [ N  Skip ]   [ S  Open in TUI ]{RESET}
"""
    rec.emit(ghost_panel, delay=0.6)
    rec.type_cmd(f"{YELLOW}Choice: {RESET}", "Y", char_speed=0.08, post_pause=0.25)
    rec.emit(f"{NEON_GREEN}✔ Patch cleanly applied to src/auth/jwt.py. Test runner re-executed: 100% green.{RESET}\n\n", delay=0.7)

    # 6. Action 3: Launch Cyber Workstation TUI
    rec.type_cmd(prompt, "k", char_speed=0.03, post_pause=0.4)

    # TUI Screen Frame
    tui_view = f"""\x1b[2J\x1b[H{BOLD}{CYAN}⚡ K-CLI CYBER WORKSTATION{RESET} │ {YELLOW}🤖 gemini-2.5-flash{RESET} │ {PINK} main (+1 ~0){RESET} │ {NEON_GREEN}💾 184MB RSS{RESET} │ {YELLOW}🏎️ 248 tok/s{RESET} │ {NEON_GREEN}💰 $0.003{RESET} │ {NEON_GREEN}🛡️ AST OK ●{RESET}
{CYAN}══════════════════════════════════════════════════════════════════════════════════════════════════════{RESET}
{DARK_GRAY}┌─ 🚀 1-CLICK LAUNCHER ────┬─ 💬 AGENTIC STREAM CANVAS ─────────────────────────┬─ 📊 TELEMETRY & DIFFS ──┐{RESET}
{DARK_GRAY}│{RESET} {YELLOW}[⚡ 5-Model Swarm Audit]{RESET}  {DARK_GRAY}│{RESET} # ⚡ K-CLI · Project Bankai                          {DARK_GRAY}│{RESET} {BOLD}Active Model:{RESET}            {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} {CYAN}[🤖 Dynamic Model Hub ]{RESET}  {DARK_GRAY}│{RESET} > The AI agent that lives in your terminal,        {DARK_GRAY}│{RESET}   gemini-2.5-flash        {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} {CYAN}[📖 Codex Setup Hub   ]{RESET}  {DARK_GRAY}│{RESET}   watches crashes, and ships verified code.        {DARK_GRAY}│{RESET} {BOLD}Session Tokens:{RESET}          {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🔑 API Key Vault     ]  {DARK_GRAY}│{RESET}                                                     {DARK_GRAY}│{RESET}   2,847 tokens            {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [👻 Ghost Autopilot   ]  {DARK_GRAY}│{RESET} ╔══ 🧠 Thinking (1.2s)...                           {DARK_GRAY}│{RESET} {BOLD}Uptime:{RESET}                  {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🐝 Adversarial Swarm ]  {DARK_GRAY}│{RESET} ║ • Dispatched 5 models across cloud & Ollama       {DARK_GRAY}│{RESET}   00:05:42                {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [⚔️ Merge Conflicts   ]  {DARK_GRAY}│{RESET} ║ • Running cross-model adversarial peer review     {DARK_GRAY}│{RESET}                           {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🐙 GitHub Center     ]  {DARK_GRAY}│{RESET} ║ • 100% AST compiler verification pass             {DARK_GRAY}│{RESET} {BOLD}Live Diffs:{RESET}               {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🛡️ Security Healer   ]  {DARK_GRAY}│{RESET} ╚═══════════════════════════════════════════════════ {DARK_GRAY}│{RESET}   • auth/jwt.py (+1 -1)   {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🎯 AI Git Bisect     ]  {DARK_GRAY}│{RESET}                                                     {DARK_GRAY}│{RESET}   • rate_limiter.py       {DARK_GRAY}│{RESET}
{DARK_GRAY}│{RESET} [🌿 Repo Gardener     ]  {DARK_GRAY}│{RESET} ✅ Consensus code synthesized & AST validated.     {DARK_GRAY}│{RESET}     (+28 -6)              {DARK_GRAY}│{RESET}
{DARK_GRAY}└──────────────────────────┴────────────────────────────────────────────────────┴─────────────────────────┘{RESET}
{DARK_GRAY} [ 📖 Codex ]  [ ⚡ 5-Model Audit ]  [ 🤖 Models ]  [ 🔑 Keys ]  [ ⚔️ Conflicts ]  [ 🐙 GitHub ]  [ 🛡️ Security ]{RESET}
{CYAN}❯ Type a task, ask a question, or hit Ctrl+O for Codex setup...{RESET}
"""
    rec.emit(tui_view, delay=4.0)

    rec.save(CAST_FILE)
    print(f"✔ High-Definition Cinematic Asciicast saved to: {CAST_FILE}")


if __name__ == "__main__":
    build_cinematic_recording()
