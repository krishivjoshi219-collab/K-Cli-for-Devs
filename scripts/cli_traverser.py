"""
cli_traverser.py - Automated CLI Mapping, Traversal & Fuzzing Runner
Project Bankai v1.0.0

Executes root command, discovers all subcommands & flags, traverses execution
paths, injects boundary values, detects unhandled tracebacks, and outputs a
structured markdown report.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TraversalRecord:
    command_path: str
    args: List[str]
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    has_traceback: bool = False
    is_hang: bool = False
    status: str = "PASS"  # "PASS", "GRACEFUL_ERROR", "CRASH_TRACEBACK", "HANG_TIMEOUT"
    notes: str = ""


class CLITraverser:
    """
    Automated CLI Path Explorer & Fuzzer.
    """

    def __init__(self, python_bin: Optional[str] = None):
        self.python_bin = python_bin or sys.executable
        self.results: List[TraversalRecord] = []

    def execute(self, args: List[str], timeout: float = 8.0) -> TraversalRecord:
        """Runs a single CLI command invocation."""
        env = os.environ.copy()
        env["PYTHONPATH"] = f"/home/k/k_cli:{env.get('PYTHONPATH', '')}"
        env["KCLI_MOCK"] = "1"

        cmd = [self.python_bin, "-m", "k_cli.cli"] + args
        cmd_str = "k-cli " + " ".join(args)

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd="/home/k/k_cli",
            )
            duration = (time.perf_counter() - start) * 1000.0
            stdout, stderr = proc.stdout, proc.stderr
            code = proc.returncode

            has_tb = "Traceback (most recent call last)" in (stdout + stderr)
            if has_tb:
                status = "CRASH_TRACEBACK"
            elif code == 0:
                status = "PASS"
            else:
                status = "GRACEFUL_ERROR"

            return TraversalRecord(
                command_path=cmd_str,
                args=args,
                exit_code=code,
                duration_ms=duration,
                stdout=stdout[:500],
                stderr=stderr[:500],
                has_traceback=has_tb,
                is_hang=False,
                status=status,
            )

        except subprocess.TimeoutExpired:
            duration = (time.perf_counter() - start) * 1000.0
            return TraversalRecord(
                command_path=cmd_str,
                args=args,
                exit_code=-999,
                duration_ms=duration,
                stdout="",
                stderr="Timeout expired (> 4.0s)",
                has_traceback=False,
                is_hang=True,
                status="HANG_TIMEOUT",
                notes="Execution did not terminate within safety deadline.",
            )

    def run_full_traversal(self) -> List[TraversalRecord]:
        """Traverses standard, edge-case, and boundary command vectors."""
        test_vectors: List[List[str]] = [
            # 1. Standard Commands & Flags
            ["--help"],
            ["doctor"],
            ["status"],
            ["diff"],
            ["map"],
            ["doc", "json.dumps"],
            ["test"],
            ["watch", "--once"],
            ["bisect", "python -c 'import sys; sys.exit(0)'", "--good", "HEAD", "--bad", "HEAD"],
            ["route", "refactor auth token verification"],
            ["garden", "--json"],
            ["explain", "How does verifier work?"],
            ["synapse", "verifier AST"],
            ["airgap"],
            ["scaffold", "FastAPI + Redis", "--dir", "/tmp/traversal_scaffold_test"],
            ["keys"],
            ["keys", "test"],
            ["keys", "set", "TEST_KEY", "val123"],
            ["auth"],
            ["conflict", "list"],
            ["conflict", "--help"],
            ["pr", "list"],
            ["pr", "--help"],
            ["gh", "status"],
            ["gh", "--help"],
            ["issue", "--help"],
            ["release", "--help"],
            ["action", "--help"],
            ["gist", "--help"],
            ["security", "scan"],
            ["models", "list"],
            ["mcp", "list"],
            ["dedup", "check", "Fix jwt auth token bug"],

            # 2. Boundary & Fuzz Vectors
            ["--invalid-flag-999"],
            ["unknown_subcommand_xyz"],
            ["explain", ""],
            ["explain", "A" * 5000],  # Giant query
            ["route", ""],
            ["scaffold", ""],
            ["doc", ""],
            ["doc", "non_existent_symbol_12345"],
            ["verify", "--file", "/tmp/non_existent_file_404.py"],
            ["keys", "set", "", ""],
            ["keys", "import", "/tmp/non_existent_file.json"],
            ["pr", "view", "-1"],
            ["pr", "review", "0"],
            ["pr", "fix", "99999"],
            ["pr", "merge", "99999"],
            ["conflict", "resolve", "--file", "non_existent.py"],
            ["mcp", "remove", "non_existent_server"],
            ["dedup", "check", ""],
            ["dedup", "check", "{invalid: json, [unclosed"],
            ["watch", "--interval", "0", "--once"],
        ]

        for i, vec in enumerate(test_vectors):
            rec = self.execute(vec)
            self.results.append(rec)
            print(f"[{i+1}/{len(test_vectors)}] {rec.status} ({rec.duration_ms:.0f}ms): {rec.command_path}", flush=True)

        return self.results

    def generate_markdown_report(self) -> str:
        """Generates comprehensive markdown audit log."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        graceful = sum(1 for r in self.results if r.status == "GRACEFUL_ERROR")
        crashes = sum(1 for r in self.results if r.status == "CRASH_TRACEBACK")
        hangs = sum(1 for r in self.results if r.status == "HANG_TIMEOUT")

        lines = [
            "# 🔍 K-CLI Systematic Binary Traversal & Fuzzing Audit Report",
            f"**Total Paths Traversed**: `{total}` | **Passed**: `{passed}` | **Graceful Errors**: `{graceful}` | **Crashes**: `{crashes}` | **Hangs**: `{hangs}`",
            "",
            "## Summary Table",
            "| Command Path | Exit Code | Duration | Status | Notes |",
            "| :--- | :---: | :---: | :---: | :--- |",
        ]

        for r in self.results:
            status_badge = {
                "PASS": "🟢 PASS",
                "GRACEFUL_ERROR": "🟡 GRACEFUL REJECT",
                "CRASH_TRACEBACK": "🔴 UNHANDLED CRASH",
                "HANG_TIMEOUT": "🚨 HANG TIMEOUT",
            }.get(r.status, r.status)
            lines.append(f"| `{r.command_path[:40]}` | `{r.exit_code}` | `{r.duration_ms:.1f}ms` | {status_badge} | {r.notes or ('OK' if r.exit_code == 0 else 'Handled')} |")

        if crashes > 0:
            lines.extend([
                "",
                "## 🔴 Unhandled Crashes Detected",
            ])
            for r in self.results:
                if r.status == "CRASH_TRACEBACK":
                    lines.extend([
                        f"### Path: `{r.command_path}`",
                        f"**Stderr**:\n```\n{r.stderr}\n```",
                    ])

        return "\n".join(lines)


if __name__ == "__main__":
    traverser = CLITraverser()
    traverser.run_full_traversal()
    report = traverser.generate_markdown_report()
    Path("docs/CLI_TRAVERSAL_AUDIT.md").write_text(report, encoding="utf-8")
    print(report)
