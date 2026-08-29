#!/usr/bin/env python3
"""
record_viral_demo.py - Next-Generation Viral Terminal Recording Engine for K-CLI (Project Bankai).
Built locally using Rust agg + ffmpeg to render pixel-perfect, artifact-free, high-contrast terminal recordings.
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

# TrueColor ANSI Palette (Dracula / Tokyo Night Cyberpunk)
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"
UNDERLINE = "\x1b[4m"

# Window Chrome
DOT_RED = "\x1b[38;2;255;95;86m●\x1b[0m"
DOT_YELLOW = "\x1b[38;2;255;189;46m●\x1b[0m"
DOT_GREEN = "\x1b[38;2;39;201;63m●\x1b[0m"

# Colors
CYAN = "\x1b[38;2;0;240;255m"         # #00f0ff (Neon Cyan)
GREEN = "\x1b[38;2;80;250;123m"       # #50fa7b (Dracula Green)
PINK = "\x1b[38;2;255;121;198m"       # #ff79c6 (Dracula Pink)
PURPLE = "\x1b[38;2;189;147;249m"     # #bd93f9 (Dracula Purple)
YELLOW = "\x1b[38;2;241;250;140m"     # #f1fa8c (Dracula Yellow)
ORANGE = "\x1b[38;2;255;184;108m"     # #ffb86c (Dracula Orange)
RED = "\x1b[38;2;255;85;85m"          # #ff5555 (Dracula Red)
WHITE = "\x1b[38;2;248;248;242m"      # #f8f8f2 (Foreground)
GRAY = "\x1b[38;2;98;114;164m"        # #6272a4 (Comment)
DARK_GRAY = "\x1b[38;2;68;71;90m"     # #44475a (Current Line)
MUTED = "\x1b[38;2;139;148;158m"


class ViralRecorder:
    def __init__(self, cols: int = 104, rows: int = 32):
        self.cols = cols
        self.rows = rows
        self.events = []
        self.t = 0.0

    def sleep(self, seconds: float):
        self.t += seconds

    def emit(self, text: str, delay: float = 0.0):
        clean_text = text.replace("\n", "\r\n")
        self.events.append([round(self.t, 3), "o", clean_text])
        if delay > 0:
            self.sleep(delay)

    def type_cmd(self, prompt: str, command: str, char_speed: float = 0.026, post_pause: float = 0.4):
        self.emit(prompt)
        for char in command:
            jitter = (ord(char) % 4) * 0.004
            self.sleep(char_speed + jitter)
            self.emit(char)
        self.sleep(post_pause)
        self.emit("\r\n")

    def animate_spinner(self, message: str, frames: int = 8, delay_step: float = 0.06):
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for i in range(frames):
            c = spinners[i % len(spinners)]
            self.emit(f"\r\x1b[K{CYAN}{c}{RESET} {message}")
            self.sleep(delay_step)
        self.emit(f"\r\x1b[K{GREEN}✔{RESET} {message}\r\n")
        self.sleep(0.08)

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


def generate_recording():
    rec = ViralRecorder(cols=104, rows=32)
    prompt = f"{CYAN}❯{PINK}❯{RESET} {PURPLE}k-cli{RESET}:{CYAN}~/rate-limiter{RESET} {GRAY}on{RESET} {PINK} main{RESET} {GREEN}●{RESET} "

    # 0. Initial Clean Screen
    rec.emit("\x1b[2J\x1b[H", delay=0.15)

    # 1. Window Frame & Banner
    window_bar = f"{DOT_RED} {DOT_YELLOW} {DOT_GREEN}  {GRAY}k-cli — zsh — 104x32{RESET}\n"
    rec.emit(window_bar, delay=0.1)

    logo = f"""{CYAN}██╗  ██╗      ██████╗██╗     ██╗{RESET}
{CYAN}██║ ██╔╝     ██╔════╝██║     ██║{RESET}  {BOLD}{WHITE}K-CLI · Project Bankai v1.0.0{RESET}
{CYAN}█████╔╝      ██║     ██║     ██║{RESET}  {MUTED}Agentic AI Developer Workstation — 5-Model Swarm Engine{RESET}
{CYAN}██╔═██╗      ██║     ██║     ██║{RESET}  {GRAY}100% Free with Local Ollama · Cloud Frontier APIs · Zero Lock-In{RESET}
{CYAN}██║  ██╗     ╚██████╗███████╗██║{RESET}
{CYAN}╚═╝  ╚═╝      ╚═════╝╚══════╝╚═╝{RESET}
{DARK_GRAY}────────────────────────────────────────────────────────────────────────────────────────────────────────{RESET}
"""
    rec.emit(logo, delay=0.5)

    # 2. Command: 5-Model Parallel Swarm Generation
    rec.type_cmd(prompt, "k \"build a thread-safe token bucket rate limiter with Redis + local LRU fallback\"", char_speed=0.022, post_pause=0.3)

    rec.animate_spinner(f"{BOLD}{WHITE}Parsing AST codebase map & extracting type definitions...{RESET}", frames=6, delay_step=0.05)
    rec.animate_spinner(f"{BOLD}{YELLOW}Dispatching 5-Model Parallel Consensus Swarm (Local + Cloud)...{RESET}", frames=7, delay_step=0.05)

    rec.emit(f"\n{BOLD}{CYAN}⚡ 5-Model Parallel Benchmark & Verification Telemetry{RESET}\n", delay=0.1)

    # Table
    t_top = f"{DARK_GRAY}┌─────────────────────────┬──────────────┬──────────────┬──────────────┬──────────┬───────────┐{RESET}\n"
    t_hdr = f"{DARK_GRAY}│{RESET} {BOLD}Model ID                {RESET}{DARK_GRAY}│{RESET} {BOLD}Provider     {RESET}{DARK_GRAY}│{RESET} {BOLD}AST Syntax   {RESET}{DARK_GRAY}│{RESET} {BOLD}Verification {RESET}{DARK_GRAY}│{RESET} {BOLD}Latency  {RESET}{DARK_GRAY}│{RESET} {BOLD}Score     {RESET}{DARK_GRAY}│{RESET}\n"
    t_mid = f"{DARK_GRAY}├─────────────────────────┼──────────────┼──────────────┼──────────────┼──────────┼───────────┤{RESET}\n"
    rec.emit(t_top + t_hdr + t_mid, delay=0.08)

    models_data = [
        ("gemini-2.5-flash        ", "Google Cloud ", f"{GREEN}✔ PASS (AST) {RESET}", f"{GREEN}✔ 14/14 PASS {RESET}", "0.62s   ", f"{YELLOW}9.2/10   {RESET}"),
        ("claude-3-7-sonnet       ", "Anthropic    ", f"{GREEN}✔ PASS (AST) {RESET}", f"{GREEN}✔ 14/14 PASS {RESET}", "1.02s   ", f"{YELLOW}9.5/10   {RESET}"),
        ("deepseek-reasoner       ", "DeepSeek     ", f"{GREEN}✔ PASS (AST) {RESET}", f"{GREEN}✔ 14/14 PASS {RESET}", "1.38s   ", f"{BOLD}{GREEN}9.8/10 👑 {RESET}"),
        ("gpt-4o                  ", "OpenAI       ", f"{GREEN}✔ PASS (AST) {RESET}", f"{GREEN}✔ 14/14 PASS {RESET}", "0.85s   ", f"{YELLOW}9.1/10   {RESET}"),
        ("qwen2.5-coder:32b       ", "Ollama (Free)", f"{GREEN}✔ PASS (AST) {RESET}", f"{GREEN}✔ 14/14 PASS {RESET}", "1.70s   ", f"{YELLOW}9.0/10   {RESET}"),
    ]

    for m_id, prov, ast_st, ver_st, lat, scr in models_data:
        row = f"{DARK_GRAY}│{RESET} {BOLD}{WHITE}{m_id}{RESET}{DARK_GRAY}│{RESET} {prov}{DARK_GRAY}│{RESET} {ast_st}{DARK_GRAY}│{RESET} {ver_st}{DARK_GRAY}│{RESET} {lat}{DARK_GRAY}│{RESET} {scr}{DARK_GRAY}│{RESET}\n"
        rec.emit(row, delay=0.1)

    t_bot = f"{DARK_GRAY}└─────────────────────────┴──────────────┴──────────────┴──────────────┴──────────┴───────────┘{RESET}\n"
    rec.emit(t_bot, delay=0.15)

    rec.emit(f"{GREEN}🛡️ Consensus Verified:{RESET} {WHITE}Zero lock contention · ABA safe · In-memory LRU fallback active{RESET}\n", delay=0.1)
    rec.emit(f"{YELLOW}👑 Winning Implementation:{RESET} {BOLD}{CYAN}deepseek-reasoner{RESET} (Consensus Agreement: 100.0%)\n\n", delay=0.3)

    # 3. Surgical Diff Card
    rec.emit(f"{BOLD}{WHITE}📜 Surgical Diff Card — {CYAN}src/rate_limiter.py{RESET} {MUTED}(+28, -6 lines){RESET}\n", delay=0.1)
    diff_box = f"""{DARK_GRAY}┌────────────────────────────────────────────────────────────────────────────────────────────────────┐{RESET}
{DARK_GRAY}│{RESET} {MUTED}@@ -14,6 +14,28 @@ class TokenBucketLimiter:{RESET}
{DARK_GRAY}│{RESET} {RED}-    def allow_request(self, key: str) -> bool:{RESET}
{DARK_GRAY}│{RESET} {RED}-        # Slow sequential in-memory lock{RESET}
{DARK_GRAY}│{RESET} {RED}-        with self.lock:{RESET}
{DARK_GRAY}│{RESET} {RED}-            return self._consume_token(key){RESET}
{DARK_GRAY}│{RESET} {GREEN}+    async def allow_request(self, key: str) -> bool:{RESET}
{DARK_GRAY}│{RESET} {GREEN}+        \"\"\"Atomic Token Bucket with distributed Redis Lua & zero-lock memory fallback.\"\"\"{RESET}
{DARK_GRAY}│{RESET} {GREEN}+        try:{RESET}
{DARK_GRAY}│{RESET} {GREEN}+            res = await self.redis.evalsha(self._lua_sha, 1, key, self.capacity, self.rate){RESET}
{DARK_GRAY}│{RESET} {GREEN}+            return bool(res){RESET}
{DARK_GRAY}│{RESET} {GREEN}+        except (ConnectionError, TimeoutError):{RESET}
{DARK_GRAY}│{RESET} {GREEN}+            return self._local_fast_lru_fallback(key){RESET}
{DARK_GRAY}└────────────────────────────────────────────────────────────────────────────────────────────────────┘{RESET}
"""
    rec.emit(diff_box, delay=0.4)
    rec.emit(f"{GREEN}✔ AST Verification: Clean Syntax{RESET} │ {GREEN}✔ Pytest: 14/14 tests pass (0.04s){RESET} │ {CYAN}💰 Cost Saved: $0.038{RESET}\n\n", delay=0.7)

    # 4. Ghost Terminal Autopilot
    rec.type_cmd(prompt, "k-cli ghost 'pytest tests/'", char_speed=0.022, post_pause=0.3)
    rec.emit(f"{MUTED}pytest running against test suite...{RESET}\n", delay=0.1)
    rec.emit(f"{RED}FAILED tests/test_auth.py::test_jwt_decode - TypeError: decode() missing 'algorithms' kwarg{RESET}\n\n", delay=0.2)

    ghost_panel = f"""{PINK}👻 GHOST AUTOPILOT INTERCEPTED CRASH{RESET}
{DARK_GRAY}────────────────────────────────────────────────────────────────────────────────────────────────────────{RESET}
  {BOLD}{WHITE}Exception:{RESET}      {RED}TypeError at src/auth/jwt.py:42{RESET}
  {BOLD}{WHITE}Root Cause:{RESET}     PyJWT v2.0+ requires explicit algorithms list in jwt.decode()
  {BOLD}{WHITE}Surgical Patch:{RESET} {GREEN}+ algorithms=['HS256']{RESET} (1-line addition)
  {BOLD}{WHITE}Verification:{RESET}   {GREEN}✔ AST Validated · Pytest 28/28 Passing{RESET}

  {BOLD}{YELLOW}[ Y  Apply Patch ]{RESET}   {MUTED}[ D  View Diff ]   [ N  Skip ]   [ S  Open in TUI ]{RESET}
"""
    rec.emit(ghost_panel, delay=0.5)
    rec.type_cmd(f"{YELLOW}Choice: {RESET}", "Y", char_speed=0.07, post_pause=0.2)
    rec.emit(f"{GREEN}✔ Patch cleanly applied to src/auth/jwt.py. Test runner re-executed: 100% green.{RESET}\n\n", delay=0.6)

    # 5. Launch Full TUI Cyber Workstation
    rec.type_cmd(prompt, "k", char_speed=0.028, post_pause=0.35)

    tui_view = f"""\x1b[2J\x1b[H{DOT_RED} {DOT_YELLOW} {DOT_GREEN}  {BOLD}{CYAN}⚡ K-CLI CYBER WORKSTATION{RESET} │ {YELLOW}🤖 gemini-2.5-flash{RESET} │ {PINK} main (+1 ~0){RESET} │ {GREEN}💾 184MB RSS{RESET} │ {YELLOW}🏎️ 248 tok/s{RESET} │ {GREEN}💰 $0.003{RESET} │ {GREEN}🛡️ AST OK ●{RESET}
{CYAN}════════════════════════════════════════════════════════════════════════════════════════════════════════{RESET}
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
    rec.emit(tui_view, delay=3.8)

    rec.save(CAST_FILE)
    print(f"✔ Viral Asciicast saved: {CAST_FILE}")


if __name__ == "__main__":
    generate_recording()
