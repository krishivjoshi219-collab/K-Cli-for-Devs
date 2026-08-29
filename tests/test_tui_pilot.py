"""
test_tui_pilot.py - Automated Headless Textual Pilot Simulation Tests for K-CLI TUI
Verifies zero dead-ends, smooth navigation, input handling, and modal lifecycle.
"""

import asyncio
from k_cli.tui.tui_app import KCliCyberWorkstation


def test_kcli_tui_full_navigation_and_modals_lifecycle():
    """Simulates a developer navigating every screen, opening and dismissing all modals."""
    async def _runner():
        app = KCliCyberWorkstation(mock_mode=True, show_codex_on_start=False)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            
            # 1. Test input prompt submission
            inp = app.query_one("#main-prompt-input")
            inp.value = "hello agent"
            await pilot.click("#btn-main-send")
            await pilot.pause()
            
            # 2. Test all modals open and dismiss cleanly via Escape
            actions = [
                ("Welcome", app.action_open_welcome),
                ("Codex", app.action_open_codex),
                ("Vault", app.action_open_vault),
                ("Models", app.action_open_models),
                ("Audit", app.action_open_audit),
                ("Conflicts", app.action_open_conflicts),
                ("GitHub", app.action_open_github),
                ("Security", app.action_open_security),
                ("ChaosImmunity", app.action_open_chaos),
                ("LocalHub", app.action_open_local_hub),
                ("Trending", app.action_open_trending),
            ]
            
            for name, action_fn in actions:
                action_fn()
                await pilot.pause()
                assert len(app.screen_stack) > 1, f"{name} modal failed to open"
                
                # Dismiss via escape key
                await pilot.press("escape")
                await pilot.pause()
                assert len(app.screen_stack) == 1, f"{name} modal failed to dismiss"

    asyncio.run(_runner())
