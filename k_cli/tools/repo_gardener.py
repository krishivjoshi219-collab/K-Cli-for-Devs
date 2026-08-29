"""
repo_gardener.py - Nightly Autonomous Repo Maintenance & Health Engine for K-CLI
Project Bankai v1.0.0

Scans repository for dead code, unreferenced symbols, outdated dependencies,
untracked technical debt, and formats actionable cleanup PRs.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from k_cli.git.repo_map import RepoMap


@dataclass
class GardenFinding:
    """A single technical debt or hygiene finding."""
    category: str  # "dead_code", "outdated_dependency", "stale_branch", "security_hygiene"
    file_path: str
    symbol_or_item: str
    message: str
    severity: str = "MEDIUM"  # "HIGH", "MEDIUM", "LOW"
    suggested_action: str = ""


@dataclass
class GardenReport:
    """Consolidated repo hygiene and maintenance report."""
    total_files_scanned: int
    total_findings: int
    findings: List[GardenFinding] = field(default_factory=list)
    dead_code_count: int = 0
    dependency_issues: int = 0
    health_score: float = 100.0  # 0 to 100

    def render_markdown(self) -> str:
        """Renders formatted markdown report."""
        lines = [
            f"# 🌿 K-CLI Repo Health & Maintenance Report",
            f"**Overall Health Score**: `{self.health_score:.1f}/100` | **Files Scanned**: {self.total_files_scanned} | **Total Findings**: {self.total_findings}",
            "",
            "## Summary",
            f"- 🧹 **Dead / Unused Functions**: {self.dead_code_count}",
            f"- 📦 **Dependency Issues**: {self.dependency_issues}",
            "",
            "## Detailed Findings",
        ]
        if not self.findings:
            lines.append("✨ Workspace is perfectly pruned! Zero technical debt detected.")
        else:
            for f in self.findings:
                lines.append(f"- **[{f.severity}]** `{f.file_path}`: `{f.symbol_or_item}` — {f.message} *(Fix: {f.suggested_action})*")
        return "\n".join(lines)


class RepoGardener:
    """
    Autonomous Repository Maintenance Gardener.
    """

    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()

    def scan_dead_code(self) -> List[GardenFinding]:
        """Scans python codebase for defined functions never referenced across the project."""
        findings: List[GardenFinding] = []
        defined_functions: Dict[str, Tuple[str, int]] = {}  # name -> (file_path, lineno)
        ignored_dirs = {".venv", "k_cli_env", ".git", ".pytest_cache", "__pycache__", "build", "dist", "data"}
        py_files = [
            p for p in self.repo_path.rglob("*.py")
            if not any(ig in p.parts for ig in ignored_dirs) and not p.name.startswith("test_")
        ]

        for p in py_files[:100]:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                all_code_text += "\n" + content
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and node.name not in ("main", "app", "compose", "on_mount"):
                        defined_functions[node.name] = (str(p.relative_to(self.repo_path)), node.lineno)
            except Exception:
                pass

        for func_name, (rel_path, lineno) in defined_functions.items():
            occurrences = len(re.findall(r"\b" + re.escape(func_name) + r"\b", all_code_text))
            if occurrences <= 1:  # Only occurs at its own definition
                findings.append(GardenFinding(
                    category="dead_code",
                    file_path=f"{rel_path}:{lineno}",
                    symbol_or_item=func_name,
                    message=f"Function `{func_name}` appears unreferenced anywhere else in project.",
                    severity="LOW",
                    suggested_action=f"Safe to remove or mark private `_{func_name}`",
                ))

        return findings

    def scan_dependencies(self) -> List[GardenFinding]:
        """Inspects pyproject.toml or requirements.txt for unpinned or obsolete libraries."""
        findings: List[GardenFinding] = []
        req_file = self.repo_path / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if "==" not in line and ">=" not in line:
                        findings.append(GardenFinding(
                            category="outdated_dependency",
                            file_path="requirements.txt",
                            symbol_or_item=line,
                            message=f"Dependency `{line}` lacks version pin.",
                            severity="MEDIUM",
                            suggested_action=f"Pin to minimum supported version e.g. `{line}>=1.0.0`",
                        ))
        return findings

    def run_garden_sweep(self) -> GardenReport:
        """Executes full repo garden sweep."""
        dead_code = self.scan_dead_code()
        dep_issues = self.scan_dependencies()

        all_findings = dead_code + dep_issues
        total_files = len(list(self.repo_path.rglob("*.py")))

        score = max(0.0, 100.0 - (len(dead_code) * 2.5) - (len(dep_issues) * 5.0))

        return GardenReport(
            total_files_scanned=total_files,
            total_findings=len(all_findings),
            findings=all_findings,
            dead_code_count=len(dead_code),
            dependency_issues=len(dep_issues),
            health_score=score,
        )
