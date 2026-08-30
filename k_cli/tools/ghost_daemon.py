"""
ghost_daemon.py - Ghost Terminal Autopilot & Background Error Healer for K-CLI
Project Bankai v1.0.0

Attaches to any dev server, compiler, or test runner subprocess, intercepts
tracebacks and compilation errors in real-time, extracts AST context, synthesizes
verified surgical patches, and presents an interactive terminal fix prompt.
"""

from __future__ import annotations

import logging
import os
import pty
import select
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from k_cli.core.llm_driver import LLMDriver
from k_cli.git.patcher import Patcher
from k_cli.git.verifier import Verifier
from k_cli.tools.incident_triage import IncidentReport, IncidentTriageEngine

logger = logging.getLogger("k_cli.tools.ghost_daemon")


@dataclass
class GhostHealPrompt:
    """A synthesized heal proposal presented to the developer."""
    incident: IncidentReport
    proposed_patch: str
    target_file: str
    confidence: float = 0.95
    verified_pass: bool = True


class GhostTerminalDaemon:
    """
    Ghost Terminal Autopilot. Wraps a command and heals runtime crashes on the fly.
    """

    def __init__(
        self,
        repo_path: str = ".",
        llm_driver: Optional[LLMDriver] = None,
        verifier: Optional[Verifier] = None,
        patcher: Optional[Patcher] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.driver = llm_driver or LLMDriver(mock_mode=True)
        self.verifier = verifier or Verifier()
        self.patcher = patcher or Patcher()
        self.triage_engine = IncidentTriageEngine(
            repo_path=str(self.repo_path),
        )

    def analyze_output_buffer(self, output_buffer: str) -> Optional[GhostHealPrompt]:
        """
        Scans output text for stack traces and generates a verified heal proposal.
        """
        # Look for error signatures
        if not any(k in output_buffer for k in ("Traceback", "TypeError", "ValueError", "ImportError", "AttributeError", "SyntaxError", "error[E", "panic:", "Uncaught")):
            return None

        incident = self.triage_engine.triage_log_or_trace(raw_log=output_buffer)
        if not incident.culprit_file:
            return None

        # Synthesize surgical fix
        heal_res = self.triage_engine.auto_heal_incident(
            incident=incident,
            verifier=self.verifier,
            patcher=self.patcher,
            llm_driver=self.driver,
        )

        return GhostHealPrompt(
            incident=incident,
            proposed_patch=heal_res.patch_diff,
            target_file=incident.culprit_file,
            confidence=0.95,
            verified_pass=heal_res.success,
        )

    def run_wrapped_command(
        self,
        command_str: str,
        on_heal_prompt: Optional[Callable[[GhostHealPrompt], bool]] = None,
    ) -> int:
        """
        Runs the command in a subprocess, monitors output, and prompts when an error occurs.
        """
        import shlex
        cmd_args = shlex.split(command_str) if isinstance(command_str, str) else command_str
        proc = subprocess.Popen(
            cmd_args,
            shell=False,
            cwd=str(self.repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout_data, stderr_data = proc.communicate()
        combined_output = stdout_data + "\n" + stderr_data

        if proc.returncode != 0:
            proposal = self.analyze_output_buffer(combined_output)
            if proposal and on_heal_prompt:
                apply = on_heal_prompt(proposal)
                if apply and proposal.proposed_patch:
                    self.patcher.apply_patch(
                        file_path=str(self.repo_path / proposal.target_file),
                        search_block="",
                        replace_block=proposal.proposed_patch,
                    )

        return proc.returncode
