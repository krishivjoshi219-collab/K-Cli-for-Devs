"""
tui_animations.py - Premium Cyberpunk & Neon Visual Experience Engine for K-CLI
Project Bankai Engine v1.0.0

Features:
1. Cyberpunk / Neon ASCII banners, logo splash with smooth multi-color gradient rendering.
2. Smooth animated spinners & loaders (Radar pulse, Quantum flux, Neon orbit, Cyber matrix cascade, Hex pulse).
3. Live Token Speedometer & Real-time Cost Ticker ($ USD calculation based on model token usage).
4. Dynamic Status Glow Badges (Git branch, Active Model, Verifier Status, MCP Server count, RAM RSS).
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text


# ==============================================================================
# 1. Cyberpunk Palettes & Gradient Color Interpolation Engine
# ==============================================================================

CYBER_PALETTES: Dict[str, List[str]] = {
    "neon_cyan": ["#00f0ff", "#00b4d8", "#7000ff", "#d946ef", "#ff007f"],
    "cyber_pink": ["#ff007f", "#ff0055", "#ff5500", "#ffe600"],
    "matrix_green": ["#5af78e", "#00ff41", "#00e676", "#00c853", "#008f11"],
    "quantum_purple": ["#b026ff", "#7000ff", "#00f0ff", "#ff007f"],
    "synthwave": ["#ff71ce", "#01cdfe", "#05ffa1", "#b967ff", "#fffb96"],
    "gold_amber": ["#ffe600", "#ffaa00", "#ff7700", "#ff3300"],
    "laser_blue": ["#00ffff", "#0080ff", "#0000ff", "#8000ff"],
    "blood_neon": ["#ff0055", "#ff3366", "#cc0033", "#990000"],
}


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converts hex string (#RRGGBB or RRGGBB) to (r, g, b) tuple."""
    clean = hex_str.lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return 0, 240, 255
    try:
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
        return r, g, b
    except ValueError:
        return 0, 240, 255


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Converts RGB integers (0-255) to hex string (#RRGGBB)."""
    r_clamped = max(0, min(255, int(r)))
    g_clamped = max(0, min(255, int(g)))
    b_clamped = max(0, min(255, int(b)))
    return f"#{r_clamped:02x}{g_clamped:02x}{b_clamped:02x}"


def interpolate_color(hex1: str, hex2: str, factor: float) -> str:
    """Linearly interpolates between two hex colors by factor (0.0 to 1.0)."""
    factor = max(0.0, min(1.0, factor))
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    r = r1 + (r2 - r1) * factor
    g = g1 + (g2 - g1) * factor
    b = b1 + (b2 - b1) * factor
    return rgb_to_hex(int(r), int(g), int(b))


def generate_gradient_colors(palette: Union[str, List[str]], steps: int) -> List[str]:
    """
    Generates a list of interpolated hex color codes of length `steps` across palette stops.
    """
    if steps <= 0:
        return []
    if isinstance(palette, str):
        colors = CYBER_PALETTES.get(palette, CYBER_PALETTES["neon_cyan"])
    else:
        colors = palette or CYBER_PALETTES["neon_cyan"]

    if len(colors) == 1 or steps == 1:
        return [colors[0]] * steps

    result: List[str] = []
    num_segments = len(colors) - 1
    steps_per_segment = steps / num_segments

    for i in range(steps):
        segment_idx = min(int(i / steps_per_segment), num_segments - 1)
        sub_factor = (i - segment_idx * steps_per_segment) / steps_per_segment
        c = interpolate_color(colors[segment_idx], colors[segment_idx + 1], sub_factor)
        result.append(c)

    return result


def apply_gradient_to_text(
    text: str,
    palette_name: str = "neon_cyan",
    direction: str = "horizontal",
    bold: bool = True,
) -> Text:
    """
    Applies a smooth multi-color cyberpunk gradient to input string using Rich Text.
    direction: 'horizontal', 'vertical', or 'diagonal'.
    """
    lines = text.split("\n")
    rich_text = Text()

    if direction == "vertical":
        colors = generate_gradient_colors(palette_name, max(1, len(lines)))
        for i, line in enumerate(lines):
            style = Style(color=colors[i], bold=bold)
            rich_text.append(line + ("\n" if i < len(lines) - 1 else ""), style=style)
        return rich_text

    # Horizontal or diagonal per character
    max_len = max(len(l) for l in lines) if lines else 1
    total_cols = max(1, max_len)

    for l_idx, line in enumerate(lines):
        if not line:
            if l_idx < len(lines) - 1:
                rich_text.append("\n")
            continue

        colors = generate_gradient_colors(
            palette_name,
            total_cols if direction == "horizontal" else (total_cols + len(lines)),
        )

        for c_idx, ch in enumerate(line):
            idx = c_idx if direction == "horizontal" else (c_idx + l_idx)
            color = colors[min(idx, len(colors) - 1)]
            rich_text.append(ch, style=Style(color=color, bold=bold))

        if l_idx < len(lines) - 1:
            rich_text.append("\n")

    return rich_text


# ==============================================================================
# 2. Cyberpunk ASCII Art Banners & Logo Splash
# ==============================================================================

CYBER_ASCII_BANNER_ART = r"""
██╗  ██╗   ██████╗██╗     ██╗
██║ ██╔╝  ██╔════╝██║     ██║
█████═╝   ██║     ██║     ██║
██╔═██╗   ██║     ██║     ██║
██║  ██╗  ╚██████╗███████╗██║
╚═╝  ╚═╝   ╚═════╝╚══════╝╚═╝
""".strip("\n")

CYBER_LOGO_COMPACT = r"""
 [ ⚡ K - C L I // P R O J E C T   B A N K A I ⚡ ]
"""

CYBER_ASCII_SUBAGENTS = r"""
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │ EXPLORE │ ──▶ │ REFACTOR│ ──▶ │ TEST &  │
   │  SWARM  │     │ ENGINE  │     │ VERIFY  │
   └─────────┘     └─────────┘     └─────────┘
""".strip("\n")


def render_cyber_banner(
    title: str = "K-CLI // AGENTIC WORKSTATION",
    subtitle: str = "Compiler Guard • Verification-First Architecture",
    palette: str = "neon_cyan",
    border_style: str = "#00f0ff",
    glitch_step: int = 0,
) -> Panel:
    """
    Renders a glowing, gradient-rendered Cyberpunk banner with active status headers.
    """
    art_text = CYBER_ASCII_BANNER_ART
    if glitch_step > 0:
        # Subtle glitch effect on glyphs
        glitch_chars = ["⚡", "◈", "◇", "█", "░", "▒"]
        art_lines = art_text.split("\n")
        mod_lines = []
        for line in art_lines:
            if line.strip():
                g_char = glitch_chars[glitch_step % len(glitch_chars)]
                mod_lines.append(line.replace("═", g_char).replace("╗", "╝" if glitch_step % 2 == 0 else "╗"))
            else:
                mod_lines.append(line)
        art_text = "\n".join(mod_lines)

    gradient_art = apply_gradient_to_text(art_text, palette_name=palette, direction="horizontal")

    # Build stylized subtitle and status line
    table = Table(box=None, expand=True, padding=(0, 0))
    table.add_column("Art", justify="center")
    table.add_row(gradient_art)
    table.add_row(Text(f"─── {title} ───", style="bold #00f0ff", justify="center"))
    table.add_row(Text(subtitle, style="dim white", justify="center"))

    return Panel(
        table,
        border_style=border_style,
        title="[bold #00f0ff]◈ K-CLI CYBER WORKSTATION ◈[/bold #00f0ff]",
        subtitle="[dim #7000ff]Bankai v1.0.0 • Online[/dim #7000ff]",
    )


def generate_splash_frames(steps: int = 8, palette: str = "neon_cyan") -> List[Panel]:
    """Generates animated splash frames for startup sequences or REPL transitions."""
    frames: List[Panel] = []
    palettes = list(CYBER_PALETTES.keys())
    for s in range(steps):
        cur_pal = palettes[s % len(palettes)] if palette == "rainbow" else palette
        frame = render_cyber_banner(
            title=f"K-CLI // SYSTEM BOOT [{s+1}/{steps}]",
            subtitle="Ground-Truth Compiler Verification Active",
            palette=cur_pal,
            glitch_step=s if s % 2 == 1 else 0,
        )
        frames.append(frame)
    return frames


# ==============================================================================
# 3. Smooth Animated Spinners & Cyber Loaders
# ==============================================================================

class SpinnerType(str, Enum):
    RADAR_PULSE = "radar_pulse"
    QUANTUM_FLUX = "quantum_flux"
    NEON_ORBIT = "neon_orbit"
    CYBER_MATRIX = "cyber_matrix"
    HEX_PULSE = "hex_pulse"
    SYNTH_BARS = "synth_bars"


SPINNER_GLYPH_SETS: Dict[SpinnerType, List[str]] = {
    SpinnerType.RADAR_PULSE: [
        "📡 ⠋ [SCANNING »»   ]",
        "📡 ⠙ [SCANNING »»»  ]",
        "📡 ⠹ [SCANNING  »»» ]",
        "📡 ⠸ [LOCKED   »»» ]",
        "📡 ⠼ [PULSE    •»» ]",
        "📡 ⠴ [SWEEP    ••» ]",
        "📡 ⠦ [RANGE    ••• ]",
        "📡 ⠧ [ECHO     »•• ]",
        "📡 ⠇ [PING     »»• ]",
        "📡 ⠏ [TARGET   »»» ]",
    ],
    SpinnerType.QUANTUM_FLUX: [
        "⟨ψ| ∿∿∿ |φ⟩",
        "⟨.ψ| ∾∾∾ |φ.⟩",
        "⟨..ψ| ⚡∿⚡ |φ..⟩",
        "⟨...ψ| ✧∾✦ |φ...⟩",
        "⟨....ψ| ░▒▓ |φ....⟩",
        "⟨...ψ| ▒▓█ |φ...⟩",
        "⟨..ψ| ▓██ |φ..⟩",
        "⟨.ψ| █▓▒ |φ.⟩",
    ],
    SpinnerType.NEON_ORBIT: [
        "🪐 ⠋ ✦ Orbit Alpha",
        "💫 ⠙ ✧ Orbit Beta",
        "✨ ⠚ ✦ Orbit Gamma",
        "🌟 ⠞ ✧ Orbit Delta",
        "⚡ ⠖ ✦ Flux Sync",
        "🔥 ⠦ ✧ Node Pulse",
        "💎 ⠴ ✦ Core Cycle",
        "🔮 ⠲ ✧ Energy Weave",
        "🌀 ⠳ ✦ Vortex Gate",
        "💠 ⠓ ✧ Matrix Mesh",
    ],
    SpinnerType.CYBER_MATRIX: [
        "1010110 ░ 010101",
        "0110101 ▒ 101010",
        "1101001 ▓ 010101",
        "0011110 █ 110011",
        "1010011 ▓ 001100",
        "0101100 ▒ 111001",
        "1110001 ░ 000111",
    ],
    SpinnerType.HEX_PULSE: [
        "⬡ ⬡ ⬡ [0x0000]",
        "⬢ ⬡ ⬡ [0x00F0]",
        "⬡ ⬢ ⬡ [0x0FF0]",
        "⬡ ⬡ ⬢ [0xFFFF]",
        "⬢ ⬢ ⬡ [0x7000]",
        "⬡ ⬢ ⬢ [0xB026]",
        "⬢ ⬢ ⬢ [0xBANK]",
    ],
    SpinnerType.SYNTH_BARS: [
        " ▃▄▅▆▇█ [FLUX 10%]",
        "▃▄▅▆▇█▇ [FLUX 35%]",
        "▄▅▆▇█▇▆ [FLUX 60%]",
        "▅▆▇█▇▆▅ [FLUX 85%]",
        "▆▇█▇▆▅▄ [FLUX 99%]",
        "▇█▇▆▅▄▃ [FLUX 100%]",
        "█▇▆▅▄▃  [FLUX SYNC]",
    ],
}


class AnimatedSpinner:
    """
    Rich-compatible Cyberpunk animated spinner with custom neon glyph sets,
    pulsating color cycles, and frame generator methods.
    """

    def __init__(
        self,
        spinner_type: Union[SpinnerType, str] = SpinnerType.RADAR_PULSE,
        label: str = "Processing...",
        palette: str = "neon_cyan",
    ):
        if isinstance(spinner_type, str):
            try:
                self.spinner_type = SpinnerType(spinner_type)
            except ValueError:
                self.spinner_type = SpinnerType.RADAR_PULSE
        else:
            self.spinner_type = spinner_type

        self.label = label
        self.palette = palette
        self.frames = SPINNER_GLYPH_SETS.get(self.spinner_type, SPINNER_GLYPH_SETS[SpinnerType.RADAR_PULSE])

    def get_frame(self, step: int) -> Text:
        """Returns stylized Text for the frame at given step index."""
        raw_glyph = self.frames[step % len(self.frames)]
        colors = generate_gradient_colors(self.palette, max(1, len(self.frames)))
        color = colors[step % len(colors)]

        text = Text()
        text.append(raw_glyph, style=Style(color=color, bold=True))
        text.append(f" {self.label}", style=Style(color="#e2e8f0", bold=False))
        return text

    def get_all_frames(self) -> List[str]:
        """Returns raw glyph frames."""
        return list(self.frames)

    def render(self, step: int) -> Text:
        """Alias for get_frame to allow direct Rich rendering."""
        return self.get_frame(step)


# ==============================================================================
# 4. Live Token Speedometer & Real-Time Cost Ticker ($ USD)
# ==============================================================================

# Pricing Catalog: (prompt_price_per_1m, completion_price_per_1m) in USD
MODEL_PRICING_CATALOG: Dict[str, Tuple[float, float]] = {
    # Project Bankai Local SLMs & GGUF (100% Free / Local Compute)
    "bankai-7b": (0.00, 0.00),
    "bankai-14b": (0.00, 0.00),
    "qwen2.5-coder:1.5b": (0.00, 0.00),
    "qwen2.5-coder:7b": (0.00, 0.00),
    "qwen2.5-coder:14b": (0.00, 0.00),
    "local ollama": (0.00, 0.00),
    "ollama": (0.00, 0.00),
    # Cloud Models
    "gemini": (0.075, 0.30),
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-2.0-pro": (1.25, 5.00),
    "claude": (3.00, 15.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def calculate_token_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculates USD cost for a given model and token usage.
    Returns $0.00 for local SLMs/GGUFs.
    """
    m_clean = (model_name or "bankai-7b").lower().strip()
    prompt_rate, compl_rate = (0.00, 0.00)

    for key, rates in MODEL_PRICING_CATALOG.items():
        if key in m_clean or m_clean in key:
            prompt_rate, compl_rate = rates
            break

    cost = (prompt_tokens / 1_000_000.0) * prompt_rate + (completion_tokens / 1_000_000.0) * compl_rate
    return round(cost, 6)


class TokenSpeedometer:
    """
    Real-time Token Throughput Speedometer.
    Tracks instantaneous tok/s, peak speed, rolling average, and renders visual RPM gauge.
    """

    def __init__(self, target_max_speed: float = 200.0):
        self.target_max_speed = max(10.0, target_max_speed)
        self.token_history: List[Tuple[float, int]] = []  # (timestamp, delta_tokens)
        self.total_tokens: int = 0
        self.peak_speed: float = 0.0
        self.start_time: float = time.time()
        self.last_update_time: float = self.start_time

    def record_tokens(self, count: int) -> None:
        """Records addition of generated tokens at current timestamp."""
        now = time.time()
        self.token_history.append((now, count))
        self.total_tokens += count
        self.last_update_time = now

        # Prune history older than 5.0 seconds for rolling speed
        cutoff = now - 5.0
        self.token_history = [item for item in self.token_history if item[0] >= cutoff]

        # Calculate current rolling speed and update peak
        speed = self.get_current_speed()
        if speed > self.peak_speed:
            self.peak_speed = speed

    def get_current_speed(self) -> float:
        """Calculates rolling tokens per second over recent window."""
        if not self.token_history:
            return 0.0
        now = time.time()
        window_start = self.token_history[0][0]
        duration = max(0.05, now - window_start)
        recent_tokens = sum(cnt for _, cnt in self.token_history)
        return round(recent_tokens / duration, 1)

    def get_average_speed(self) -> float:
        """Calculates cumulative average tokens per second since inception."""
        total_time = max(0.05, time.time() - self.start_time)
        return round(self.total_tokens / total_time, 1)

    def render_gauge(self, width: int = 16, style: str = "neon") -> Text:
        """
        Renders a cyber speedometer visual gauge bar with speed readout.
        """
        speed = self.get_current_speed()
        pct = min(1.0, speed / self.target_max_speed)
        filled_bars = int(pct * width)
        empty_bars = width - filled_bars

        # Dynamic speed color tiers
        if speed < 30.0:
            bar_color = "#00f0ff"
        elif speed < 80.0:
            bar_color = "#5af78e"
        elif speed < 140.0:
            bar_color = "#ffe600"
        else:
            bar_color = "#ff007f"

        gauge = Text()
        gauge.append("⚡ ", style="bold #ffe600")
        gauge.append(f"{speed:5.1f} tok/s ", style=f"bold {bar_color}")
        gauge.append("[", style="dim white")
        gauge.append("█" * filled_bars, style=f"bold {bar_color}")
        gauge.append("░" * empty_bars, style="dim #1e293b")
        gauge.append("]", style="dim white")
        gauge.append(f" (peak: {self.peak_speed:.0f})", style="dim #94a3b8")
        return gauge


class CostTicker:
    """
    Real-time USD Cost Ticker tracking cumulative session spending by model.
    """

    def __init__(self, active_model: str = "Bankai-7B"):
        self.active_model = active_model
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.model_breakdown: Dict[str, Tuple[int, int]] = {}

    def record_usage(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Records token usage for a model."""
        self.active_model = model_name
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        prev_p, prev_c = self.model_breakdown.get(model_name, (0, 0))
        self.model_breakdown[model_name] = (prev_p + prompt_tokens, prev_c + completion_tokens)

    @property
    def total_cost(self) -> float:
        """Calculates total cumulative USD cost across all recorded models."""
        total = 0.0
        for m_name, (p_cnt, c_cnt) in self.model_breakdown.items():
            total += calculate_token_cost(m_name, p_cnt, c_cnt)
        return round(total, 6)

    def render_ticker(self, compact: bool = False) -> Text:
        """
        Renders glowing USD cost ticker text.
        """
        cost = self.total_cost
        tot_tokens = self.total_prompt_tokens + self.total_completion_tokens
        is_free = (cost == 0.0)

        ticker = Text()
        ticker.append("💰 ", style="bold #ffe600")

        if is_free:
            ticker.append("$0.00 USD (LOCAL FREE)", style="bold #5af78e")
        else:
            ticker.append(f"${cost:.5f} USD", style="bold #00f0ff")

        if not compact:
            ticker.append(f" │ 📊 {tot_tokens:,} tokens", style="dim white")
            ticker.append(f" │ 🤖 {self.active_model}", style="dim #94a3b8")

        return ticker


# ==============================================================================
# 5. Dynamic Status Glow Badges
# ==============================================================================

class GlowBadgeStatus(str, Enum):
    ONLINE = "online"
    ACTIVE = "active"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    IDLE = "idle"
    INFO = "info"


STATUS_COLORS: Dict[GlowBadgeStatus, Tuple[str, str, str]] = {
    # (fg_color, bg_color, border_color)
    GlowBadgeStatus.ONLINE: ("#00ff88", "#082d1c", "#00ff88"),
    GlowBadgeStatus.ACTIVE: ("#00f0ff", "#092336", "#00f0ff"),
    GlowBadgeStatus.SUCCESS: ("#5af78e", "#0a2612", "#5af78e"),
    GlowBadgeStatus.WARNING: ("#ffe600", "#332b00", "#ffe600"),
    GlowBadgeStatus.ERROR: ("#ff3366", "#360914", "#ff3366"),
    GlowBadgeStatus.IDLE: ("#94a3b8", "#121a29", "#1e293b"),
    GlowBadgeStatus.INFO: ("#b026ff", "#220d36", "#b026ff"),
}


@dataclass
class StatusGlowBadge:
    """
    Dynamic neon glow badge representation for terminal HUDs and Textual headers.
    """
    label: str
    value: str
    status: GlowBadgeStatus = GlowBadgeStatus.ACTIVE
    icon: str = ""
    glow_color: Optional[str] = None

    def render(self) -> Text:
        """Renders stylized Rich Text badge with neon border brackets."""
        fg, bg, default_glow = STATUS_COLORS.get(self.status, STATUS_COLORS[GlowBadgeStatus.ACTIVE])
        color = self.glow_color or fg

        badge = Text()
        badge.append("[", style="dim #1e293b")
        if self.icon:
            badge.append(f"{self.icon} ", style=f"bold {color}")
        badge.append(f"{self.label}: ", style="dim white")
        badge.append(f"{self.value}", style=f"bold {color}")
        badge.append("]", style="dim #1e293b")
        return badge

    def render_as_tag(self) -> str:
        """Returns string with Rich markup tags."""
        fg, _, _ = STATUS_COLORS.get(self.status, STATUS_COLORS[GlowBadgeStatus.ACTIVE])
        color = self.glow_color or fg
        icon_str = f"{self.icon} " if self.icon else ""
        return f"[{color}][bold]{icon_str}{self.label}: {self.value}[/bold][/{color}]"


def create_branch_badge(branch_name: str = "main", is_dirty: bool = False) -> StatusGlowBadge:
    """Creates a Git Branch glow badge."""
    val = f"{branch_name}{'*' if is_dirty else ''}"
    stat = GlowBadgeStatus.WARNING if is_dirty else GlowBadgeStatus.ONLINE
    return StatusGlowBadge(label="Git", value=val, status=stat, icon="🌿")


def create_model_badge(model_name: str = "Bankai-7B", is_active: bool = True) -> StatusGlowBadge:
    """Creates an Active Model glow badge."""
    stat = GlowBadgeStatus.ACTIVE if is_active else GlowBadgeStatus.IDLE
    return StatusGlowBadge(label="Model", value=model_name, status=stat, icon="🤖")


def create_verifier_badge(
    status: str = "PASS",
    pass_rate: float = 1.0,
    attempts: int = 1,
) -> StatusGlowBadge:
    """Creates an AST/Compiler Verifier Status glow badge."""
    if status.upper() in ("PASS", "VERIFIED", "OK"):
        stat = GlowBadgeStatus.SUCCESS
        icon = "🛡️"
        val = f"VERIFIED ({int(pass_rate*100)}%)"
    elif status.upper() in ("WARN", "RETRYING"):
        stat = GlowBadgeStatus.WARNING
        icon = "⚠️"
        val = f"RETRY ({attempts})"
    else:
        stat = GlowBadgeStatus.ERROR
        icon = "✘"
        val = f"FAILED ({attempts})"

    return StatusGlowBadge(label="Verifier", value=val, status=stat, icon=icon)


def create_mcp_badge(server_count: int = 0, active_tools: int = 0) -> StatusGlowBadge:
    """Creates an MCP Server count and tool availability glow badge."""
    stat = GlowBadgeStatus.INFO if server_count > 0 else GlowBadgeStatus.IDLE
    val = f"{server_count} svr ({active_tools} tools)" if active_tools > 0 else f"{server_count} svr"
    return StatusGlowBadge(label="MCP", value=val, status=stat, icon="🔌")


def create_ram_badge(ram_mb: float = 0.0, max_ram_mb: float = 1024.0) -> StatusGlowBadge:
    """Creates a RAM Allocation RSS glow badge with budget threshold colors."""
    pct = (ram_mb / max_ram_mb) * 100 if max_ram_mb > 0 else 0.0
    if pct > 90.0:
        stat = GlowBadgeStatus.ERROR
    elif pct > 70.0:
        stat = GlowBadgeStatus.WARNING
    else:
        stat = GlowBadgeStatus.ONLINE

    val = f"{ram_mb:.1f}MB ({pct:.0f}%)"
    return StatusGlowBadge(label="RAM", value=val, status=stat, icon="💾")


def render_hud_status_bar(badges: List[StatusGlowBadge]) -> Text:
    """Combines multiple glow badges into a continuous horizontal HUD status bar."""
    bar = Text()
    for i, b in enumerate(badges):
        bar.append_text(b.render())
        if i < len(badges) - 1:
            bar.append("  ")
    return bar
