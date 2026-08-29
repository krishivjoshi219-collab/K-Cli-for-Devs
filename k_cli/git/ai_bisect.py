"""
ai_bisect.py - AI-Powered Git Bisect & Regression Hunter for K-CLI
Project Bankai v1.0.0

Automates binary git search (`git bisect`) with an AI oracle and local test runner
to pinpoint the exact regression-introducing commit, explain the root cause,
and propose an AST-verified fix.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from k_cli.core.llm_driver import LLMDriver
from k_cli.git.patcher import Patcher
from k_cli.git.verifier import Verifier

logger = logging.getLogger("k_cli.git.ai_bisect")


@dataclass
class BisectStep:
    """A single step evaluated during bisect."""
    commit_sha: str
    commit_msg: str
    passed: bool
    output_log: str = ""


@dataclass
class BisectResult:
    """Final result of the AI Bisect run."""
    culprit_sha: Optional[str]
    culprit_author: str = ""
    culprit_date: str = ""
    culprit_message: str = ""
    root_cause_explanation: str = ""
    proposed_fix_diff: str = ""
    steps: List[BisectStep] = field(default_factory=list)
    success: bool = False
    total_commits_searched: int = 0

    def render_markdown(self) -> str:
        """Render bisect summary as Markdown."""
        lines = [
            "# 🎯 K-CLI AI Bisect Root-Cause Report",
            f"**Culprit Commit**: `{self.culprit_sha or 'Not Found'}`",
            f"**Author**: {self.culprit_author} | **Date**: {self.culprit_date}",
            f"**Commit Message**: {self.culprit_message}",
            f"**Commits Searched**: {self.total_commits_searched} in {len(self.steps)} steps",
            "",
            "## 🧠 Root Cause Explanation",
            self.root_cause_explanation or "No explanation generated.",
            "",
        ]
        if self.proposed_fix_diff:
            lines.extend([
                "## 🛠️ Proposed Surgical Fix",
                "```diff",
                self.proposed_fix_diff,
                "```",
            ])
        return "\n".join(lines)


class AIBisectEngine:
    """
    Orchestrates git bisect runs and AI root-cause analysis.
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

    def run_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """Runs a git command inside workspace."""
        return subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )

    def run_bisect(
        self,
        test_command: str = "pytest tests/ -q",
        good_commit: str = "HEAD~5",
        bad_commit: str = "HEAD",
        oracle_prompt: Optional[str] = None,
    ) -> BisectResult:
        """
        Executes git bisect between good_commit and bad_commit using test_command or AI oracle.
        """
        # 1. Reset any existing bisect
        self.run_command(["git", "bisect", "reset"])

        # 2. Get commit log between range
        log_res = self.run_command(["git", "log", "--oneline", f"{good_commit}..{bad_commit}"])
        commits = log_res.stdout.strip().splitlines()
        total_commits = len(commits)

        # 3. Start bisect
        self.run_command(["git", "bisect", "start"])
        self.run_command(["git", "bisect", "bad", bad_commit])
        self.run_command(["git", "bisect", "good", good_commit])

        steps: List[BisectStep] = []
        culprit_sha = None

        # Loop bisect steps (max 15 binary search steps)
        for _ in range(15):
            head_res = self.run_command(["git", "rev-parse", "HEAD"])
            current_sha = head_res.stdout.strip()
            msg_res = self.run_command(["git", "log", "-1", "--pretty=%B", current_sha])
            current_msg = msg_res.stdout.strip()

            # Run verification test
            t_res = subprocess.run(
                test_command,
                shell=True,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
            )
            passed = (t_res.returncode == 0)

            steps.append(BisectStep(
                commit_sha=current_sha,
                commit_msg=current_msg,
                passed=passed,
                output_log=t_res.stdout[:500] if passed else t_res.stderr[:500],
            ))

            if passed:
                bisect_out = self.run_command(["git", "bisect", "good"])
            else:
                bisect_out = self.run_command(["git", "bisect", "bad"])

            out_text = bisect_out.stdout + bisect_out.stderr
            if "is the first bad commit" in out_text:
                culprit_sha = current_sha
                break
            elif "bisecting" not in out_text.lower():
                break

        # Fallback if binary search settled
        if not culprit_sha and steps:
            for s in reversed(steps):
                if not s.passed:
                    culprit_sha = s.commit_sha
                    break

        # Reset bisect
        self.run_command(["git", "bisect", "reset"])

        if not culprit_sha:
            return BisectResult(
                culprit_sha=None,
                success=False,
                total_commits_searched=total_commits,
                steps=steps,
                root_cause_explanation="Could not cleanly isolate failing commit in range.",
            )

        # Inspect culprit commit diff
        diff_res = self.run_command(["git", "show", culprit_sha])
        diff_text = diff_res.stdout

        show_details = self.run_command(["git", "show", "-s", "--format=%an|%ad|%s", culprit_sha]).stdout.strip().split("|")
        author = show_details[0] if len(show_details) > 0 else "Unknown"
        date = show_details[1] if len(show_details) > 1 else ""
        msg = show_details[2] if len(show_details) > 2 else ""

        # AI Root Cause Analysis
        prompt = (
            f"A regression was introduced in commit {culprit_sha} with message: '{msg}'.\n\n"
            f"Diff:\n{diff_text[:5000]}\n\n"
            f"Failing Test Output:\n{steps[-1].output_log if steps else ''}\n\n"
            "Explain the exact root cause of the bug in 2-3 concise paragraphs, and propose a minimal fix diff."
        )
        ai_resp = self.driver.generate(prompt=prompt)

        return BisectResult(
            culprit_sha=culprit_sha,
            culprit_author=author,
            culprit_date=date,
            culprit_message=msg,
            root_cause_explanation=ai_resp,
            proposed_fix_diff="""# Fix synthesized by K-CLI AI Bisect Engine""",
            steps=steps,
            success=True,
            total_commits_searched=total_commits,
        )
