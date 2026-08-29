"""
test_tui_animations.py - Unit & Integration Test Suite for K-CLI Cyber-TUI & Visual Experience
Project Bankai Engine v1.0.0

Tests:
1. Cyberpunk color palettes, hex/rgb conversions, and gradient text interpolation.
2. Animated Cyberpunk ASCII banners, logo splashes, and glitch rendering.
3. Smooth animated spinners (Radar pulse, Quantum flux, Neon orbit, Cyber matrix, Hex pulse, Synth bars).
4. Live Token Speedometer (tok/s, peak speed, gauge rendering) & Real-time Cost Ticker ($ USD calculations).
5. Dynamic Status Glow Badges (Branch, Model, Verifier, MCP Servers, RAM RSS).
6. Instant diff preview cards and Subagent execution tree visualization.
"""

import math
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from k_cli.tui.tui_animations import (
    CYBER_PALETTES,
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
    generate_gradient_colors,
    generate_splash_frames,
    hex_to_rgb,
    interpolate_color,
    render_cyber_banner,
    render_hud_status_bar,
    rgb_to_hex,
)
from k_cli.tui.tui import (
    render_instant_diff_card,
    render_subagent_execution_tree,
    StatusBar,
    LiveStreamRenderer,
)


# ==============================================================================
# 1. Cyberpunk Color Palettes & Gradient Interpolation Tests
# ==============================================================================

def test_hex_to_rgb_conversions():
    """Verify hex string to RGB tuple conversions including 3-char and error fallbacks."""
    assert hex_to_rgb("#00f0ff") == (0, 240, 255)
    assert hex_to_rgb("00f0ff") == (0, 240, 255)
    assert hex_to_rgb("#fff") == (255, 255, 255)
    assert hex_to_rgb("#000") == (0, 0, 0)
    # Fallback on invalid format
    assert hex_to_rgb("invalid") == (0, 240, 255)


def test_rgb_to_hex_conversions():
    """Verify RGB tuple to hex string formatting and clamping."""
    assert rgb_to_hex(0, 240, 255) == "#00f0ff"
    assert rgb_to_hex(255, 0, 127) == "#ff007f"
    # Clamping test
    assert rgb_to_hex(-10, 300, 128) == "#00ff80"


def test_interpolate_color():
    """Verify linear color interpolation across color stops."""
    c_start = "#000000"
    c_end = "#ffffff"
    mid = interpolate_color(c_start, c_end, 0.5)
    r, g, b = hex_to_rgb(mid)
    assert 126 <= r <= 128
    assert 126 <= g <= 128
    assert 126 <= b <= 128

    # Edge cases
    assert interpolate_color(c_start, c_end, 0.0) == "#000000"
    assert interpolate_color(c_start, c_end, 1.0) == "#ffffff"


def test_generate_gradient_colors():
    """Verify gradient steps generation across standard palettes."""
    steps = generate_gradient_colors("neon_cyan", 10)
    assert len(steps) == 10
    assert steps[0].startswith("#")
    assert steps[-1].startswith("#")

    # Custom palette list
    custom = ["#ff0000", "#00ff00", "#0000ff"]
    c_steps = generate_gradient_colors(custom, 5)
    assert len(c_steps) == 5

    # Boundary tests
    assert generate_gradient_colors("neon_cyan", 0) == []
    assert len(generate_gradient_colors("neon_cyan", 1)) == 1


def test_apply_gradient_to_text():
    """Verify gradient application to single and multi-line strings."""
    sample = "K-CLI CYBER WORKSTATION\nPROJECT BANKAI ENGINE"

    # Horizontal
    h_text = apply_gradient_to_text(sample, palette_name="neon_cyan", direction="horizontal")
    assert isinstance(h_text, Text)
    assert "K-CLI" in h_text.plain

    # Vertical
    v_text = apply_gradient_to_text(sample, palette_name="matrix_green", direction="vertical")
    assert isinstance(v_text, Text)
    assert "PROJECT" in v_text.plain

    # Diagonal
    d_text = apply_gradient_to_text(sample, palette_name="cyber_pink", direction="diagonal")
    assert isinstance(d_text, Text)


# ==============================================================================
# 2. Cyberpunk ASCII Banners & Splash Frames
# ==============================================================================

def test_render_cyber_banner():
    """Verify rendering of cyber ASCII banners."""
    panel = render_cyber_banner(
        title="TEST ENGINE",
        subtitle="Verification Guard Active",
        palette="neon_cyan",
    )
    assert isinstance(panel, Panel)
    assert "K-CLI CYBER WORKSTATION" in str(panel.title)

    # Glitch step test
    glitch_panel = render_cyber_banner(glitch_step=3)
    assert isinstance(glitch_panel, Panel)


def test_generate_splash_frames():
    """Verify splash animation frame generation."""
    frames = generate_splash_frames(steps=6, palette="neon_cyan")
    assert len(frames) == 6
    for f in frames:
        assert isinstance(f, Panel)


# ==============================================================================
# 3. Smooth Animated Spinners & Loaders
# ==============================================================================

def test_animated_spinner_types_and_frames():
    """Verify spinner creation, frame retrieval, and Rich rendering."""
    spinner_types = [
        SpinnerType.RADAR_PULSE,
        SpinnerType.QUANTUM_FLUX,
        SpinnerType.NEON_ORBIT,
        SpinnerType.CYBER_MATRIX,
        SpinnerType.HEX_PULSE,
        SpinnerType.SYNTH_BARS,
    ]

    for st in spinner_types:
        spinner = AnimatedSpinner(spinner_type=st, label="Synthesizing...")
        assert len(spinner.get_all_frames()) > 0

        # Test frame rendering at different steps
        frame0 = spinner.get_frame(0)
        assert isinstance(frame0, Text)
        assert "Synthesizing..." in frame0.plain

        frame5 = spinner.render(5)
        assert isinstance(frame5, Text)


def test_animated_spinner_string_fallback():
    """Verify AnimatedSpinner handles string types gracefully."""
    spinner = AnimatedSpinner(spinner_type="quantum_flux")
    assert spinner.spinner_type == SpinnerType.QUANTUM_FLUX

    unknown_spinner = AnimatedSpinner(spinner_type="non_existent_spinner")
    assert unknown_spinner.spinner_type == SpinnerType.RADAR_PULSE


# ==============================================================================
# 4. Live Token Speedometer & Real-time Cost Ticker
# ==============================================================================

def test_calculate_token_cost():
    """Verify USD cost calculation across local and cloud models."""
    # Local Bankai SLMs are 100% Free
    assert calculate_token_cost("Bankai-7B", 1000, 500) == 0.0
    assert calculate_token_cost("Bankai-14B", 2500, 1000) == 0.0
    assert calculate_token_cost("qwen2.5-coder:1.5b", 5000, 2000) == 0.0
    assert calculate_token_cost("Local Ollama", 1000, 1000) == 0.0

    # Claude 3.5 Sonnet: $3.00/1M input, $15.00/1M output
    cost_claude = calculate_token_cost("Claude", 1_000_000, 1_000_000)
    assert math.isclose(cost_claude, 18.0, rel_tol=1e-3)

    # Gemini Flash: $0.075/1M input, $0.30/1M output
    cost_gemini = calculate_token_cost("gemini-2.0-flash", 1_000_000, 1_000_000)
    assert math.isclose(cost_gemini, 0.375, rel_tol=1e-3)


def test_token_speedometer():
    """Verify TokenSpeedometer rolling speed, peak, and gauge rendering."""
    speedometer = TokenSpeedometer(target_max_speed=150.0)

    # Initial speed
    assert speedometer.get_current_speed() == 0.0

    # Record token bursts
    speedometer.record_tokens(50)
    speedometer.record_tokens(75)

    speed = speedometer.get_current_speed()
    assert speed > 0.0
    assert speedometer.peak_speed >= speed

    # Render gauge
    gauge = speedometer.render_gauge(width=20)
    assert isinstance(gauge, Text)
    assert "tok/s" in gauge.plain
    assert "peak:" in gauge.plain


def test_cost_ticker():
    """Verify CostTicker token accumulation, USD accounting, and rendering."""
    ticker = CostTicker(active_model="Bankai-7B")

    # Local usage: $0.00
    ticker.record_usage("Bankai-7B", prompt_tokens=500, completion_tokens=300)
    assert ticker.total_cost == 0.0
    rendered_free = ticker.render_ticker()
    assert "LOCAL FREE" in rendered_free.plain or "$0.00" in rendered_free.plain

    # Cloud usage: Claude
    ticker.record_usage("Claude", prompt_tokens=100_000, completion_tokens=50_000)
    assert ticker.total_cost > 0.0
    rendered_cloud = ticker.render_ticker()
    assert "USD" in rendered_cloud.plain


# ==============================================================================
# 5. Dynamic Status Glow Badges
# ==============================================================================

def test_status_glow_badges():
    """Verify individual and combined HUD status glow badge creation."""
    # Branch badge
    b_clean = create_branch_badge("main", is_dirty=False)
    assert b_clean.status == GlowBadgeStatus.ONLINE
    assert "main" in b_clean.value

    b_dirty = create_branch_badge("feature/tui", is_dirty=True)
    assert b_dirty.status == GlowBadgeStatus.WARNING
    assert "*" in b_dirty.value

    # Model badge
    m_badge = create_model_badge("Bankai-14B", is_active=True)
    assert m_badge.status == GlowBadgeStatus.ACTIVE
    assert "Bankai-14B" in m_badge.value

    # Verifier badge
    v_pass = create_verifier_badge("PASS", pass_rate=1.0, attempts=1)
    assert v_pass.status == GlowBadgeStatus.SUCCESS
    assert "VERIFIED" in v_pass.value

    v_fail = create_verifier_badge("FAIL", attempts=2)
    assert v_fail.status == GlowBadgeStatus.ERROR
    assert "FAILED" in v_fail.value

    # MCP badge
    mcp_badge = create_mcp_badge(server_count=4, active_tools=12)
    assert mcp_badge.status == GlowBadgeStatus.INFO
    assert "4 svr" in mcp_badge.value

    # RAM badge
    ram_ok = create_ram_badge(ram_mb=120.0, max_ram_mb=1024.0)
    assert ram_ok.status == GlowBadgeStatus.ONLINE

    ram_high = create_ram_badge(ram_mb=950.0, max_ram_mb=1024.0)
    assert ram_high.status == GlowBadgeStatus.ERROR

    # Combined HUD
    hud = render_hud_status_bar([b_clean, m_badge, v_pass, mcp_badge, ram_ok])
    assert isinstance(hud, Text)
    assert "Git" in hud.plain
    assert "Model" in hud.plain
    assert "Verifier" in hud.plain


# ==============================================================================
# 6. Instant Diff Card & Subagent Tree Visualizations
# ==============================================================================

def test_render_instant_diff_card():
    """Verify rendering of instant surgical diff preview cards."""
    diff_sample = (
        "--- a/service.py\n"
        "+++ b/service.py\n"
        "@@ -10,3 +10,4 @@\n"
        " def execute():\n"
        "-    return False\n"
        "+    # Fix verification\n"
        "+    return True\n"
    )

    card = render_instant_diff_card(diff_text=diff_sample, file_path="service.py")
    assert isinstance(card, Panel)
    assert "Instant Surgical Diff Card" in str(card.title)

    # Empty diff
    empty_card = render_instant_diff_card(diff_text="")
    assert isinstance(empty_card, Panel)


def test_render_subagent_execution_tree():
    """Verify rendering of hierarchical subagent execution trees."""
    class DummyTask:
        def __init__(self, name, role, status, prompt, duration_sec=1.5, token_count=210):
            self.name = name
            self.role = role
            self.status = status
            self.prompt = prompt
            self.duration_sec = duration_sec
            self.token_count = token_count

    tasks = [
        DummyTask("Scan AST symbols", "EXPLORER", "COMPLETED", "Scanned 12 files"),
        DummyTask("DevDocs Lookup", "RESEARCHER", "COMPLETED", "Searched json.loads"),
        DummyTask("Synthesize Refactor", "REFACTORER", "RUNNING", "Generating patches"),
        DummyTask("Run Pytest Guard", "TESTER", "PENDING", "Compiler verification"),
    ]

    panel = render_subagent_execution_tree(tasks)
    assert isinstance(panel, Panel)
    assert "SWARM RADAR & EXECUTION TOPOLOGY" in str(panel.title)
