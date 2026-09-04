"""
memory.py - Persistent Self-Learning Project Memory Engine for K-CLI
Project Bankai Engine v1.0.0

Provides:
1. Automatic detection and management of `KCLI.md` and `.kcli/MEMORY.md`.
2. Active learning: remembers project conventions, test commands, and past bug resolutions.
3. Injects accumulated project memory into the Autonomous Agent system prompt.
4. Prevents the agent from repeating past mistakes or breaking architectural standards.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("k_cli.core.memory")

DEFAULT_MEMORY_TEMPLATE = """# 🧠 K-CLI Project Memory & Architecture Context

## 📌 Project Overview & Tech Stack
- Automatically discovered and updated by K-CLI Autonomous Workstation.

## ⚙️ Build & Verification Directives
- Test Runner: `pytest`
- Language Standards: Python 3.11+ / Strict Type Hints

## 💡 Learned Lessons & Bug Resolutions
- [Initialization] Project initialized under K-CLI Autonomous Workstation.
"""


class ProjectMemoryManager:
    """
    Manages persistent, evolving project memory stored in `KCLI.md` or `.kcli/MEMORY.md`.
    """

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = Path(workspace_dir or ".").resolve()
        self.primary_memory_file = self.workspace_dir / "KCLI.md"
        self.dot_memory_file = self.workspace_dir / ".kcli" / "MEMORY.md"

    def _resolve_file(self) -> Path:
        if self.primary_memory_file.exists():
            return self.primary_memory_file
        if self.dot_memory_file.exists():
            return self.dot_memory_file
        return self.primary_memory_file

    def initialize_if_missing(self) -> None:
        target = self._resolve_file()
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(DEFAULT_MEMORY_TEMPLATE, encoding="utf-8")
            logger.info(f"Initialized project memory at {target}")

    def load_memory(self, max_chars: int = 4000) -> str:
        """Loads project memory for prompt injection, bounded to prevent token bloat."""
        target = self._resolve_file()
        if not target.exists():
            return ""
        try:
            content = target.read_text(encoding="utf-8", errors="replace").strip()
            if len(content) > max_chars:
                return content[:max_chars] + "\n... [truncated project memory] ..."
            return content
        except Exception as e:
            logger.error(f"Error loading project memory: {e}")
            return ""

    def record_learning(self, lesson: str, category: str = "Lesson") -> None:
        """Appends a new learned convention, bug fix pattern, or instruction."""
        target = self._resolve_file()
        self.initialize_if_missing()

        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"- [{timestamp_str}] ({category}): {lesson.strip()}\n"

        try:
            current = target.read_text(encoding="utf-8", errors="replace")
            if "## 💡 Learned Lessons & Bug Resolutions" in current:
                parts = current.split("## 💡 Learned Lessons & Bug Resolutions")
                updated = f"{parts[0]}## 💡 Learned Lessons & Bug Resolutions\n{entry}{parts[1].lstrip()}"
            else:
                updated = f"{current.strip()}\n\n## 💡 Learned Lessons & Bug Resolutions\n{entry}"

            target.write_text(updated, encoding="utf-8")
            logger.info(f"Recorded learning in {target.name}: {lesson[:60]}...")
        except Exception as e:
            logger.error(f"Failed to record learning: {e}")


# Global Singleton Accessor
global_memory_manager = ProjectMemoryManager()
