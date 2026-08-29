"""
diff_viewer.py - Surgical and Unified Diff Visualizer for K-CLI

Provides high-speed, modern terminal diff visualizers using Rich:
- Side-by-Side (2-column) diff visualizer with synchronized line numbers and change highlights.
- Inline unified diff visualizer with colored additions/deletions and hunk header markers.
- Surgical SEARCH/REPLACE patch visualizer.
"""

from __future__ import annotations

import difflib
from typing import List, Optional, Tuple

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


class DiffVisualizer:
    """Renders beautiful terminal visual diffs in inline or side-by-side formats."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    @staticmethod
    def render_inline_diff(
        diff_text: str,
        title: str = "Unified Diff",
        border_style: str = "yellow",
    ) -> Panel:
        """
        Renders a unified diff string with stylized line numbers and color-coded changes.

        Args:
            diff_text: Standard unified diff text.
            title: Title for the enclosing Rich Panel.
            border_style: Color for panel border.

        Returns:
            Rich Panel containing formatted diff.
        """
        if not diff_text or not diff_text.strip():
            return Panel(
                Text("No changes (working tree clean)", style="dim italic"),
                title=title,
                border_style="dim",
            )

        lines = diff_text.splitlines()
        formatted_text = Text()

        old_lineno = 0
        new_lineno = 0
        in_hunk = False

        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                formatted_text.append(f"{line}\n", style="bold cyan")
            elif line.startswith("diff --git") or line.startswith("index "):
                formatted_text.append(f"{line}\n", style="bold dim")
            elif line.startswith("@@"):
                in_hunk = True
                # Parse hunk header e.g. @@ -1,5 +1,6 @@
                formatted_text.append(f"\n{line}\n", style="bold magenta")
                try:
                    parts = line.split("@@")[1].strip().split()
                    old_spec = parts[0][1:]
                    new_spec = parts[1][1:]
                    old_lineno = int(old_spec.split(",")[0])
                    new_lineno = int(new_spec.split(",")[0])
                except Exception:
                    old_lineno = 1
                    new_lineno = 1
            elif line.startswith("-") and not line.startswith("---"):
                num_str = f"{old_lineno:4d}      │ " if in_hunk else "   - │ "
                formatted_text.append(num_str, style="dim red")
                formatted_text.append(f"{line}\n", style="bold red")
                if in_hunk:
                    old_lineno += 1
            elif line.startswith("+") and not line.startswith("+++"):
                num_str = f"     {new_lineno:4d} │ " if in_hunk else "   + │ "
                formatted_text.append(num_str, style="dim green")
                formatted_text.append(f"{line}\n", style="bold green")
                if in_hunk:
                    new_lineno += 1
            else:
                prefix = line[1:] if line.startswith(" ") else line
                num_str = f"{old_lineno:4d} {new_lineno:4d} │ " if in_hunk else "     │ "
                formatted_text.append(num_str, style="dim gray")
                formatted_text.append(f" {prefix}\n", style="bright_white")
                if in_hunk:
                    old_lineno += 1
                    new_lineno += 1

        return Panel(formatted_text, title=f"[bold yellow]{title}[/bold yellow]", border_style=border_style)

    @classmethod
    def render_side_by_side(
        cls,
        old_code: str,
        new_code: str,
        old_title: str = "Original / Candidate",
        new_title: str = "Modified / Repaired",
        language: str = "python",
        title: str = "Side-by-Side Diff Visualizer",
    ) -> Panel:
        """
        Renders two code strings side-by-side in a 2-column table with aligned lines.

        Args:
            old_code: Original code string.
            new_code: Modified code string.
            old_title: Header title for left column.
            new_title: Header title for right column.
            language: Programming language for syntax formatting.
            title: Panel title.

        Returns:
            Rich Panel containing 2-column table.
        """
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        table = Table(
            show_header=True,
            header_style="bold cyan",
            expand=True,
            box=None,
            padding=(0, 1),
        )
        table.add_column(f"L#", justify="right", style="dim", width=4)
        table.add_column(f"{old_title} (Before)", style="white", ratio=1)
        table.add_column(f"│", justify="center", style="dim", width=1)
        table.add_column(f"R#", justify="right", style="dim", width=4)
        table.add_column(f"{new_title} (After)", style="white", ratio=1)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for idx in range(i2 - i1):
                    l_no = str(i1 + idx + 1)
                    r_no = str(j1 + idx + 1)
                    l_text = Text(old_lines[i1 + idx], style="dim white")
                    r_text = Text(new_lines[j1 + idx], style="dim white")
                    table.add_row(l_no, l_text, "│", r_no, r_text)

            elif tag == "replace":
                max_len = max(i2 - i1, j2 - j1)
                for idx in range(max_len):
                    if idx < (i2 - i1):
                        l_no = str(i1 + idx + 1)
                        l_text = Text(old_lines[i1 + idx], style="bold red")
                    else:
                        l_no = " "
                        l_text = Text("·", style="dim")

                    if idx < (j2 - j1):
                        r_no = str(j1 + idx + 1)
                        r_text = Text(new_lines[j1 + idx], style="bold green")
                    else:
                        r_no = " "
                        r_text = Text("·", style="dim")

                    table.add_row(l_no, l_text, "│", r_no, r_text)

            elif tag == "delete":
                for idx in range(i2 - i1):
                    l_no = str(i1 + idx + 1)
                    l_text = Text(old_lines[i1 + idx], style="bold red")
                    table.add_row(l_no, l_text, "│", " ", Text("·", style="dim"))

            elif tag == "insert":
                for idx in range(j2 - j1):
                    r_no = str(j1 + idx + 1)
                    r_text = Text(new_lines[j1 + idx], style="bold green")
                    table.add_row(" ", Text("·", style="dim"), "│", r_no, r_text)

        return Panel(table, title=f"[bold yellow]{title}[/bold yellow]", border_style="yellow")

    @classmethod
    def render_diff_auto(
        cls,
        diff_text: str,
        old_code: Optional[str] = None,
        new_code: Optional[str] = None,
        side_by_side: bool = False,
        title: str = "Diff",
    ) -> Panel:
        """
        Auto-renders diff in either side-by-side or inline view.
        """
        if side_by_side and old_code is not None and new_code is not None:
            return cls.render_side_by_side(old_code, new_code, title=title)
        return cls.render_inline_diff(diff_text, title=title)

    @classmethod
    def render_surgical_patch_preview(
        cls,
        search_block: str,
        replace_block: str,
        file_path: str = "file.py",
    ) -> Panel:
        """
        Renders a SEARCH/REPLACE surgical patch block preview.
        """
        table = Table(show_header=True, header_style="bold magenta", expand=True, box=None)
        table.add_column("[bold red]SEARCH (Target to Replace)[/bold red]", ratio=1)
        table.add_column("│", justify="center", style="dim", width=1)
        table.add_column("[bold green]REPLACE (Replacement Block)[/bold green]", ratio=1)

        search_syn = Syntax(search_block.strip() or "(empty)", "python", theme="monokai", line_numbers=True)
        replace_syn = Syntax(replace_block.strip() or "(empty)", "python", theme="monokai", line_numbers=True)

        table.add_row(search_syn, "│", replace_syn)
        return Panel(
            table,
            title=f"[bold cyan]Surgical Patch Block: {file_path}[/bold cyan]",
            border_style="cyan",
        )
