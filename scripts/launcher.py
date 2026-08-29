#!/usr/bin/env python3
"""
launcher.py - Entrypoint script for launching K-CLI application interfaces.
"""

import sys
from pathlib import Path

# Add project root directory to python path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from k_cli.cli import app

if __name__ == "__main__":
    app()
