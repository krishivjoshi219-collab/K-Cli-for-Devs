"""Small, dependency-free secret hygiene checks for K-CLI workspaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


IGNORED = {".git", ".venv", "venv", "k_cli_env", "node_modules", "__pycache__", "data"}
SOURCE_SUFFIXES = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".sh"}
RULES = {
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


@dataclass(frozen=True)
class SecurityFinding:
    path: str
    line: int
    rule: str


def scan_workspace(root_dir: str | Path = ".", max_findings: int = 25) -> List[SecurityFinding]:
    """Find likely committed credentials without returning sensitive values."""
    root = Path(root_dir).resolve()
    findings: List[SecurityFinding] = []
    for path in root.rglob("*"):
        if len(findings) >= max_findings:
            break
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in IGNORED for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for rule_name, pattern in RULES.items():
                if pattern.search(line):
                    findings.append(SecurityFinding(path=path.relative_to(root).as_posix(), line=line_number, rule=rule_name))
                    if len(findings) >= max_findings:
                        break
            if len(findings) >= max_findings:
                break
    return findings
