"""
pr_watcher.py - Autonomous PR Review & Watcher Daemon for K-CLI
Project Bankai v1.0.0

Monitors a GitHub repository for open pull requests, performs multi-criteria
AI reviews, posts feedback, and can auto-merge if CI passes and reviews approve.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from k_cli.core.llm_driver import LLMDriver
from k_cli.github.github_client import GitHubClient, PRReviewResult, PullRequest
from k_cli.github.github_engine import GitHubEngine

logger = logging.getLogger("k_cli.github.pr_watcher")


@dataclass
class WatchEvent:
    """Represents a PR watcher event."""
    pr_number: int
    pr_title: str
    action_taken: str
    review_status: str
    auto_merged: bool = False
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None


class PRWatcherDaemon:
    """
    Autonomous PR Review & Watcher Daemon.
    Continuously monitors repository for new or updated PRs.
    """

    def __init__(
        self,
        repo_path: str = ".",
        github_client: Optional[GitHubClient] = None,
        llm_driver: Optional[LLMDriver] = None,
        auto_merge_approved: bool = False,
    ):
        self.repo_path = repo_path
        self.client = github_client or GitHubClient()
        self.driver = llm_driver or LLMDriver(mock_mode=True)
        self.auto_merge_approved = auto_merge_approved
        self._processed_shas: Dict[int, str] = {}

    def poll_once(self) -> List[WatchEvent]:
        """
        Performs a single polling cycle over open pull requests.
        """
        events: List[WatchEvent] = []
        try:
            open_prs = self.client.list_pull_requests(state="open", limit=20)
        except Exception as e:
            logger.error(f"Failed to list PRs: {e}")
            return [WatchEvent(pr_number=0, pr_title="Error", action_taken="list_failed", review_status="ERROR", error=str(e))]

        for pr in open_prs:
            last_sha = self._processed_shas.get(pr.number)
            if last_sha == pr.head_sha:
                continue  # Already reviewed this exact commit

            # Review PR
            try:
                diff_text = self.client.get_pr_diff(pr.number)
                prompt = (
                    f"Perform a rigorous code review of PR #{pr.number}: '{pr.title}'\n\n"
                    f"Diff:\n{diff_text[:6000]}\n\n"
                    "Evaluate: 1. Bugs / Edge Cases 2. Security 3. Performance 4. Verdict (APPROVED / CHANGES_REQUESTED)"
                )
                raw_review = self.driver.generate(prompt=prompt)
                is_approved = "APPROVED" in raw_review.upper() and "CHANGES_REQUESTED" not in raw_review.upper()

                # Post review comment
                self.client.post_review_comment(
                    pr_number=pr.number,
                    body=f"🤖 **K-CLI Autonomous PR Review**\n\n{raw_review}",
                    event="APPROVE" if is_approved else "COMMENT",
                )

                merged = False
                if is_approved and self.auto_merge_approved:
                    ci = self.client.get_ci_status(pr.head_sha)
                    if ci.all_passed:
                        merged = self.client.merge_pull_request(pr.number, merge_method="squash")

                self._processed_shas[pr.number] = pr.head_sha
                events.append(WatchEvent(
                    pr_number=pr.number,
                    pr_title=pr.title,
                    action_taken="reviewed_and_commented",
                    review_status="APPROVED" if is_approved else "COMMENTED",
                    auto_merged=merged,
                ))

            except Exception as ex:
                logger.error(f"Error reviewing PR #{pr.number}: {ex}")
                events.append(WatchEvent(
                    pr_number=pr.number,
                    pr_title=pr.title,
                    action_taken="review_failed",
                    review_status="ERROR",
                    error=str(ex),
                ))

        return events

    def run_loop(self, interval_seconds: int = 30, max_iterations: Optional[int] = None, callback: Optional[Callable[[WatchEvent], None]] = None) -> List[WatchEvent]:
        """Runs the watcher daemon loop."""
        all_events: List[WatchEvent] = []
        iteration = 0
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            events = self.poll_once()
            all_events.extend(events)
            if callback:
                for ev in events:
                    callback(ev)
            if max_iterations is not None and iteration >= max_iterations:
                break
            time.sleep(interval_seconds)
        return all_events
