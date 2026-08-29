"""
test_tui.py - Comprehensive Unit and Integration Tests for K-CLI Modern TUI Layer

Tests:
1. LiveStreamRenderer live token streaming and syntax highlighting.
2. StatusBar model presets, git branch tracking, active persona, and toolbar formatting.
3. SlashCommandHandler interactive commands (/model, /persona, /diff, /rollback, /help, /docs, /clear, /test).
4. DiffVisualizer inline diff, side-by-side 2-column diff, and surgical patch preview.
5. SlashCommandCompleter auto-completions and metadata.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.panel import Panel

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from k_cli.tui.diff_viewer import DiffVisualizer
from k_cli.tui.tui import (
    StatusBar,
    LiveStreamRenderer,
    SlashCommandHandler,
    MODEL_PRESETS,
    get_persona_style,
)
from k_cli.core.session import SessionManager

try:
    from tui import SlashCommandCompleter
    from prompt_toolkit.document import Document
    HAS_PTK = True
except ImportError:
    HAS_PTK = False


# ==============================================================================
# 1. StatusBar Tests
# ==============================================================================

def test_status_bar_initialization():
    """Verify StatusBar default properties and models."""
    sb = StatusBar(
        active_model="Bankai-7B",
        git_branch="main",
        active_persona="CODER",
        ram_mb=45.2,
        max_ram_mb=1024.0,
        token_count=150,
        max_tokens=4096,
    )
    assert sb.active_model == "Bankai-7B"
    assert sb.git_branch == "main"
    assert sb.active_persona == "CODER"
    assert sb.ram_mb == 45.2

    # Render rich panel
    panel = sb.render_rich_panel()
    assert isinstance(panel, Panel)


def test_status_bar_update_from_session(tmp_path: Path):
    """Verify StatusBar syncing state from SessionManager."""
    session = SessionManager(workspace_dir=str(tmp_path), model_name="Bankai-14B", mock_mode=True)
    session.active_persona = "ARCHITECT"

    sb = StatusBar()
    sb.update_from_session(session)
    assert sb.active_model == "Bankai-14B"
    assert sb.active_persona == "ARCHITECT"


def test_status_bar_prompt_toolkit_toolbar():
    """Verify StatusBar formatted toolbar text."""
    sb = StatusBar(
        active_model="Gemini",
        git_branch="feat/tui",
        active_persona="DEBUGGER",
        ram_mb=82.0,
    )
    html = sb.get_prompt_toolkit_toolbar()
    assert "Gemini" in html.value
    assert "feat/tui" in html.value
    assert "DEBUGGER" in html.value


def test_get_persona_style():
    """Verify get_persona_style maps personas to distinctive colors and icons."""
    color, icon, desc = get_persona_style("RESEARCHER")
    assert color == "cyan"
    assert "🔍" in icon

    color, icon, desc = get_persona_style("ARCHITECT")
    assert color == "magenta"
    assert "📐" in icon

    color, icon, desc = get_persona_style("CODER")
    assert color == "green"
    assert "⚡" in icon

    color, icon, desc = get_persona_style("CRITIC")
    assert color == "yellow"
    assert "🛡️" in icon

    color, icon, desc = get_persona_style("DEBUGGER")
    assert color == "red"
    assert "🔧" in icon


# ==============================================================================
# 2. DiffVisualizer Tests (Inline and Side-by-Side)
# ==============================================================================

def test_diff_visualizer_inline_diff():
    """Verify inline diff visualization with additions, deletions, and hunks."""
    diff_sample = (
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    # Fix addition\n"
        "+    return a + b\n"
    )
    panel = DiffVisualizer.render_inline_diff(diff_sample, title="Test Inline Diff")
    assert isinstance(panel, Panel)


def test_diff_visualizer_inline_diff_empty():
    """Verify inline diff handling of empty diff string."""
    panel = DiffVisualizer.render_inline_diff("", title="Clean Diff")
    assert isinstance(panel, Panel)


def test_diff_visualizer_side_by_side():
    """Verify side-by-side 2-column diff rendering."""
    old_code = "def solve():\n    return False\n"
    new_code = "def solve():\n    # optimized\n    return True\n"

    panel = DiffVisualizer.render_side_by_side(
        old_code=old_code,
        new_code=new_code,
        old_title="Original",
        new_title="Repaired",
    )
    assert isinstance(panel, Panel)


def test_diff_visualizer_surgical_patch_preview():
    """Verify surgical SEARCH/REPLACE block preview."""
    search_b = "def broken():\n    x = None\n    return x.val\n"
    replace_b = "def broken():\n    x = {'val': 42}\n    return x['val']\n"

    panel = DiffVisualizer.render_surgical_patch_preview(
        search_block=search_b,
        replace_block=replace_b,
        file_path="service.py",
    )
    assert isinstance(panel, Panel)


# ==============================================================================
# 3. LiveStreamRenderer Tests
# ==============================================================================

def test_live_stream_renderer_text_and_code():
    """Verify LiveStreamRenderer displays streaming tokens smoothly."""
    console = Console(record=True)
    renderer = LiveStreamRenderer(console=console)

    def mock_generator():
        yield "```python\n"
        yield "def hello():\n"
        yield "    return 'world'\n"
        yield "```\n"

    res = renderer.stream_display(
        token_generator=mock_generator(),
        initial_persona="CODER",
        language="python",
    )
    assert res["total_tokens"] == 4
    assert "def hello" in res["final_text"]


# ==============================================================================
# 4. SlashCommandHandler Tests (/model, /persona, /diff, /rollback, /help, /docs, /clear, /test)
# ==============================================================================

def test_slash_command_handler_help(tmp_path: Path):
    """Verify /help renders command table."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)
    cont, sig = handler.handle("/help")
    assert cont is True
    assert sig == "HELP_RENDERED"


def test_slash_command_handler_model_listing_and_switching(tmp_path: Path):
    """Verify /model command displays available models and switches active model."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    # 1. Listing models
    cont, sig = handler.handle("/model")
    assert cont is True
    assert sig == "MODEL_HANDLED"

    # 2. Switching model to Bankai-14B
    cont, sig = handler.handle("/model Bankai-14B")
    assert cont is True
    assert session.model_name == "Bankai-14B"

    # 3. Switching model to Claude
    cont, sig = handler.handle("/model Claude")
    assert cont is True
    assert session.model_name == "Claude"


def test_slash_command_handler_persona_listing_and_switching(tmp_path: Path):
    """Verify /persona command displays personas and switches active persona."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    # 1. Listing personas
    cont, sig = handler.handle("/persona")
    assert cont is True
    assert sig == "PERSONA_HANDLED"

    # 2. Switching persona to ARCHITECT
    cont, sig = handler.handle("/persona ARCHITECT")
    assert cont is True
    assert "ARCHITECT" in str(session.active_persona).upper()

    # 3. Switching persona to CODER
    cont, sig = handler.handle("/persona CODER")
    assert cont is True
    assert session.active_persona == "CODER"


def test_slash_command_handler_diff(tmp_path: Path):
    """Verify /diff command handles clean and modified repos."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/diff")
    assert cont is True
    assert sig == "DIFF_HANDLED"


def test_slash_command_handler_rollback(tmp_path: Path):
    """Verify /rollback command invokes rollback."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/rollback")
    assert cont is True
    assert sig == "ROLLBACK_HANDLED"


def test_slash_command_handler_docs(tmp_path: Path):
    """Verify /docs and /doc search offline DevDocs."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/docs json.dumps")
    assert cont is True
    assert sig == "DOCS_HANDLED"


def test_slash_command_handler_clear(tmp_path: Path):
    """Verify /clear resets context and history."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    session.history.append({"prompt": "test", "response": "resp"})
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/clear")
    assert cont is True
    assert sig == "CLEARED"
    assert len(session.history) == 0


def test_slash_command_handler_test(tmp_path: Path):
    """Verify /test runs ground-truth verifier."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/test def valid(): return 42")
    assert cont is True
    assert sig == "TEST_HANDLED"


def test_slash_command_handler_exit(tmp_path: Path):
    """Verify /exit returns False and EXIT signal."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handler = SlashCommandHandler(session=session)

    cont, sig = handler.handle("/exit")
    assert cont is False
    assert sig == "EXIT"


# ==============================================================================
# 5. SlashCommandCompleter Tests
# ==============================================================================

@pytest.mark.skipif(not HAS_PTK, reason="prompt_toolkit is required for completer tests")
def test_slash_command_completer():
    """Verify autocompletion of slash commands and arguments."""
    completer = SlashCommandCompleter()

    # Complete command names
    doc = Document("/mo")
    completions = list(completer.get_completions(doc, None))
    assert any(c.text == "/model" for c in completions)

    # Complete subcommands / options
    doc = Document("/model Ba")
    completions = list(completer.get_completions(doc, None))
    assert any("Bankai" in c.text for c in completions)

    doc = Document("/persona CO")
    completions = list(completer.get_completions(doc, None))
    assert any(c.text == "CODER" for c in completions)
