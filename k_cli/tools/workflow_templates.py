"""Reusable workflow templates for common engineering operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    description: str
    steps: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
        }


WORKFLOW_TEMPLATES: Dict[str, WorkflowTemplate] = {
    "ci-triage": WorkflowTemplate(
        name="ci-triage",
        description="Investigate failing CI quickly and produce an actionable repair path.",
        steps=[
            "Run `k-cli doctor --json` to detect workspace and secret hygiene issues.",
            "Run `k-cli test` (or project test target) to reproduce failures locally.",
            "Run `k-cli review --json` to catch changed-file syntax and safety issues.",
            "Run `k-cli auto-heal <log_or_error>` for structured triage suggestions.",
            "Run `k-cli verify <file>` for any touched source before commit.",
        ],
    ),
    "release-prep": WorkflowTemplate(
        name="release-prep",
        description="Prepare a release with validation, changelog confidence, and repo hygiene.",
        steps=[
            "Run `k-cli doctor` and resolve any failing checks.",
            "Run `k-cli test` to validate full regression coverage.",
            "Run `k-cli security scan` and resolve high-severity findings.",
            "Run `k-cli hub` to inspect commit stream and branch health.",
            "Run `k-cli release list` to verify version sequencing before publish.",
        ],
    ),
    "incident-response": WorkflowTemplate(
        name="incident-response",
        description="Handle production-style incidents with repeatable triage and verified remediation.",
        steps=[
            "Collect stack trace or failure logs and run `k-cli auto-heal`.",
            "Use `k-cli explain` to inspect impacted architecture areas quickly.",
            "Use `k-cli verify` on proposed fixes with targeted tests.",
            "Run `k-cli immune <target_file>` to add defensive edge-case coverage.",
            "Document the fix path and validation outputs for postmortem handoff.",
        ],
    ),
}


def list_workflow_templates() -> List[WorkflowTemplate]:
    return [WORKFLOW_TEMPLATES[name] for name in sorted(WORKFLOW_TEMPLATES)]


def get_workflow_template(name: str) -> WorkflowTemplate | None:
    return WORKFLOW_TEMPLATES.get(name)
