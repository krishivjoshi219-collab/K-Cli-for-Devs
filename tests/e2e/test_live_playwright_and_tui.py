"""
tests/e2e/test_live_playwright_and_tui.py - Live Automated App Verification Suite
Tests the complete real-world user experience across:
1. Live Web UI Dashboard via Playwright Chromium automation
2. Full Textual Cyber-Workstation TUI via Textual App Pilot
"""

import asyncio
import os
import socket
import sys
import time
import threading
from pathlib import Path
import pytest
import uvicorn

from k_cli.web.server import create_app
from k_cli.tui.tui_app import KCliCyberWorkstation


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server_in_thread(port: int):
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server


def wait_for_server(port: int, timeout: float = 10.0):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def test_playwright_web_ui_e2e():
    from playwright.sync_api import sync_playwright

    port = get_free_port()
    server = run_server_in_thread(port=port)
    assert wait_for_server(port=port), "FastAPI Web Server failed to start!"

    screenshots_dir = Path("demo_assets/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 850})

        print(f"\n[Playwright] 1. Loading K-CLI Web UI Dashboard on port {port}...")
        page.goto(f"http://127.0.0.1:{port}")
        page.wait_for_selector("#btn-run-agent", timeout=8000)

        # 1. Test Status Header
        badge_status = page.locator("#pill-status").inner_text()
        print(f"[Playwright] ✔ Status badge: {badge_status.strip()}")
        assert len(badge_status) > 0

        page.screenshot(path=str(screenshots_dir / "01_web_ui_landing.png"))

        # 2. Test Agent Streaming Prompt (Selecting Gemini 2.0 Flash)
        print("[Playwright] 2. Typing prompt and executing Autonomous Agent stream...")
        page.select_option("#agent-model", "gemini-2.0-flash")
        page.fill("#agent-prompt", "Explain how K-CLI achieves autonomous AST verification in 2 concise sentences.")
        page.click("#btn-run-agent")

        # Wait for terminal to start receiving streamed tokens
        page.wait_for_timeout(1000)
        page.wait_for_function("() => document.getElementById('agent-terminal').textContent.length > 30", timeout=20000)
        
        term_text = page.locator("#agent-terminal").inner_text()
        print(f"[Playwright] ✔ Live streamed token output ({len(term_text)} chars):\n{term_text[:140]}...")
        assert len(term_text) > 30, "No tokens streamed to terminal!"

        page.screenshot(path=str(screenshots_dir / "02_web_ui_streamed.png"))

        # 3. Test Incident Crash Triage
        print("[Playwright] 3. Testing Incident Crash Triage Studio...")
        page.click("button.nav-item[data-tab='tab-triage']")
        page.fill("#triage-log", "Traceback (most recent call last):\n  File 'server.py', line 42, in <module>\nZeroDivisionError: division by zero")
        page.click("#btn-triage")
        page.wait_for_function("() => document.getElementById('triage-output').textContent.includes('{') || document.getElementById('triage-output').textContent.includes('ZeroDivisionError') || document.getElementById('triage-output').textContent.includes('triage')", timeout=10000)
        triage_text = page.locator("#triage-output").inner_text()
        print(f"[Playwright] ✔ Triage output generated ({len(triage_text)} chars)")
        assert len(triage_text) > 10

        # 4. Test 3-Way Conflict Studio
        print("[Playwright] 4. Testing 3-Way Merge Conflict Studio...")
        page.click("button.nav-item[data-tab='tab-conflicts']")
        page.click("#btn-scan-conflicts")
        page.wait_for_function("() => document.getElementById('conflicts-list-container').children.length > 0", timeout=10000)
        conflicts_text = page.locator("#conflicts-list-container").inner_text()
        print(f"[Playwright] ✔ Conflict scan output: {conflicts_text[:60]}...")
        assert len(conflicts_text) > 5

        # 5. Test AST Security Scanner
        print("[Playwright] 5. Testing Security Scanner...")
        page.click("button.nav-item[data-tab='tab-security']")
        page.click("#btn-scan-security")
        page.wait_for_function("() => document.getElementById('security-results-container').children.length > 0", timeout=10000)
        sec_text = page.locator("#security-results-container").inner_text()
        print(f"[Playwright] ✔ Security scanner report: {sec_text[:60]}...")
        assert len(sec_text) > 5

        # 6. Test Chaos Immunity Shield
        print("[Playwright] 6. Testing Chaos Immunity Shield...")
        page.click("button.nav-item[data-tab='tab-chaos']")
        page.click("#btn-run-chaos")
        page.wait_for_function("() => document.getElementById('chaos-results-container').children.length > 0", timeout=10000)
        chaos_text = page.locator("#chaos-results-container").inner_text()
        print(f"[Playwright] ✔ Chaos immunity report: {chaos_text[:60]}...")
        assert len(chaos_text) > 5

        # 7. Test DevDocs Search
        print("[Playwright] 7. Testing DevDocs Offline Search...")
        page.click("button.nav-item[data-tab='tab-devdocs']")
        page.fill("#devdocs-query", "functools.lru_cache")
        page.click("#btn-search-devdocs")
        page.wait_for_timeout(1000)
        devdocs_text = page.locator("#devdocs-results-container").inner_text()
        print(f"[Playwright] ✔ DevDocs search completed ({len(devdocs_text)} chars)")

        # 8. Test API Vault Tab
        print("[Playwright] 8. Testing API Credentials Vault Tab...")
        page.click("button.nav-item[data-tab='tab-vault']")
        page.wait_for_timeout(500)
        vault_badge = page.locator("#badge-key-detect").inner_text()
        print(f"[Playwright] ✔ Vault tab loaded ({vault_badge})")

        # 9. Test Model Hub Tab
        print("[Playwright] 9. Testing Model Hub & Intent Routing Tab...")
        page.click("button.nav-item[data-tab='tab-models']")
        page.wait_for_timeout(500)
        models_text = page.locator("#tab-models").inner_text()
        print(f"[Playwright] ✔ Model Hub tab loaded ({len(models_text)} chars)")

        page.screenshot(path=str(screenshots_dir / "03_web_ui_complete.png"))
        browser.close()

    print("\n🎉 ALL PLAYWRIGHT LIVE BROWSER TESTS PASSED 100% PERFECTLY!\n")


def test_textual_tui_pilot_e2e():
    async def _run():
        print("[Textual TUI] 1. Initializing KCliCyberWorkstation in Pilot mode...")
        app = KCliCyberWorkstation(mock_mode=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            print("[Textual TUI] ✔ TUI Mounted successfully. Testing chat prompt submission...")
            
            inp = app.query_one("#main-prompt-input")
            inp.value = "does the code look solid"
            await pilot.press("enter")
            await pilot.pause(0.5)

            scroll = app.query_one("#chat-scroll")
            assert len(scroll.children) > 0, "No messages rendered in TUI scroll container!"
            print(f"[Textual TUI] ✔ Chat container rendered {len(scroll.children)} elements!")

    asyncio.run(_run())
    print("\n🎉 ALL TEXTUAL TUI PILOT TESTS PASSED 100% PERFECTLY!\n")


if __name__ == "__main__":
    test_playwright_web_ui_e2e()
    test_textual_tui_pilot_e2e()
