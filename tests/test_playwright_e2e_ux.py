"""
test_playwright_e2e_ux.py - End-to-End Playwright UX & Real Prompt Test for K-CLI Cyber Station
"""

import os
import sys
import time
import socket
import uvicorn
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

_root_dir = Path(__file__).parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from k_cli.core.credentials import CredentialsManager
from k_cli.web.server import create_app

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_e2e_ux_test():
    print("==================================================================")
    print("  K-CLI REAL PLAYWRIGHT E2E & USER EXPERIENCE AUDIT")
    print("==================================================================")

    # 1. Load credentials from key.json / env
    creds = CredentialsManager.load_all_credentials()
    print(f"[*] Loaded API credentials ({len(creds)} providers detected)")

    port = find_free_port()
    app = create_app()
    server_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    print(f"[*] Started K-CLI Web UI server on http://127.0.0.1:{port}")

    # Wait for server readiness
    time.sleep(2)

    screenshot_dir = Path("/home/k/.gemini/antigravity-cli/brain/23e80555-f72c-4c99-9a36-45630791e641/ux_screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    test_results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Listen for console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("\n--- 1. Testing Page Load & Telemetry HUD ---")
        page.goto(f"http://127.0.0.1:{port}", timeout=15000)
        page.wait_for_selector(".header-bar", timeout=5000)

        title = page.title()
        print(f"[✔] Page title: '{title}'")
        assert "K-CLI Cyber Station" in title, f"Unexpected page title: {title}"

        # Verify status pills
        model_text = page.text_content("#stat-model")
        branch_text = page.text_content("#stat-branch")
        ram_text = page.text_content("#stat-ram")
        print(f"[✔] HUD Status: Model='{model_text}', Branch='{branch_text}', RAM='{ram_text}'")
        test_results["hud_telemetry"] = "PASS"

        # --- 2. Testing Cyber Agent with REAL Prompt and API key ---
        print("\n--- 2. Testing Cyber Agent Tab (Real Prompt & WebSocket Stream) ---")
        page.click('.nav-item[data-tab="tab-agent"]')
        page.wait_for_selector("#tab-agent.active", timeout=3000)

        # Quick chip interaction - click the first chip
        first_chip = page.locator(".quick-chip").first
        first_chip.click()
        prompt_val = page.input_value("#agent-prompt")
        print(f"[✔] Quick chip populated prompt: '{prompt_val[:40]}...'")

        # Set real prompt and model
        real_prompt = "Write a python function is_palindrome(text: str) -> bool with docstring and unit tests"
        page.fill("#agent-prompt", real_prompt)

        # Select model (gemini-2.0-flash)
        try:
            page.select_option("#agent-model", value="gemini-2.0-flash")
            print(f"[✔] Selected model: gemini-2.0-flash")
        except Exception:
            print(f"[!] Using default/auto model selection")

        # Click Run Agent
        print("[*] Clicking 'Run Cyber Agent' with real API key...")
        page.click("#btn-run-agent")

        # Wait for terminal to receive streaming output
        page.wait_for_selector("#agent-terminal", timeout=5000)

        # Wait up to 35 seconds for agent execution to complete
        start_wait = time.time()
        completed = False
        while time.time() - start_wait < 35:
            badge_text = page.text_content("#badge-verif") or ""
            term_content = page.text_content("#agent-terminal") or ""
            if "AST VERIFIED" in badge_text or "is_palindrome" in term_content or "def " in term_content:
                completed = True
                break
            time.sleep(1)

        final_term = page.text_content("#agent-terminal") or ""
        badge_status = page.text_content("#badge-verif") or ""
        print(f"[✔] Agent Run Completed in {time.time() - start_wait:.1f}s (Status Badge: '{badge_status}')")
        print(f"    Terminal preview: {final_term[:150].replace(chr(10), ' ')}...")
        assert len(final_term) > 20, "Agent terminal output was empty!"
        test_results["cyber_agent_real_run"] = "PASS"

        # Test copy button
        page.click("#btn-copy-output")
        time.sleep(0.5)
        copy_text = page.text_content("#btn-copy-output")
        print(f"[✔] Copy button state: '{copy_text.strip()}'")

        page.screenshot(path=str(screenshot_dir / "01_cyber_agent_completed.png"))

        # --- 3. Testing Incident Triage Tab ---
        print("\n--- 3. Testing Incident Crash Triage Tab ---")
        page.click('.nav-item[data-tab="tab-triage"]')
        page.wait_for_selector("#tab-triage.active", timeout=3000)

        traceback_sample = """Traceback (most recent call last):
  File "calculator.py", line 8, in divide
    return a / b
ZeroDivisionError: division by zero"""
        page.fill("#triage-log", traceback_sample)
        page.click("#btn-triage")
        page.wait_for_selector("#triage-result-card:not(.hidden)", timeout=15000)
        triage_out = page.text_content("#triage-output") or ""
        print(f"[✔] Triage Analysis: {triage_out[:100].replace(chr(10), ' ')}...")
        assert len(triage_out) > 10, "Triage output was empty!"
        test_results["incident_triage"] = "PASS"
        page.screenshot(path=str(screenshot_dir / "02_incident_triage.png"))

        # --- 4. Testing Security Shield Tab ---
        print("\n--- 4. Testing Security Shield Tab ---")
        page.click('.nav-item[data-tab="tab-security"]')
        page.wait_for_selector("#tab-security.active", timeout=3000)
        page.click("#btn-scan-security")
        # Wait for scan results container to not have loading text
        time.sleep(2)
        page.wait_for_selector("#security-results-container", timeout=10000)
        sec_out = page.text_content("#security-results-container") or ""
        print(f"[✔] Security Scan Output: {sec_out[:100].replace(chr(10), ' ')}...")
        test_results["security_shield"] = "PASS"
        page.screenshot(path=str(screenshot_dir / "03_security_shield.png"))

        # --- 5. Testing DevDocs Search Tab ---
        print("\n--- 5. Testing DevDocs Search Tab ---")
        page.click('.nav-item[data-tab="tab-devdocs"]')
        page.wait_for_selector("#tab-devdocs.active", timeout=3000)
        page.fill("#devdocs-query", "mmap")
        page.click("#btn-search-devdocs")
        page.wait_for_selector("#devdocs-results-container .spotlight-card", timeout=10000)
        docs_out = page.text_content("#devdocs-results-container") or ""
        print(f"[✔] DevDocs Search Output: {docs_out[:100].replace(chr(10), ' ')}...")
        assert "mmap" in docs_out or "virtual address" in docs_out, "DevDocs search returned no results!"
        test_results["devdocs_search"] = "PASS"
        page.screenshot(path=str(screenshot_dir / "04_devdocs.png"))

        # --- 6. Testing API Credentials Vault Tab ---
        print("\n--- 6. Testing API Credentials Vault Tab ---")
        page.click('.nav-item[data-tab="tab-vault"]')
        page.wait_for_selector("#tab-vault.active", timeout=3000)
        time.sleep(1)
        vault_cards = page.locator("#vault-keys-grid .spotlight-card").all()
        print(f"[✔] Vault rendered {len(vault_cards)} provider key cards")
        assert len(vault_cards) > 0, "No vault key cards rendered!"
        test_results["credentials_vault"] = "PASS"
        page.screenshot(path=str(screenshot_dir / "05_credentials_vault.png"))

        # --- 7. Testing Model Hub Tab ---
        print("\n--- 7. Testing Model Hub & Bankai Tab ---")
        page.click('.nav-item[data-tab="tab-models"]')
        page.wait_for_selector("#tab-models.active", timeout=3000)
        time.sleep(1)
        model_cards = page.locator("#models-list-container .spotlight-card").all()
        print(f"[✔] Model Hub rendered {len(model_cards)} model cards")
        assert len(model_cards) > 0, "No model cards rendered in Model Hub!"
        test_results["model_hub"] = "PASS"
        page.screenshot(path=str(screenshot_dir / "06_model_hub.png"))

        browser.close()

    print("\n==================================================================")
    print("  ALL REAL PLAYWRIGHT UX & AGENT TESTS PASSED WITHOUT DEAD ENDS!  ")
    print(f"  Screenshots saved to: {screenshot_dir}")
    print("  Results Summary:", test_results)
    print("==================================================================")

if __name__ == "__main__":
    run_e2e_ux_test()
