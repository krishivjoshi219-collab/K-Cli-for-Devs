"""
tests/test_viewport_engine.py
Unit tests for ViewportEngine auto-adjusting responsive layout calculator.
"""

import pytest
from k_cli.core.viewport_engine import ViewportEngine, ViewportMode, ViewportGeometry


def test_viewport_engine_ultrawide():
    geom = ViewportEngine.compute_geometry(width=160, height=45)
    assert geom.mode == ViewportMode.ULTRAWIDE
    assert geom.show_left_sidebar is True
    assert geom.show_right_drawer is True
    assert geom.sidebar_width == 26
    assert geom.drawer_width == 30
    assert geom.is_height_constrained is False


def test_viewport_engine_standard():
    geom = ViewportEngine.compute_geometry(width=110, height=35)
    assert geom.mode == ViewportMode.STANDARD
    assert geom.show_left_sidebar is True
    assert geom.show_right_drawer is False
    assert geom.sidebar_width == 22
    assert geom.drawer_width == 0


def test_viewport_engine_compact_mobile():
    geom = ViewportEngine.compute_geometry(width=80, height=24)
    assert geom.mode == ViewportMode.COMPACT
    assert geom.show_left_sidebar is False
    assert geom.show_right_drawer is False
    assert geom.sidebar_width == 0
    assert geom.drawer_width == 0
    assert geom.is_height_constrained is True


def test_viewport_css_classes():
    geom = ViewportEngine.compute_geometry(width=70, height=20)
    classes = geom.to_css_classes()
    assert "viewport-compact" in classes
    assert "hide-sidebar" in classes
    assert "hide-drawer" in classes
    assert "height-compact" in classes
