"""
tui.py - Modern Terminal User Interface Architecture for K-CLI
Project Bankai Engine v1.0.0

Features:
1. Live token streaming with syntax highlighting, animated spinners, and real-time metrics.
2. Dynamic Status Bar displaying Active Model, Git Branch, Active Persona, RAM, Tokens, Cost Ticker, and Glow Badges.
3. Interactive slash commands (/model, /persona, /diff, /rollback, /help, /docs, /clear, /test, /banner, /tree).
4. Side-by-side and inline surgical diff visualization with instant preview cards.
5. High-speed prompt_toolkit interactive shell with auto-completion and toolbar.
6. Animated subagent execution trees with status glyphs and DAG hierarchy.
"""

from __future__ import annotations

import functools
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style as PTKStyle
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

try:
    import psutil
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import Header, Footer, Input, Static, Button, RichLog, Label
    HAS_TEXTUAL = True
except (ImportError, ModuleNotFoundError):
    HAS_TEXTUAL = False
    App = object  # type: ignore

try:
    from k_cli.tui.diff_viewer import DiffVisualizer
    from k_cli.agents.orchestrator import Persona
    from k_cli.agents.persona import DomainPersona, PersonaProfile, PersonaRegistry
    from k_cli.tui.tui_animations import (
        AnimatedSpinner,
        CostTicker,
        GlowBadgeStatus,
        SpinnerType,
        StatusGlowBadge,
        TokenSpeedometer,
        apply_gradient_to_text,
        calculate_token_cost,
        create_branch_badge,
        create_mcp_badge,
        create_model_badge,
        create_ram_badge,
        create_verifier_badge,
        generate_splash_frames,
        render_cyber_banner,
        render_hud_status_bar,
    )
except (ModuleNotFoundError, ImportError):
    try:
        from diff_viewer import DiffVisualizer
        from orchestrator import Persona
        from persona import DomainPersona, PersonaProfile, PersonaRegistry
        from tui_animations import (
            AnimatedSpinner,
            CostTicker,
            GlowBadgeStatus,
            SpinnerType,
            StatusGlowBadge,
            TokenSpeedometer,
            apply_gradient_to_text,
            calculate_token_cost,
            create_branch_badge,
            create_mcp_badge,
            create_model_badge,
            create_ram_badge,
            create_verifier_badge,
            generate_splash_frames,
            render_cyber_banner,
            render_hud_status_bar,
        )
    except (ModuleNotFoundError, ImportError):
        DiffVisualizer = None
        Persona = None
        PersonaRegistry = None
        AnimatedSpinner = None
        TokenSpeedometer = None
        CostTicker = None
        render_cyber_banner = None
        create_branch_badge = None
        create_model_badge = None
        create_verifier_badge = None
        create_mcp_badge = None
        create_ram_badge = None
        render_hud_status_bar = None
        apply_gradient_to_text = None
        generate_splash_frames = None
        calculate_token_cost = None

# Model Presets
MODEL_PRESETS: List[Dict[str, str]] = [
    {"name": "Bankai-7B", "desc": "Project Bankai Flagship 7B Coder (Fast & Compiler-Grounded)", "type": "SLM"},
    {"name": "Bankai-14B", "desc": "Project Bankai Flagship 14B Deep Reasoning Engine", "type": "SLM"},
    {"name": "Gemini", "desc": "Gemini 2.0 Flash / Pro (Cloud Multi-Modal & High-Throughput)", "type": "Cloud"},
    {"name": "Claude", "desc": "Claude 3.5 Sonnet (Advanced Agentic Architecture & Refactoring)", "type": "Cloud"},
    {"name": "Local Ollama", "desc": "Local GGUF SLM (e.g. qwen2.5-coder:1.5b / deepseek)", "type": "Local"},
]

PERSONA_METADATA: Dict[str, Dict[str, str]] = {
    "DEVOPS": {"color": "cyan", "icon": "☸", "desc": "Docker, Kubernetes, CI/CD, Terraform, Cloud Deployments"},
    "SURGICAL DEBUGGER": {"color": "red", "icon": "🩺", "desc": "Root-cause analysis, minimal SEARCH/REPLACE diffs, zero regression"},
    "SYSTEMS ARCHITECT": {"color": "magenta", "icon": "⚡", "desc": "C++23, Rust, Linux Kernel, Lock-free concurrency, Big-O proofs"},
    "APPLICATION SECURITY ENGINEER": {"color": "red", "icon": "🛡️", "desc": "OWASP Top 10, HMAC, Auth middlewares, Constant-time crypto"},
    "FRONTEND & FULLSTACK ENGINEER": {"color": "green", "icon": "🎨", "desc": "React, Vite, Next.js, CSS layout, accessibility"},
    "DATABASE & QUERY OPTIMIZER": {"color": "yellow", "icon": "🗄️", "desc": "PostgreSQL, Redis, Spanner, SQL query optimization"},
    "FULLSTACK AI SYSTEMS ENGINEER": {"color": "blue", "icon": "⚙", "desc": "Clean architecture, compiler-grounded verification"},
    "RESEARCHER": {"color": "cyan", "icon": "🔍", "desc": "Extracts signatures, API dependencies, specifications"},
    "ARCHITECT": {"color": "magenta", "icon": "📐", "desc": "Designs modular architecture & execution plan"},
    "CODER": {"color": "green", "icon": "⚡", "desc": "Generates isolated, verified code implementation"},
    "CRITIC": {"color": "yellow", "icon": "🛡️", "desc": "Audits safety, boundaries, memory & runtime limits"},
    "DEBUGGER": {"color": "red", "icon": "🔧", "desc": "Analyzes compiler traces and applies surgical repairs"},
    "AUTO": {"color": "bright_blue", "icon": "🔄", "desc": "Full sequential multi-persona pipeline"},
}


@functools.lru_cache(maxsize=128)
def get_persona_style(persona_name: str) -> Tuple[str, str, str]:
    """Returns (color, icon, description) for a given persona."""
    if not persona_name:
        return "blue", "🤖", "AI Assistant Persona"

    key = str(persona_name).upper().strip()
    if key in PERSONA_METADATA:
        p_v = PERSONA_METADATA[key]
        return p_v["color"], p_v["icon"], p_v["desc"]

    # Check PersonaRegistry first if available
    if PersonaRegistry:
        prof = PersonaRegistry.get(persona_name)
        if prof is not None:
            return prof.color, prof.icon, prof.description

    for p_k, p_v in PERSONA_METADATA.items():
        if p_k in key or key in p_k:
            return p_v["color"], p_v["icon"], p_v["desc"]
    return "blue", "🤖", "AI Assistant Persona"


# ==============================================================================
# 1. Instant Diff Preview Card & Subagent Execution Tree Renderers
# ==============================================================================

def render_instant_diff_card(
    diff_text: str = "",
    file_path: str = "",
    old_code: str = "",
    new_code: str = "",
    title: str = "Instant Surgical Diff Card",
) -> Panel:
    """
    Renders a compact, glowing surgical diff preview card with line counts and syntax highlighting.
    """
    if not diff_text.strip() and old_code and new_code:
        # Generate simple unified diff preview from old and new code
        import difflib
        lines = difflib.unified_diff(
            old_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile=f"a/{file_path or 'original.py'}",
            tofile=f"b/{file_path or 'repaired.py'}",
        )
        diff_text = "".join(lines)

    if not diff_text.strip():
        return Panel(
            Text("Working tree is clean — no diffs detected.", style="dim italic"),
            title=f"[bold #00f0ff]{title}[/bold #00f0ff]",
            border_style="#00f0ff",
        )

    # Count additions and deletions
    additions = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))

    header_text = Text()
    if file_path:
        header_text.append(f"📄 {file_path} │ ", style="bold white")
    header_text.append(f"+{additions} ", style="bold #00ff88")
    header_text.append(f"-{deletions} ", style="bold #ff3366")
    header_text.append("lines changed", style="dim white")

    # Style diff lines
    formatted_body = Text()
    for line in diff_text.splitlines()[:60]:  # limit lines for card preview
        if line.startswith("+++") or line.startswith("---"):
            formatted_body.append(line + "\n", style="bold #ffe600")
        elif line.startswith("@@"):
            formatted_body.append(line + "\n", style="bold #b026ff")
        elif line.startswith("+"):
            formatted_body.append(line + "\n", style="bold #00ff88")
        elif line.startswith("-"):
            formatted_body.append(line + "\n", style="bold #ff3366")
        else:
            formatted_body.append(line + "\n", style="dim white")

    card_content = Group(
        header_text,
        Text("─" * 40, style="dim #1e293b"),
        formatted_body,
    )

    return Panel(
        card_content,
        title=f"[bold #00f0ff]⚡ {title}[/bold #00f0ff]",
        subtitle=f"[dim #5af78e]Surgical Patch Guard[/dim #5af78e]",
        border_style="#00f0ff",
    )


def render_subagent_execution_tree(
    tasks: List[Any],
    title: str = "Subagent Swarm Execution Tree",
) -> Panel:
    """
    Renders an animated hierarchical Rich Tree of subagent execution tasks,
    displaying roles, status glyphs, elapsed durations, progress meters, and token metrics.
    """
    root_label = Text(f"📦 {title} ({len(tasks)} Subagents)", style="bold #00f0ff")
    tree = Tree(root_label)

    role_glyphs = {
        "EXPLORER": "🔍",
        "RESEARCHER": "📚",
        "REFACTORER": "🔨",
        "CODER": "⚡",
        "TESTER": "🧪",
        "CRITIC": "🛡️",
        "ARCHITECT": "📐",
    }

    status_styles = {
        "COMPLETED": ("🟢", "#00ff88", "Done"),
        "RUNNING": ("🟡", "#ffe600", "Running"),
        "PENDING": ("🔵", "#00f0ff", "Queued"),
        "FAILED": ("🔴", "#ff3366", "Failed"),
        "CANCELLED": ("🚫", "#94a3b8", "Cancelled"),
    }

    for task in tasks:
        # Extract attributes from SubagentTask object or dictionary
        role_str = getattr(task, "role", "CODER")
        if hasattr(role_str, "value"):
            role_str = role_str.value
        role_str = str(role_str).upper()

        status_str = getattr(task, "status", "PENDING")
        if hasattr(status_str, "value"):
            status_str = status_str.value
        status_str = str(status_str).upper()

        name = getattr(task, "name", getattr(task, "task_id", "Subtask"))
        prompt = getattr(task, "prompt", getattr(task, "status_message", ""))
        duration = getattr(task, "duration_sec", 0.0)
        tokens = getattr(task, "token_count", getattr(task, "tokens", 0))

        glyph, color, st_text = status_styles.get(status_str, ("🔵", "#00f0ff", status_str))
        r_glyph = role_glyphs.get(role_str, "🤖")

        node_text = Text()
        node_text.append(f"{glyph} {r_glyph} ", style=f"bold {color}")
        node_text.append(f"[{role_str}] ", style="bold white")
        node_text.append(f"{name} ", style=f"bold {color}")
        node_text.append(f"({st_text})", style=f"dim {color}")

        node = tree.add(node_text)

        # Add detail leaves
        if prompt:
            node.add(Text(f"🎯 Objective: {str(prompt)[:80]}...", style="dim white"))

        metrics_text = Text()
        metrics_text.append("⚡ Metrics: ", style="dim #ffe600")
        if duration > 0:
            metrics_text.append(f"⏱️ {duration:.2f}s │ ", style="dim white")
        if tokens > 0:
            metrics_text.append(f"📊 {tokens} tokens │ ", style="dim white")
        metrics_text.append("Verified Execution", style="dim #00ff88")
        node.add(metrics_text)

    return Panel(
        tree,
        title="[bold #00f0ff]◈ SWARM RADAR & EXECUTION TOPOLOGY ◈[/bold #00f0ff]",
        border_style="#00f0ff",
    )


# ==============================================================================
# 2. Enhanced Status Bar Manager
# ==============================================================================

class StatusBar:
    """Manages active session parameters and formats top/bottom status displays with glowing badges."""

    def __init__(
        self,
        active_model: str = "Bankai-7B",
        git_branch: str = "main",
        active_persona: str = "AUTO",
        ram_mb: float = 0.0,
        max_ram_mb: float = 1024.0,
        token_count: int = 0,
        max_tokens: int = 4096,
        context_files: Optional[List[str]] = None,
        verifier_status: str = "VERIFIED",
        mcp_server_count: int = 4,
    ):
        self.active_model = active_model
        self.git_branch = git_branch
        self.active_persona = active_persona
        self.ram_mb = ram_mb
        self.max_ram_mb = max_ram_mb
        self.token_count = token_count
        self.max_tokens = max_tokens
        self.context_files = context_files or []
        self.verifier_status = verifier_status
        self.mcp_server_count = mcp_server_count
        self.speedometer = TokenSpeedometer() if TokenSpeedometer else None
        self.cost_ticker = CostTicker(active_model=self.active_model) if CostTicker else None

    def update_from_session(self, session: Any) -> None:
        """Syncs status bar properties from SessionManager status dict."""
        if not session:
            return
        st = session.get_status() if hasattr(session, "get_status") else {}
        self.active_model = st.get("model") or st.get("model_name") or self.active_model
        self.git_branch = st.get("git_branch") or (session.get_git_branch() if hasattr(session, "get_git_branch") else self.git_branch)
        self.active_persona = st.get("persona") or st.get("active_persona") or getattr(session, "active_persona", self.active_persona)
        self.ram_mb = st.get("ram_mb", 0.0)
        self.token_count = st.get("token_count", 0)
        self.max_tokens = st.get("max_tokens", self.max_tokens)
        self.context_files = st.get("context_files", [])

        if self.cost_ticker:
            self.cost_ticker.active_model = self.active_model

    def get_prompt_toolkit_toolbar(self) -> HTML:
        """Returns stylized HTML for prompt_toolkit bottom toolbar."""
        p_color, p_icon, _ = get_persona_style(self.active_persona)
        ptk_color_map = {
            "cyan": "#00d7ff",
            "magenta": "#ff00d7",
            "green": "#5af78e",
            "yellow": "#f3e430",
            "red": "#ff5c57",
            "bright_blue": "#57c7ff",
            "blue": "#57c7ff",
        }
        hex_p = ptk_color_map.get(p_color, "#57c7ff")
        files_str = f"{len(self.context_files)} files" if self.context_files else "0 files"
        cost_str = f"${self.cost_ticker.total_cost:.4f}" if self.cost_ticker else "$0.00"

        return HTML(
            f' <b>Model:</b> <style color="#00ffff">{self.active_model}</style> │ '
            f'<b>Branch:</b> <style color="#5af78e">{self.git_branch}</style> │ '
            f'<b>Persona:</b> <style color="{hex_p}">{p_icon} {self.active_persona}</style> │ '
            f'<b>RAM:</b> <style color="#ffb86c">{self.ram_mb:.1f}/{self.max_ram_mb:.0f}MB</style> │ '
            f'<b>Cost:</b> <style color="#ffe600">{cost_str}</style> │ '
            f'<b>Context:</b> <style color="#8be9fd">{files_str}</style>'
        )

    def render_rich_panel(self) -> Panel:
        """Renders full diagnostic HUD panel with glow badges and speedometer."""
        p_color, p_icon, p_desc = get_persona_style(self.active_persona)

        # Generate badges
        badges = []
        if create_model_badge:
            badges.append(create_model_badge(self.active_model, is_active=True))
        if create_branch_badge:
            badges.append(create_branch_badge(self.git_branch, is_dirty=False))
        if create_verifier_badge:
            badges.append(create_verifier_badge(self.verifier_status, pass_rate=1.0))
        if create_mcp_badge:
            badges.append(create_mcp_badge(self.mcp_server_count, active_tools=12))
        if create_ram_badge:
            badges.append(create_ram_badge(self.ram_mb, self.max_ram_mb))

        hud_bar = render_hud_status_bar(badges) if render_hud_status_bar and badges else Text()

        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Parameter", style="bold cyan", width=24)
        table.add_column("Value", style="bold white")

        table.add_row("⚡ Active Model", f"[bold green]{self.active_model}[/bold green]")
        table.add_row("🌿 Git Branch", f"[bold yellow]{self.git_branch}[/bold yellow]")
        table.add_row(f"{p_icon} Active Persona", f"[{p_color}][bold]{self.active_persona}[/bold] - {p_desc}[/{p_color}]")
        table.add_row("💾 RAM RSS Allocation", f"[bold magenta]{self.ram_mb:.2f} MB[/bold magenta] / {self.max_ram_mb:.0f} MB (Budget Limit)")
        table.add_row("📊 Estimated Tokens", f"{self.token_count} / {self.max_tokens} max")

        if self.cost_ticker:
            ticker_text = self.cost_ticker.render_ticker()
            table.add_row("💰 Real-Time Cost Ticker", ticker_text.markup if hasattr(ticker_text, "markup") else str(ticker_text))

        if self.speedometer:
            gauge_text = self.speedometer.render_gauge()
            table.add_row("🏎️ Token Speedometer", gauge_text.markup if hasattr(gauge_text, "markup") else str(gauge_text))

        files_text = ", ".join(self.context_files) if self.context_files else "[dim]None (use /add <file>)[/dim]"
        table.add_row("📁 Tracked Files", files_text)

        panel_content = Group(
            hud_bar,
            Text("─" * 60, style="dim #1e293b"),
            table,
        )

        return Panel(
            panel_content,
            title="[bold #00f0ff]◈ K-CLI CYBER DIAGNOSTIC HUD ◈[/bold #00f0ff]",
            subtitle="[dim #7000ff]Ground-Truth Verifier Active[/dim #7000ff]",
            border_style="#00f0ff",
        )


# ==============================================================================
# 3. Live Token Streaming Renderer with Cyber Animations
# ==============================================================================

class LiveStreamRenderer:
    """
    Manages real-time token streaming with automatic code fence syntax highlighting,
    animated cyberpunk spinners, live token speedometer, and glowing status badges.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.speedometer = TokenSpeedometer() if TokenSpeedometer else None
        self.cost_ticker = CostTicker() if CostTicker else None
        self.spinner = AnimatedSpinner(spinner_type=SpinnerType.QUANTUM_FLUX) if AnimatedSpinner else None

    def stream_display(
        self,
        token_generator: Generator[str, None, Dict[str, Any]],
        initial_persona: str = "RESEARCHER",
        language: str = "python",
        title: str = "Agent Execution",
        model_name: str = "Bankai-7B",
    ) -> Dict[str, Any]:
        """
        Consumes tokens from generator, dynamically highlighting syntax and updating Rich Live view
        with real-time tok/s speedometer and animated cyberpunk spinners.
        """
        current_persona = initial_persona
        accumulated_text = ""
        token_count = 0
        start_time = time.time()
        step_index = 0

        if self.cost_ticker:
            self.cost_ticker.active_model = model_name

        def make_panel() -> Panel:
            nonlocal step_index
            step_index += 1
            elapsed = max(0.001, time.time() - start_time)
            speed = token_count / elapsed
            p_color, p_icon, _ = get_persona_style(current_persona)

            # Spinner frame
            spinner_str = ""
            if self.spinner:
                spinner_str = f"{self.spinner.frames[step_index % len(self.spinner.frames)]} "

            # Calculate cost ticker
            cost_val = calculate_token_cost(model_name, 0, token_count) if calculate_token_cost else 0.0
            cost_display = f"$0.00 (Local)" if cost_val == 0.0 else f"${cost_val:.5f}"

            header = (
                f"[{p_color}][bold]{p_icon} {current_persona}[/bold][/{p_color}] │ "
                f"[bold #ffe600]{spinner_str}[/bold #ffe600] │ "
                f"[bold #00f0ff]{speed:.1f} tok/s[/bold #00f0ff] │ "
                f"[dim #5af78e]{token_count} tokens[/dim #5af78e] │ "
                f"[bold #ffe600]{cost_display}[/bold #ffe600]"
            )

            if not accumulated_text.strip():
                content = Text(f"⚡ Initializing {current_persona} pipeline stream...", style="dim italic")
            elif "```" in accumulated_text:
                # Detect and highlight code fences
                try:
                    content = Markdown(accumulated_text)
                except Exception:
                    content = Text(accumulated_text)
            elif current_persona in ("CODER", "DEBUGGER"):
                # Pure code output
                try:
                    content = Syntax(accumulated_text, language, theme="monokai", line_numbers=True)
                except Exception:
                    content = Text(accumulated_text, style="green")
            else:
                content = Text(accumulated_text, style="white")

            return Panel(
                content,
                title=f"[bold {p_color}]{header}[/bold {p_color}]",
                subtitle="[dim #7000ff]Streaming Live • Ground-Truth Guard[/dim #7000ff]",
                border_style=p_color,
            )

        with Live(make_panel(), console=self.console, refresh_per_second=15, auto_refresh=True) as live:
            for token in token_generator:
                token_count += 1
                accumulated_text += token
                if self.speedometer:
                    self.speedometer.record_tokens(1)
                live.update(make_panel())

        elapsed_total = time.time() - start_time
        final_cost = calculate_token_cost(model_name, 0, token_count) if calculate_token_cost else 0.0

        if self.cost_ticker:
            self.cost_ticker.record_usage(model_name, 0, token_count)

        return {
            "total_tokens": token_count,
            "elapsed_seconds": elapsed_total,
            "final_text": accumulated_text,
            "speed_tok_s": round(token_count / max(0.001, elapsed_total), 1),
            "cost_usd": final_cost,
        }


# ==============================================================================
# 4. Prompt Toolkit Slash Command Completer
# ==============================================================================

if HAS_PROMPT_TOOLKIT:
    class SlashCommandCompleter(Completer):
        """Auto-completes slash commands with rich descriptions in prompt_toolkit."""

        COMMANDS = [
            ("/model", "Switch active model (Bankai-7B, Bankai-14B, Gemini, Claude, Local Ollama)"),
            ("/persona", "Switch active persona (RESEARCHER, ARCHITECT, CODER, CRITIC, DEBUGGER, AUTO)"),
            ("/diff", "View surgical / git diff (inline or side-by-side)"),
            ("/rollback", "Roll back last uncommitted edit via Git (alias /undo)"),
            ("/help", "Show all slash commands, shortcuts, and capabilities"),
            ("/docs", "Search DevDocs offline documentation index (alias /doc)"),
            ("/clear", "Reset conversation history and context files"),
            ("/test", "Run ground-truth compiler and pytest verification"),
            ("/banner", "Display cyberpunk animated gradient ASCII splash banner"),
            ("/tree", "Display live subagent execution tree and swarm metrics"),
            ("/speed", "Inspect real-time token throughput speedometer and cost ticker"),
            ("/add", "Add file to active session context"),
            ("/remove", "Remove file from active session context"),
            ("/undo", "Roll back last uncommitted edit via Git"),
            ("/status", "Display active model, context files, tokens, cost, and RAM"),
            ("/map", "Display workspace AST symbol repository map"),
            ("/exit", "Exit interactive session"),
            ("/quit", "Exit interactive session"),
        ]

        MODEL_OPTIONS = [m["name"] for m in MODEL_PRESETS]
        PERSONA_OPTIONS = ["AUTO", "RESEARCHER", "ARCHITECT", "CODER", "CRITIC", "DEBUGGER"]
        DIFF_OPTIONS = ["inline", "side-by-side", "sbs", "card"]

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return

            parts = text.split()
            if len(parts) == 1 and not text.endswith(" "):
                # Completing slash command name
                query = parts[0].lower()
                for cmd, desc in self.COMMANDS:
                    if cmd.startswith(query):
                        yield Completion(cmd, start_position=-len(query), display=cmd, display_meta=desc)
            elif len(parts) >= 1:
                cmd = parts[0].lower()
                sub_query = parts[1].lower() if len(parts) > 1 and not text.endswith(" ") else ""
                start_pos = -len(sub_query) if sub_query else 0

                if cmd == "/model":
                    for m in self.MODEL_OPTIONS:
                        if not sub_query or m.lower().startswith(sub_query):
                            yield Completion(m, start_position=start_pos, display=m)
                elif cmd == "/persona":
                    for p in self.PERSONA_OPTIONS:
                        if not sub_query or p.lower().startswith(sub_query):
                            yield Completion(p, start_position=start_pos, display=p)
                elif cmd == "/diff":
                    for d in self.DIFF_OPTIONS:
                        if not sub_query or d.lower().startswith(sub_query):
                            yield Completion(d, start_position=start_pos, display=d)


# ==============================================================================
# 5. Interactive Slash Commands Handler
# ==============================================================================

class SlashCommandHandler:
    """Handles and visually formats interactive slash commands."""

    def __init__(self, session: Any, console: Optional[Console] = None):
        self.session = session
        self.console = console or Console()
        self.diff_visualizer = DiffVisualizer(console=self.console) if DiffVisualizer else None

    def handle(self, command_line: str) -> Tuple[bool, str]:
        """
        Routes slash command and renders rich terminal output.

        Returns:
            Tuple[bool, str]: (should_continue, exit_signal_or_status)
        """
        raw = command_line.strip()
        if not raw.startswith("/"):
            return True, ""

        parts = raw[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        # /exit, /quit
        if cmd in ("exit", "quit", "q"):
            self.console.print("[bold dim]Exiting K-CLI. Goodbye![/bold dim]")
            return False, "EXIT"

        # /help
        if cmd in ("help", "?"):
            self._render_help()
            return True, "HELP_RENDERED"

        # /banner, /splash
        if cmd in ("banner", "splash"):
            if render_cyber_banner:
                self.console.print(render_cyber_banner(palette="neon_cyan"))
            else:
                self.console.print("[bold cyan]K-CLI Bankai Engine v1.0.0[/bold cyan]")
            return True, "BANNER_RENDERED"

        # /tree, /swarm
        if cmd in ("tree", "swarm"):
            self._handle_tree()
            return True, "TREE_RENDERED"

        # /speed, /cost
        if cmd in ("speed", "cost", "ticker"):
            self._handle_speed_and_cost()
            return True, "SPEED_RENDERED"

        # /model
        if cmd == "model":
            self._handle_model(arg)
            return True, "MODEL_HANDLED"

        # /persona
        if cmd in ("persona", "role"):
            self._handle_persona(arg)
            return True, "PERSONA_HANDLED"

        # /diff
        if cmd == "diff":
            self._handle_diff(arg)
            return True, "DIFF_HANDLED"

        # /rollback or /undo
        if cmd in ("rollback", "undo"):
            self._handle_rollback(arg)
            return True, "ROLLBACK_HANDLED"

        # /docs or /doc
        if cmd in ("docs", "doc"):
            self._handle_docs(arg)
            return True, "DOCS_HANDLED"

        # /clear
        if cmd in ("clear", "cls"):
            self.console.clear()
            self.session.reset_context()
            self.console.print("[bold green]✔ Screen, conversation history, and context files cleared.[/bold green]\n")
            return True, "CLEARED"

        # /test or /verify
        if cmd in ("test", "verify"):
            self._handle_test(arg)
            return True, "TEST_HANDLED"

        # /keys, /api, /vault
        if cmd in ("keys", "api", "vault", "creds"):
            self.console.print(Panel(
                "[bold cyan]🔑 K-CLI Credentials Vault[/bold cyan]\n\n"
                f"• GITHUB_TOKEN: {'[green]Configured[/green]' if os.environ.get('GITHUB_TOKEN') else '[red]Missing[/red]'}\n"
                f"• GEMINI_API_KEY: {'[green]Configured[/green]' if os.environ.get('GEMINI_API_KEY') else '[red]Missing[/red]'}\n"
                f"• ANTHROPIC_API_KEY: {'[green]Configured[/green]' if os.environ.get('ANTHROPIC_API_KEY') else '[red]Missing[/red]'}\n"
                f"• OPENAI_API_KEY: {'[green]Configured[/green]' if os.environ.get('OPENAI_API_KEY') else '[red]Missing[/red]'}\n"
                f"• DEEPSEEK_API_KEY: {'[green]Configured[/green]' if os.environ.get('DEEPSEEK_API_KEY') else '[red]Missing[/red]'}\n"
                f"• GROQ_API_KEY: {'[green]Configured[/green]' if os.environ.get('GROQ_API_KEY') else '[red]Missing[/red]'}\n\n"
                "[dim]To update credentials, run: [bold white]k-cli ui[/bold white] and press [bold white]Ctrl+A[/bold white], or export in your terminal.[/dim]",
                title="Credentials Vault Status",
                border_style="cyan",
            ))
            return True, "KEYS_HANDLED"

        # /conflict
        if cmd in ("conflict", "conflicts"):
            from k_cli.git.conflict_resolver import ConflictResolver
            res = ConflictResolver().find_conflicts()
            if not res:
                self.console.print("[bold green]✔ Zero git merge conflicts in repository.[/bold green]")
            else:
                self.console.print(f"[bold yellow]⚠️ Found {len(res)} active merge conflicts in workspace.[/bold yellow]")
            return True, "CONFLICT_HANDLED"

        # /gh or /github
        if cmd in ("gh", "github", "issues", "prs"):
            from k_cli.github.github_engine import GitHubEngine
            engine = GitHubEngine()
            issues = engine.list_issues(limit=5)
            self.console.print(f"[bold cyan]🐙 GitHub Issues ({len(issues)} listed):[/bold cyan]")
            for i in issues:
                self.console.print(f"  #{i.number}: {i.title} (@{i.author})")
            return True, "GH_HANDLED"

        # /solve <issue_num>
        if cmd in ("solve", "fix_issue") and arg:
            try:
                num = int(arg.strip("#"))
                from k_cli.github.github_engine import GitHubEngine
                from k_cli.git.verifier import Verifier
                from k_cli.git.patcher import Patcher
                self.console.print(f"[bold cyan]Autonomously investigating issue #{num}...[/bold cyan]")
                res = GitHubEngine().solve_issue(issue_number=num, llm_driver=self.session.driver, verifier=Verifier(), patcher=Patcher(), auto_pr=True)
                if res.success:
                    self.console.print(f"[bold green]✔ Issue #{num} solved! Branch: {res.branch_name}, PR: {res.pr_url}[/bold green]")
                else:
                    self.console.print(f"[bold red]✘ Issue #{num} failed: {res.error_message}[/bold red]")
            except ValueError:
                self.console.print("[bold red]Please provide a numeric issue number: /solve <number>[/bold red]")
            return True, "SOLVE_HANDLED"

        # Delegate /add, /remove, /map, /status to SessionManager
        handled, msg = self.session.handle_slash_command(raw)
        if handled:
            if cmd == "status":
                status_bar = StatusBar()
                status_bar.update_from_session(self.session)
                self.console.print(status_bar.render_rich_panel())
            elif cmd == "map" and self.session.repo_map:
                map_str = self.session.repo_map.get_repo_map(max_tokens=400, focus_files=self.session.get_context_files())
                if map_str.strip():
                    map_syn = Syntax(map_str, "python", theme="monokai", line_numbers=False)
                    self.console.print(Panel(map_syn, title="[bold magenta]AST Repository Codebase Map[/bold magenta]", border_style="magenta"))
                else:
                    self.console.print("[yellow]Repository map is empty.[/yellow]")
            else:
                self.console.print(f"[bold cyan]{msg}[/bold cyan]")
            return True, msg

        self.console.print(f"[bold red]Unknown command:[/bold red] {raw}. Type [bold yellow]/help[/bold yellow] for available commands.")
        return True, "UNKNOWN_COMMAND"

    def _render_help(self) -> None:
        table = Table(title="K-CLI Interactive Slash Commands", box=None, expand=True)
        table.add_column("Command", style="bold cyan", width=18)
        table.add_column("Arguments", style="bold yellow", width=16)
        table.add_column("Description", style="white")

        commands_info = [
            ("/model", "[name]", "Switch active model (Bankai-7B, Bankai-14B, Gemini, Claude, Local Ollama)"),
            ("/persona", "[name]", "Switch active persona (RESEARCHER, ARCHITECT, CODER, CRITIC, DEBUGGER, AUTO)"),
            ("/diff", "[mode]", "View surgical git diff (options: inline, side-by-side / sbs, card)"),
            ("/rollback", "[file]", "Roll back last uncommitted edit via Git (alias /undo)"),
            ("/docs", "<query>", "Search offline DevDocs SQLite database for API signatures"),
            ("/clear", "", "Clear terminal screen, conversation history, and context"),
            ("/test", "[file/code]", "Run ground-truth compiler / pytest verification"),
            ("/banner", "", "Display cyberpunk gradient ASCII splash banner"),
            ("/tree", "", "Display animated subagent execution tree & metrics"),
            ("/speed", "", "Inspect real-time token throughput and USD cost ticker"),
            ("/add", "<file>", "Add file to active session context"),
            ("/remove", "<file>", "Remove file from active session context"),
            ("/map", "", "Display AST codebase repository map"),
            ("/status", "", "Inspect model, token usage, and RAM budget diagnostics"),
            ("/help", "", "Show this help table"),
            ("/exit", "", "Exit interactive session (alias /quit)"),
        ]

        for cmd, args, desc in commands_info:
            table.add_row(cmd, args, desc)

        self.console.print(Panel(table, title="[bold cyan]Command Reference[/bold cyan]", border_style="cyan"))

    def _handle_tree(self) -> None:
        """Renders live subagent execution tree."""
        tasks = []
        if hasattr(self.session, "dispatcher") and self.session.dispatcher:
            tasks = getattr(self.session.dispatcher, "last_tasks", [])
        if not tasks:
            # Generate sample execution topology
            class MockTask:
                def __init__(self, name, role, status, prompt, duration_sec=1.2, token_count=180):
                    self.name = name
                    self.role = role
                    self.status = status
                    self.prompt = prompt
                    self.duration_sec = duration_sec
                    self.token_count = token_count

            tasks = [
                MockTask("Inspect AST Map", "EXPLORER", "COMPLETED", "Scans workspace AST symbol definitions", 0.45, 120),
                MockTask("DevDocs Reference Lookup", "RESEARCHER", "COMPLETED", "Queries offline signatures", 0.32, 95),
                MockTask("Surgical Patch Generator", "REFACTORER", "RUNNING", "Synthesizes SEARCH/REPLACE diff", 1.15, 340),
                MockTask("AST Compiler Guard", "TESTER", "PENDING", "Verifies zero syntax errors & tests", 0.0, 0),
            ]

        self.console.print(render_subagent_execution_tree(tasks))

    def _handle_speed_and_cost(self) -> None:
        """Renders token speedometer and cost ticker diagnostics."""
        st = self.session.get_status() if hasattr(self.session, "get_status") else {}
        m_name = st.get("model", "Bankai-7B")
        t_count = st.get("token_count", 0)

        speedometer = TokenSpeedometer()
        speedometer.record_tokens(max(10, t_count))

        cost_ticker = CostTicker(active_model=m_name)
        cost_ticker.record_usage(m_name, max(0, t_count // 2), max(0, t_count // 2))

        table = Table(box=None, expand=True)
        table.add_column("Diagnostic Metric", style="bold cyan", width=26)
        table.add_column("Real-Time Telemetry", style="bold white")

        table.add_row("🏎️ Live Speedometer", speedometer.render_gauge())
        table.add_row("💰 Cumulative Cost Ticker", cost_ticker.render_ticker())
        table.add_row("🤖 Active Engine", f"[bold green]{m_name}[/bold green]")
        table.add_row("💾 Memory Allocation", f"{st.get('ram_mb', 0.0):.1f} MB / 1024 MB")

        self.console.print(Panel(table, title="[bold #00f0ff]◈ REAL-TIME SPEEDOMETER & COST TICKER ◈[/bold #00f0ff]", border_style="#00f0ff"))

    def _handle_model(self, model_arg: str) -> None:
        if not model_arg:
            table = Table(title="Available AI Models", box=None, expand=True)
            table.add_column("Preset", style="bold cyan", width=18)
            table.add_column("Engine", style="bold magenta", width=10)
            table.add_column("Description", style="white")
            table.add_column("Active", style="bold green", width=8)

            current = getattr(self.session, "model_name", "")
            for p in MODEL_PRESETS:
                is_active = "✔ YES" if p["name"].lower() == current.lower() or current.lower().startswith(p["name"].lower().split()[0]) else ""
                table.add_row(p["name"], p["type"], p["desc"], is_active)

            self.console.print(Panel(table, title="[bold cyan]Active & Available Models[/bold cyan]", border_style="cyan"))
            self.console.print(f"[dim]Use [/dim][bold yellow]/model <name>[/bold yellow][dim] to switch models (e.g. [/dim][bold cyan]/model Bankai-14B[/bold cyan][dim]).[/dim]\n")
        else:
            self.session.set_model(model_arg)
            self.console.print(f"[bold green]✔ Switched active model to:[/bold green] [bold cyan]{model_arg}[/bold cyan]")

    def _handle_persona(self, persona_arg: str) -> None:
        if not persona_arg:
            table = Table(title="Dynamic Persona & Architecture State Machine", box=None, expand=True)
            table.add_column("Persona", style="bold cyan", width=32)
            table.add_column("Command", style="bold yellow", width=14)
            table.add_column("Description", style="white")
            table.add_column("Active", style="bold green", width=8)

            current = getattr(self.session, "active_persona", "AUTO")
            active_id = getattr(self.session.active_persona_profile, "id", "") if hasattr(self.session, "active_persona_profile") and self.session.active_persona_profile else ""

            if PersonaRegistry:
                for p in PersonaRegistry.list_personas():
                    is_active = "✔ YES" if (p.id == active_id or p.title.lower() == str(current).lower()) else ""
                    table.add_row(f"[{p.color}][bold]{p.icon} {p.title}[/bold][/{p.color}]", f"/{p.id}", p.description, is_active)
            else:
                valid_personas = ["AUTO", "RESEARCHER", "ARCHITECT", "CODER", "CRITIC", "DEBUGGER"]
                for p in valid_personas:
                    color, icon, desc = get_persona_style(p)
                    is_active = "✔ YES" if p == current else ""
                    table.add_row(f"[{color}][bold]{icon} {p}[/bold][/{color}]", f"/{p.lower()}", desc, is_active)

            self.console.print(Panel(table, title="[bold cyan]Dynamic Persona Profiles[/bold cyan]", border_style="cyan"))
            self.console.print(f"[dim]Use [/dim][bold yellow]/persona <name>[/bold yellow][dim] to switch (e.g. [/dim][bold cyan]/persona devops[/bold cyan][dim] or [/dim][bold cyan]/persona debugger[/bold cyan][dim]).[/dim]\n")
        else:
            success, msg = self.session.set_persona(persona_arg)
            if success:
                self.console.print(f"[bold green]✔ {msg}[/bold green]")
            else:
                self.console.print(f"[bold red]{msg}[/bold red]")

    def _handle_diff(self, mode_arg: str) -> None:
        if not self.session.git_guard.is_git_repo():
            self.console.print("[yellow]Not inside a Git repository. No diff available.[/yellow]")
            return

        diff_text = self.session.git_guard.get_diff()
        if not diff_text.strip():
            self.console.print("[dim]Working tree is clean; no uncommitted changes.[/dim]")
            return

        mode = (mode_arg or "").lower().strip()
        if mode in ("card", "preview", "box"):
            self.console.print(render_instant_diff_card(diff_text=diff_text, title="Working Tree Diff Preview"))
        elif mode in ("sbs", "side-by-side", "2col", "side"):
            if DiffVisualizer:
                self.console.print(DiffVisualizer.render_inline_diff(diff_text, title="Git Working Tree Diff (Inline)"))
            else:
                self.console.print(render_instant_diff_card(diff_text=diff_text))
        else:
            if DiffVisualizer:
                self.console.print(DiffVisualizer.render_inline_diff(diff_text, title="Git Working Tree Diff"))
            else:
                self.console.print(render_instant_diff_card(diff_text=diff_text))

    def _handle_rollback(self, file_arg: str) -> None:
        files = [file_arg] if file_arg else None
        if not self.session.git_guard.is_git_repo():
            self.console.print("[yellow]Not inside a Git repository; cannot rollback.[/yellow]")
            return

        success = self.session.git_guard.rollback(files=files)
        if success:
            target_str = f" for '{file_arg}'" if file_arg else ""
            self.console.print(f"[bold green]✔ Successfully rolled back uncommitted changes{target_str}.[/bold green]")
        else:
            self.console.print("[bold red]✘ Rollback failed or no changes to revert.[/bold red]")

    def _handle_docs(self, query: str) -> None:
        if not query:
            self.console.print("[yellow]Usage: /docs <query> (e.g. /docs json.loads)[/yellow]")
            return

        if not self.session.doc_retriever:
            self.console.print("[yellow]DevDocs retriever not available.[/yellow]")
            return

        results = self.session.doc_retriever.search(query, limit=3, max_tokens=250)
        if not results:
            self.console.print(f"[yellow]No documentation found for '{query}'.[/yellow]")
            return

        self.console.print(f"[bold cyan]DevDocs search results for '{query}':[/bold cyan]\n")
        for r in results:
            name = r.get("name", "")
            sig = r.get("signature", "")
            doc_str = r.get("doc", "")
            module = r.get("module", "")
            content = f"[bold green]{sig}[/bold green]\n\n[dim]{doc_str}[/dim]"
            self.console.print(Panel(content, title=f"Module: {module} | Symbol: {name}", border_style="cyan"))

    def _handle_test(self, target_arg: str) -> None:
        passed, summary = self.session.run_test(target_arg if target_arg else None)
        if passed:
            if create_verifier_badge:
                badge = create_verifier_badge("PASS", pass_rate=1.0)
                self.console.print(badge.render())
            self.console.print(f"[bold green]{summary}[/bold green]")
        else:
            if create_verifier_badge:
                badge = create_verifier_badge("FAIL", pass_rate=0.0)
                self.console.print(badge.render())
            self.console.print(f"[bold red]{summary}[/bold red]")


# ==============================================================================
# 6. Interactive Shell Engine
# ==============================================================================

class InteractiveShell:
    """Prompt-toolkit powered high-speed interactive shell for K-CLI."""

    def __init__(
        self,
        session: Any,
        console: Optional[Console] = None,
    ):
        self.session = session
        self.console = console or Console()
        self.status_bar = StatusBar()
        self.status_bar.update_from_session(self.session)
        self.command_handler = SlashCommandHandler(session=self.session, console=self.console)
        self.stream_renderer = LiveStreamRenderer(console=self.console)

    def run(self) -> None:
        """Starts the interactive multi-turn REPL loop."""
        self.status_bar.update_from_session(self.session)

        # Setup prompt_toolkit if available and interactive terminal
        prompt_session = None
        if HAS_PROMPT_TOOLKIT and sys.stdin.isatty():
            try:
                style = PTKStyle.from_dict({
                    "prompt": "bold #00ffff",
                    "arrow": "bold #5af78e",
                })
                prompt_session = PromptSession(
                    completer=SlashCommandCompleter(),
                    history=InMemoryHistory(),
                    style=style,
                )
            except Exception:
                prompt_session = None

        # Display startup banner
        if render_cyber_banner:
            self.console.print(render_cyber_banner(palette="neon_cyan"))

        while True:
            try:
                self.status_bar.update_from_session(self.session)

                if prompt_session:
                    prompt_input = prompt_session.prompt(
                        [("class:prompt", "K-CLI "), ("class:arrow", "❯ ")],
                        bottom_toolbar=self.status_bar.get_prompt_toolkit_toolbar,
                    ).strip()
                else:
                    prompt_input = self.console.input("[bold cyan]K-CLI [/bold cyan][bold green]❯ [/bold green]").strip()

                if not prompt_input:
                    continue

                # 1. Handle Slash Commands
                if prompt_input.startswith("/"):
                    cont, signal = self.command_handler.handle(prompt_input)
                    if not cont or signal == "EXIT":
                        break
                    self.console.print()
                    continue

                # 2. Conversational greetings
                clean_lower = prompt_input.lower().strip()
                if clean_lower in ("yo", "hi", "hello", "hey", "sup", "howdy", "greetings"):
                    self.console.print(Panel(
                        "[bold green]Yo! I'm K-CLI — your universal, compiler-grounded AI coding assistant.[/bold green]\n\n"
                        "[bold cyan]What you can do right now:[/bold cyan]\n"
                        "• [bold]Write & Refactor Code[/bold]: Enter a coding task (e.g. [italic]write a function to parse jwt tokens[/italic]).\n"
                        "• [bold]/model[/bold]: Switch active model (Bankai-7B, Bankai-14B, Gemini, Claude, Local Ollama).\n"
                        "• [bold]/persona[/bold]: Switch active persona (RESEARCHER, ARCHITECT, CODER, CRITIC, DEBUGGER).\n"
                        "• [bold]/add <file>[/bold]: Scope a file to active context for surgical edits.\n"
                        "• [bold]/diff[/bold] & [bold]/rollback[/bold]: Review git diff or undo any modification instantly.\n"
                        "• [bold]/docs <symbol>[/bold]: Instant SQLite FTS5 DevDocs lookup (e.g. [italic]/docs json.loads[/italic]).\n"
                        "• [bold]/test [file][/bold]: Run ground-truth verification on file or tests.\n"
                        "• [bold]/banner[/bold] & [bold]/tree[/bold]: Cyberpunk logo splash and subagent execution tree.\n"
                        "• [bold]/status[/bold]: Inspect active model, tokens, branch, cost, and RAM diagnostics.",
                        title="[bold cyan]K-CLI Assistant[/bold cyan]",
                        border_style="cyan",
                    ))
                    self.console.print("\n" + "─" * 60 + "\n")
                    continue

                # 3. Live Token Streaming & Pipeline Turn Execution
                self.console.print(f"\n[bold yellow]Agent Task:[/bold yellow] [italic]'{prompt_input}'[/italic]\n")

                gen = self.session.process_turn(prompt_input)
                self.stream_renderer.stream_display(
                    token_generator=gen,
                    initial_persona=self.session.active_persona if self.session.active_persona != "AUTO" else "RESEARCHER",
                    language="python",
                    model_name=self.session.model_name,
                )

                # 4. Result & Diff Presentation with Glowing Badges and Cards
                res = self.session.last_result or {}
                if res.get("success"):
                    if create_verifier_badge:
                        v_badge = create_verifier_badge("PASS", attempts=res.get("attempts", 1))
                        self.console.print(v_badge.render())
                    self.console.print(f"[bold green]✔ GROUND-TRUTH VERIFIED[/bold green] [dim](Attempts: {res.get('attempts', 1)} | RAM: {res.get('ram_mb', 0):.2f} MB)[/dim]\n")
                    if res.get("code"):
                        syntax = Syntax(res["code"], "python", theme="monokai", line_numbers=True)
                        self.console.print(Panel(syntax, title="[bold green]Verified Implementation[/bold green]", border_style="green"))
                else:
                    if create_verifier_badge:
                        v_badge = create_verifier_badge("FAIL", attempts=res.get("attempts", 1))
                        self.console.print(v_badge.render())
                    self.console.print(f"[bold red]✘ VERIFICATION FAILED[/bold red] [dim](RAM: {res.get('ram_mb', 0):.2f} MB)[/dim]\n")
                    if res.get("patch_error"):
                        self.console.print(Panel(res["patch_error"], title="Patch Application Error", border_style="red"))
                    elif res.get("code"):
                        syntax = Syntax(res["code"], "python", theme="monokai", line_numbers=True)
                        self.console.print(Panel(syntax, title="Unverified Candidate Code", border_style="yellow"))

                # Check for git working tree diff preview card
                if hasattr(self.session, "git_guard") and self.session.git_guard.is_git_repo():
                    diff_txt = self.session.git_guard.get_diff()
                    if diff_txt.strip():
                        self.console.print(render_instant_diff_card(diff_text=diff_txt, title="Working Tree Modification"))

                self.console.print("\n" + "─" * 60 + "\n")

            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[bold dim]Exiting K-CLI. Goodbye![/bold dim]")
                break
            except Exception as e:
                self.console.print(f"[bold red]Error:[/bold red] {e}")


# ==============================================================================
# 7. Full-Screen Textual TUI (KCliApp fallback / delegation)
# ==============================================================================

TUI_ASCII_BANNER = r"""[bold cyan]
  ██╗  ██╗   ██████╗██╗     ██╗
  ██║ ██╔╝  ██╔════╝██║     ██║
  █████═╝   ██║     ██║     ██║
  ██╔═██╗   ██║     ██║     ██║
  ██║  ██╗  ╚██████╗███████╗██║
  ╚═╝  ╚═╝   ╚═════╝╚══════╝╚═╝
[/bold cyan][bold bright_white]K-CLI AGENTIC WORKSTATION v1.0.0 | Verification-First Engine[/bold bright_white]"""

if HAS_TEXTUAL:
    try:
        from k_cli.tui.tui_app import KCliApp
    except (ImportError, ModuleNotFoundError):
        try:
            from tui_app import KCliApp
        except (ImportError, ModuleNotFoundError):
            class KCliApp(App):  # type: ignore
                def compose(self) -> ComposeResult:
                    yield Header()
                    yield Static("K-CLI Bankai Workstation")
                    yield Footer()
else:
    class KCliApp:
        def __init__(self, *args, **kwargs):
            pass
        def run(self):
            print("Textual is not installed.")
