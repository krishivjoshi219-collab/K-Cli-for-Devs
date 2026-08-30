"""
rules.py - Project Rules, Custom Developer Instructions & Workspace Guidance Loader
Project Bankai v1.0.0

Loads and manages developer-specific instructions for the AI from:
1. Workspace files: .kclirules, K_RULES.md, .cursorrules, .kcli/rules.md, CLAUDE.md, AGENTS.md
2. User-level global instructions: ~/.kcli/rules.md or ~/.kcli/custom_instructions.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union, Optional, List

MAX_RULE_BYTES = 65_536

DEFAULT_RULES_TEMPLATE = """# K-CLI Custom Developer Instructions (.kclirules)
# Project Bankai Autonomous AI Engine

## Architecture & Code Standards
- Write clean, modular, and type-annotated code (Python 3.12+ / Rust / TypeScript).
- Never remove existing docstrings, tests, or exception handlers unless refactoring.
- Always include robust error handling with zero crashes on edge cases.
- Perform strict AST verification and validate all generated functions against test suites.

## Developer Preferences
- Coding Style: Clean, production-grade, minimal dependencies.
- Test Framework: pytest (Python) / cargo test (Rust) / vitest (TS).
- Security Guardrails: Zero raw secrets in code; use environment variables or Credential Vault.
"""

RULE_FILE_CANDIDATES = [
    ".kclirules",
    "K_RULES.md",
    ".cursorrules",
    ".kcli/rules.md",
    ".kcli/instructions.md",
    "CLAUDE.md",
    "AGENTS.md",
]


def load_project_rules(
    workspace_dir: Union[str, Path] = ".",
    rules_file: Optional[Union[str, Path]] = None,
) -> str:
    """
    Load project-level coding rules and custom developer instructions from workspace
    or global user preferences.
    """
    workspace = Path(workspace_dir).resolve()
    target_file: Optional[Path] = None

    if rules_file is not None:
        rf_path = Path(rules_file)
        if not rf_path.is_absolute():
            rf_path = (workspace / rf_path).resolve()
        else:
            rf_path = rf_path.resolve()

        try:
            rf_path.relative_to(workspace)
        except ValueError:
            raise ValueError("Rules file must be inside the workspace directory.")

        target_file = rf_path
    else:
        # Search workspace candidates
        for cand in RULE_FILE_CANDIDATES:
            p = workspace / cand
            if p.exists() and p.is_file():
                target_file = p
                break

    # If no workspace file found, check global user instructions
    if target_file is None or not target_file.exists():
        global_p = Path.home() / ".kcli" / "rules.md"
        if global_p.exists() and global_p.is_file():
            target_file = global_p

    if target_file is None or not target_file.exists():
        return ""

    content_bytes = target_file.read_bytes()
    if len(content_bytes) > MAX_RULE_BYTES:
        raise ValueError(f"Rules file exceeds byte limit ({len(content_bytes)} > {MAX_RULE_BYTES})")

    content = content_bytes.decode("utf-8", errors="replace")
    return f"### 📋 Custom Developer Instructions & Workspace Rules ({target_file.name}):\n{content.strip()}\n"


def create_default_rules_file(workspace_dir: Union[str, Path] = ".", force: bool = False) -> Path:
    """Creates a starter .kclirules template in the workspace root."""
    workspace = Path(workspace_dir).resolve()
    target = workspace / ".kclirules"
    if target.exists() and not force:
        return target
    target.write_text(DEFAULT_RULES_TEMPLATE, encoding="utf-8")
    return target


def set_global_rules(instructions: str) -> Path:
    """Sets global custom developer instructions in ~/.kcli/rules.md."""
    global_dir = Path.home() / ".kcli"
    global_dir.mkdir(parents=True, exist_ok=True)
    target = global_dir / "rules.md"
    target.write_text(instructions.strip(), encoding="utf-8")
    return target
