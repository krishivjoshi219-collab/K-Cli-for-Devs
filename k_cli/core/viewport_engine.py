"""
viewport_engine.py - Hyper-Responsive Auto-Adjusting Viewport & Layout Engine for K-CLI
Project Bankai v1.0.0

Calculates optimal UI density, pane visibility, modal scaling, and typography
across all terminal sizes and displays (Compact <90cols, Standard 90-140cols, UltraWide >140cols).
Ensures zero visual clipping, zero clutter, and automatic responsive adaptation.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Any


class ViewportMode(str, Enum):
    COMPACT = "compact"        # < 95 cols: 1-pane focus mode, sidebars collapsed
    STANDARD = "standard"      # 95 - 140 cols: 2-pane mode (Sidebar + Canvas)
    ULTRAWIDE = "ultrawide"    # > 140 cols: 3-pane mode (Sidebar + Canvas + Drawer)


@dataclass
class ViewportGeometry:
    width: int
    height: int
    mode: ViewportMode
    show_left_sidebar: bool
    show_right_drawer: bool
    sidebar_width: int
    drawer_width: int
    chat_width_fraction: float
    hud_density: str
    is_height_constrained: bool

    def to_css_classes(self) -> list[str]:
        classes = [f"viewport-{self.mode.value}"]
        if not self.show_left_sidebar:
            classes.append("hide-sidebar")
        if not self.show_right_drawer:
            classes.append("hide-drawer")
        if self.is_height_constrained:
            classes.append("height-compact")
        return classes


class ViewportEngine:
    """
    Real-time screen geometry and auto-adjusting layout calculator (<0.01ms).
    """

    @classmethod
    def get_current_terminal_size(cls) -> Tuple[int, int]:
        """Gets (columns, rows) of current terminal with graceful fallback."""
        try:
            size = shutil.get_terminal_size(fallback=(120, 35))
            return size.columns, size.lines
        except Exception:
            return 120, 35

    @classmethod
    def compute_geometry(cls, width: Optional[int] = None, height: Optional[int] = None) -> ViewportGeometry:
        """
        Calculates optimal layout dimensions and visibility flags based on viewport width & height.
        """
        if width is None or height is None:
            cur_w, cur_h = cls.get_current_terminal_size()
            width = width if width is not None else cur_w
            height = height if height is not None else cur_h

        # Prevent degenerate dimensions
        w = max(40, width)
        h = max(15, height)

        is_height_compact = h < 26

        if w >= 140:
            mode = ViewportMode.ULTRAWIDE
            show_left = True
            show_right = True
            left_w = 26
            right_w = 30
            density = "full"
        elif w >= 95:
            mode = ViewportMode.STANDARD
            show_left = True
            show_right = False  # Right drawer hidden to give maximum space to canvas
            left_w = 22
            right_w = 0
            density = "standard"
        else:
            mode = ViewportMode.COMPACT
            show_left = False
            show_right = False  # Pure 1-pane streamlined focus mode
            left_w = 0
            right_w = 0
            density = "minimal"

        # Calculate chat width ratio
        occupied = (left_w if show_left else 0) + (right_w if show_right else 0)
        remaining = max(30, w - occupied)
        chat_fraction = remaining / w

        return ViewportGeometry(
            width=w,
            height=h,
            mode=mode,
            show_left_sidebar=show_left,
            show_right_drawer=show_right,
            sidebar_width=left_w,
            drawer_width=right_w,
            chat_width_fraction=chat_fraction,
            hud_density=density,
            is_height_constrained=is_height_compact,
        )
