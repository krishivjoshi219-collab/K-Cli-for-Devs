"""
k_cli.ui - UI interfaces package for K-CLI for Devs.
Includes:
- Tier 1: Fullscreen Cyber Workstation TUI (k_cli.tui.tui_app)
- Tier 2: Cyber Station Modern Web Dashboard (k_cli.web.server)
- Tier 3: Streamlined Interactive Terminal REPL (k_cli.ui.simple_repl)
"""
from k_cli.ui.simple_repl import SimpleCyberCLI, run_simple_cli

__all__ = ["SimpleCyberCLI", "run_simple_cli"]
