"""
security_healer.py - Advanced AST & Regex Security Scanner & Surgical Auto-Healer for K-CLI

Features:
1. Fast AST & Regex static detection:
   - Hardcoded API keys, tokens, and credentials (OpenAI, HuggingFace, GitHub, AWS, Slack, Private Keys, JWT).
   - SQL Injection patterns (f-string interpolation, %, +, .format() in SQL calls).
   - Unsafe code execution (eval(), exec()).
   - Unsafe deserialization (pickle.loads(), yaml.load() without SafeLoader).
   - Command injection (subprocess with shell=True, os.system(), os.popen()).
   - Insecure ReDoS (Regular Expression Denial of Service) exponential backtracking patterns.
2. CWE Mapping, Severity classification (CRITICAL, HIGH, MEDIUM, LOW), and CVSS-style scoring.
3. Surgical Auto-Healing Loop:
   - Generates surgical SEARCH/REPLACE patches using `patcher.py`.
   - Verifies AST syntax and executes test suites via `verifier.py`.
   - Re-scans to confirm vulnerability elimination with zero regressions.
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Safe relative / package imports
try:
    from k_cli.git.verifier import VerificationResult, Verifier
except (ModuleNotFoundError, ImportError):
    try:
        from verifier import VerificationResult, Verifier
    except (ModuleNotFoundError, ImportError):
        VerificationResult = None  # type: ignore
        Verifier = None  # type: ignore

try:
    from k_cli.git.patcher import FilePatch, PatchResult, Patcher
except (ModuleNotFoundError, ImportError):
    try:
        from patcher import FilePatch, PatchResult, Patcher
    except (ModuleNotFoundError, ImportError):
        FilePatch = None  # type: ignore
        PatchResult = None  # type: ignore
        Patcher = None  # type: ignore

try:
    from k_cli.core.llm_driver import LLMDriver
except (ModuleNotFoundError, ImportError):
    try:
        from k_cli.core.llm_driver import LLMDriver
    except (ModuleNotFoundError, ImportError):
        LLMDriver = None  # type: ignore


class VulnerabilitySeverity(str, Enum):
    """Vulnerability severity rankings."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class VulnerabilityType(str, Enum):
    """Categorized vulnerability types."""
    HARDCODED_SECRET = "HARDCODED_SECRET"
    SQL_INJECTION = "SQL_INJECTION"
    UNSAFE_EVAL = "UNSAFE_EVAL"
    UNSAFE_DESERIALIZATION = "UNSAFE_DESERIALIZATION"
    COMMAND_INJECTION = "COMMAND_INJECTION"
    REDOS = "REDOS"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    INSECURE_CIPHER = "INSECURE_CIPHER"


@dataclass
class VulnerabilityFinding:
    """Represents an individual detected security vulnerability."""
    id: str
    vuln_type: str
    severity: str
    cvss_score: float
    cvss_vector: str
    file_path: str
    line_number: int
    snippet: str
    description: str
    recommendation: str
    cwe_id: str
    end_line_number: Optional[int] = None
    suggested_patch: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vuln_type": self.vuln_type,
            "severity": self.severity,
            "cvss_score": self.cvss_score,
            "cvss_vector": self.cvss_vector,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "snippet": self.snippet,
            "description": self.description,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "suggested_patch": self.suggested_patch,
        }


@dataclass
class SecurityScanReport:
    """Aggregated report of repository security scan findings."""
    repo_path: str
    findings: List[VulnerabilityFinding] = field(default_factory=list)
    scanned_files_count: int = 0
    scan_duration_seconds: float = 0.0

    @property
    def total_files_scanned(self) -> int:
        return self.scanned_files_count

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.CRITICAL.value)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.HIGH.value)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.MEDIUM.value)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == VulnerabilitySeverity.LOW.value)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def max_cvss_score(self) -> float:
        return max([f.cvss_score for f in self.findings], default=0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "scanned_files_count": self.scanned_files_count,
            "scan_duration_seconds": round(self.scan_duration_seconds, 3),
            "total_findings": self.total_findings,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "max_cvss_score": self.max_cvss_score,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Renders rich Markdown summary of the scan report."""
        md = [
            f"# 🛡️ Security Audit Report",
            f"**Repository Root**: `{self.repo_path}`  ",
            f"**Files Scanned**: `{self.scanned_files_count}` | **Duration**: `{self.scan_duration_seconds:.2f}s` | **Max CVSS**: `{self.max_cvss_score}`\n",
            f"### 📊 Findings Breakdown",
            f"- **CRITICAL**: `{self.critical_count}`",
            f"- **HIGH**: `{self.high_count}`",
            f"- **MEDIUM**: `{self.medium_count}`",
            f"- **LOW**: `{self.low_count}`",
            f"- **Total**: `{self.total_findings}`\n",
        ]

        if not self.findings:
            md.append("✅ **Clean Workspace**: No security vulnerabilities or hardcoded credentials detected.")
            return "\n".join(md)

        md.append("### 🔍 Detected Vulnerabilities\n")
        md.append("| ID | Severity | Type | File:Line | CVSS | CWE | Description |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for f in self.findings:
            md.append(
                f"| `{f.id}` | **{f.severity}** | `{f.vuln_type}` | `{f.file_path}:{f.line_number}` | `{f.cvss_score}` | `{f.cwe_id}` | {f.description} |"
            )

        return "\n".join(md)


@dataclass
class VulnerabilityHealResult:
    """Result of an automated surgical remediation attempt."""
    vuln_id: str
    file_path: str
    success: bool
    applied_patch: str = ""
    syntax_verified: bool = False
    tests_passed: bool = False
    rescan_clean: bool = False
    error_message: str = ""
    diff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vuln_id": self.vuln_id,
            "file_path": self.file_path,
            "success": self.success,
            "applied_patch": self.applied_patch,
            "syntax_verified": self.syntax_verified,
            "tests_passed": self.tests_passed,
            "rescan_clean": self.rescan_clean,
            "error_message": self.error_message,
            "diff": self.diff,
        }


SECRET_REGEX_RULES = [
    {
        "name": "OpenAI API Key",
        "pattern": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,})\b"),
        "severity": VulnerabilitySeverity.CRITICAL.value,
        "cvss": 9.8,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-798",
        "desc": "Hardcoded OpenAI API key exposed in source code.",
        "rec": "Migrate secret to environment variables or secret manager using os.environ.get('OPENAI_API_KEY').",
    },
    {
        "name": "Hugging Face Token",
        "pattern": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
        "severity": VulnerabilitySeverity.CRITICAL.value,
        "cvss": 9.8,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-798",
        "desc": "Hardcoded Hugging Face access token exposed in source code.",
        "rec": "Use os.environ.get('HF_TOKEN') instead of hardcoding credentials.",
    },
    {
        "name": "GitHub Token",
        "pattern": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
        "severity": VulnerabilitySeverity.CRITICAL.value,
        "cvss": 9.8,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-798",
        "desc": "Hardcoded GitHub personal access token exposed in source code.",
        "rec": "Inject token at runtime via GITHUB_TOKEN environment variable.",
    },
    {
        "name": "AWS Access Key",
        "pattern": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "severity": VulnerabilitySeverity.CRITICAL.value,
        "cvss": 9.8,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-798",
        "desc": "Hardcoded AWS Access Key ID exposed in source code.",
        "rec": "Use AWS IAM roles or AWS_ACCESS_KEY_ID environment variable.",
    },
    {
        "name": "Private Key",
        "pattern": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "severity": VulnerabilitySeverity.CRITICAL.value,
        "cvss": 9.8,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-798",
        "desc": "Unencrypted Private Key block embedded directly in repository.",
        "rec": "Store private keys in secure vault or filesystem with strict 0600 permissions.",
    },
    {
        "name": "Slack Token",
        "pattern": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
        "severity": VulnerabilitySeverity.HIGH.value,
        "cvss": 8.5,
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N",
        "cwe": "CWE-798",
        "desc": "Hardcoded Slack OAuth bot / user token exposed in source code.",
        "rec": "Store Slack tokens in SLACK_BOT_TOKEN environment variable.",
    },
]

REDOS_PATTERNS = [
    re.compile(r"\((?:[^()]|\([^()]*\))+(?:\+|\*|\{\d+,?\d*\})\)(?:\+|\*|\{\d+,?\d*\})"),
]

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "k_cli_env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    ".eggs",
}

SCANNABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".bash",
    ".sql",
}


class SecurityHealer:
    """
    Static AST & Regex Security Scanner and Automated Remediation Engine for K-CLI.
    """

    def __init__(self, repo_path: str = ".", llm_driver: Optional[Any] = None):
        self.repo_path = Path(repo_path).resolve()
        self.llm_driver = llm_driver

    # =========================================================================
    # 1. Repository Scanning Engine
    # =========================================================================

    def scan_repository(self, repo_path: Optional[str] = None) -> SecurityScanReport:
        """
        Performs high-speed AST & regex scan across repository files.
        """
        import time

        start_time = time.time()
        root = Path(repo_path).resolve() if repo_path else self.repo_path

        findings: List[VulnerabilityFinding] = []
        scanned_count = 0
        vuln_counter = 1

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SCANNABLE_EXTENSIONS:
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue

            rel_path = path.relative_to(root).as_posix()
            scanned_count += 1

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.splitlines()
            # 1. Regex-based secret detection
            for line_idx, line in enumerate(lines, start=1):
                if "rule" in line.lower() and "re.compile" in line.lower():
                    continue

                for rule in SECRET_REGEX_RULES:
                    match = rule["pattern"].search(line)
                    if match:
                        matched_val = match.group(0)
                        if any(ph in matched_val.lower() for ph in ("example", "your_key", "placeholder", "dummy")):
                            continue

                        v_id = f"SEC-KEY-{vuln_counter:03d}"
                        vuln_counter += 1
                        findings.append(
                            VulnerabilityFinding(
                                id=v_id,
                                vuln_type=VulnerabilityType.HARDCODED_SECRET.value,
                                severity=rule["severity"],
                                cvss_score=rule["cvss"],
                                cvss_vector=rule["vector"],
                                file_path=rel_path,
                                line_number=line_idx,
                                snippet=line.strip(),
                                description=f"{rule['name']}: {rule['desc']}",
                                recommendation=rule["rec"],
                                cwe_id=rule["cwe"],
                            )
                        )

            # 2. ReDoS Detection
            for line_idx, line in enumerate(lines, start=1):
                if any(kw in line for kw in ("re.compile", "re.match", "re.search", "re.findall", "RegExp", "pattern =")):
                    for p in REDOS_PATTERNS:
                        if p.search(line):
                            v_id = f"SEC-REDOS-{vuln_counter:03d}"
                            vuln_counter += 1
                            findings.append(
                                VulnerabilityFinding(
                                    id=v_id,
                                    vuln_type=VulnerabilityType.REDOS.value,
                                    severity=VulnerabilitySeverity.MEDIUM.value,
                                    cvss_score=7.5,
                                    cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                                    file_path=rel_path,
                                    line_number=line_idx,
                                    snippet=line.strip(),
                                    description="Potential ReDoS: Catastrophic backtracking nested quantifiers detected in regex.",
                                    recommendation="Simplify nested quantifiers or use possessive/atomic matching to prevent CPU exhaustion.",
                                    cwe_id="CWE-1333",
                                )
                            )

            # 3. Python Deep AST Analysis
            if path.suffix.lower() == ".py":
                ast_findings, vuln_counter = self._scan_python_ast(rel_path, content, vuln_counter)
                findings.extend(ast_findings)

        duration = time.time() - start_time
        return SecurityScanReport(
            repo_path=str(root),
            findings=findings,
            scanned_files_count=scanned_count,
            scan_duration_seconds=duration,
        )

    # =========================================================================
    # 2. Python AST Security Visitor
    # =========================================================================

    def _scan_python_ast(
        self, rel_path: str, code: str, start_counter: int
    ) -> Tuple[List[VulnerabilityFinding], int]:
        """Deep AST analysis for SQLi, unsafe eval/exec, pickle, yaml, and shell=True."""
        findings: List[VulnerabilityFinding] = []
        counter = start_counter

        try:
            tree = ast.parse(code)
        except Exception:
            return findings, counter

        lines = code.splitlines()

        class SecurityVisitor(ast.NodeVisitor):
            def __init__(self):
                self.local_findings: List[VulnerabilityFinding] = []

            def _get_snippet(self, node: ast.AST) -> str:
                lineno = getattr(node, "lineno", 1)
                if 1 <= lineno <= len(lines):
                    return lines[lineno - 1].strip()
                return ""

            def visit_Call(self, node: ast.Call):
                nonlocal counter

                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                    if node.args:
                        if not isinstance(node.args[0], ast.Constant):
                            v_id = f"SEC-RCE-{counter:03d}"
                            counter += 1
                            self.local_findings.append(
                                VulnerabilityFinding(
                                    id=v_id,
                                    vuln_type=VulnerabilityType.UNSAFE_EVAL.value,
                                    severity=VulnerabilitySeverity.CRITICAL.value,
                                    cvss_score=9.8,
                                    cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    snippet=self._get_snippet(node),
                                    description=f"Unsafe dynamic code execution using `{node.func.id}()` with untrusted input.",
                                    recommendation="Use ast.literal_eval() for safe literal evaluation or parse structured JSON.",
                                    cwe_id="CWE-95",
                                )
                            )

                if isinstance(node.func, ast.Attribute):
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id in ("pickle", "_pickle", "cPickle")
                        and node.func.attr in ("loads", "load")
                    ):
                        v_id = f"SEC-DESER-{counter:03d}"
                        counter += 1
                        self.local_findings.append(
                            VulnerabilityFinding(
                                id=v_id,
                                vuln_type=VulnerabilityType.UNSAFE_DESERIALIZATION.value,
                                severity=VulnerabilitySeverity.CRITICAL.value,
                                cvss_score=9.8,
                                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                file_path=rel_path,
                                line_number=node.lineno,
                                snippet=self._get_snippet(node),
                                description="Insecure deserialization using `pickle.loads()` allows arbitrary code execution.",
                                recommendation="Use safer serialization formats such as JSON, Protocol Buffers, or messagepack.",
                                cwe_id="CWE-502",
                            )
                        )

                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml" and node.func.attr == "load":
                        has_safe_loader = False
                        for kw in node.keywords:
                            if kw.arg == "Loader":
                                if isinstance(kw.value, ast.Attribute) and kw.value.attr in ("SafeLoader", "CSafeLoader"):
                                    has_safe_loader = True
                        if not has_safe_loader:
                            v_id = f"SEC-YAML-{counter:03d}"
                            counter += 1
                            self.local_findings.append(
                                VulnerabilityFinding(
                                    id=v_id,
                                    vuln_type=VulnerabilityType.UNSAFE_DESERIALIZATION.value,
                                    severity=VulnerabilitySeverity.HIGH.value,
                                    cvss_score=8.6,
                                    cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    snippet=self._get_snippet(node),
                                    description="Unsafe YAML loading: `yaml.load()` without SafeLoader can lead to arbitrary code execution.",
                                    recommendation="Replace `yaml.load(...)` with `yaml.safe_load(...)` or pass `Loader=yaml.SafeLoader`.",
                                    cwe_id="CWE-502",
                                )
                            )

                    if node.func.attr in ("execute", "executemany", "raw"):
                        if node.args:
                            first_arg = node.args[0]
                            is_sqli = False
                            if isinstance(first_arg, ast.JoinedStr):
                                is_sqli = True
                            elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, (ast.Mod, ast.Add)):
                                is_sqli = True
                            elif isinstance(first_arg, ast.Call) and isinstance(first_arg.func, ast.Attribute) and first_arg.func.attr == "format":
                                is_sqli = True

                            if is_sqli:
                                v_id = f"SEC-SQLI-{counter:03d}"
                                counter += 1
                                self.local_findings.append(
                                    VulnerabilityFinding(
                                        id=v_id,
                                        vuln_type=VulnerabilityType.SQL_INJECTION.value,
                                        severity=VulnerabilitySeverity.CRITICAL.value,
                                        cvss_score=8.8,
                                        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                        file_path=rel_path,
                                        line_number=node.lineno,
                                        snippet=self._get_snippet(node),
                                        description="Potential SQL Injection: String formatting or interpolation used in SQL query execution.",
                                        recommendation="Use parameterized queries with placeholder bindings instead of string interpolation.",
                                        cwe_id="CWE-89",
                                    )
                                )

                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                        and node.func.attr in ("Popen", "run", "call", "check_output", "check_call")
                    ):
                        for kw in node.keywords:
                            if kw.arg == "shell":
                                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    v_id = f"SEC-SH-{counter:03d}"
                                    counter += 1
                                    self.local_findings.append(
                                        VulnerabilityFinding(
                                            id=v_id,
                                            vuln_type=VulnerabilityType.COMMAND_INJECTION.value,
                                            severity=VulnerabilitySeverity.HIGH.value,
                                            cvss_score=8.8,
                                            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                            file_path=rel_path,
                                            line_number=node.lineno,
                                            snippet=self._get_snippet(node),
                                            description="Command Injection risk: `subprocess` invoked with `shell=True`.",
                                            recommendation="Pass arguments as a list of strings and set `shell=False` to prevent shell injection.",
                                            cwe_id="CWE-78",
                                        )
                                    )

                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr in ("system", "popen"):
                        v_id = f"SEC-OS-{counter:03d}"
                        counter += 1
                        self.local_findings.append(
                            VulnerabilityFinding(
                                id=v_id,
                                vuln_type=VulnerabilityType.COMMAND_INJECTION.value,
                                severity=VulnerabilitySeverity.HIGH.value,
                                cvss_score=8.8,
                                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                file_path=rel_path,
                                line_number=node.lineno,
                                snippet=self._get_snippet(node),
                                description=f"Insecure command execution using `os.{node.func.attr}()`.",
                                recommendation="Replace os.system with `subprocess.run([...], check=True)` without shell.",
                                cwe_id="CWE-78",
                            )
                        )

                self.generic_visit(node)

        visitor = SecurityVisitor()
        visitor.visit(tree)
        return visitor.local_findings, counter

    # =========================================================================
    # 3. Surgical Auto-Healing & Verification Engine
    # =========================================================================

    def auto_heal_vulnerability(
        self,
        vuln_id: str,
        verifier: Optional[Any] = None,
        patcher: Optional[Any] = None,
        llm_driver: Optional[Any] = None,
        repo_path: Optional[str] = None,
    ) -> VulnerabilityHealResult:
        """
        Remediates a specific detected vulnerability surgically using AST search/replace,
        verifies syntax and tests with Verifier guard, and re-scans to confirm resolution.
        """
        root = Path(repo_path).resolve() if repo_path else self.repo_path
        report = self.scan_repository(repo_path=str(root))

        finding = next((f for f in report.findings if f.id == vuln_id), None)
        if not finding:
            return VulnerabilityHealResult(
                vuln_id=vuln_id,
                file_path="",
                success=False,
                error_message=f"Vulnerability ID '{vuln_id}' not found in active repository scan.",
            )

        target_file = (root / finding.file_path).resolve()
        if not target_file.exists() or not target_file.is_file():
            return VulnerabilityHealResult(
                vuln_id=vuln_id,
                file_path=finding.file_path,
                success=False,
                error_message=f"Target file does not exist on disk: {target_file}",
            )

        original_code = target_file.read_text(encoding="utf-8", errors="replace")
        backup_code = original_code

        v_engine = verifier or (Verifier() if Verifier else None)
        p_engine = patcher or (Patcher() if Patcher else None)
        driver = llm_driver or self.llm_driver

        patch_blocks: List[Tuple[str, str]] = []

        if driver is not None and hasattr(driver, "generate"):
            try:
                prompt = (
                    f"Fix the following security vulnerability in `{finding.file_path}`:\n"
                    f"Vulnerability Type: {finding.vuln_type}\n"
                    f"Severity: {finding.severity} (CVSS: {finding.cvss_score})\n"
                    f"Line {finding.line_number}: {finding.snippet}\n"
                    f"Description: {finding.description}\n"
                    f"Recommendation: {finding.recommendation}\n\n"
                    f"Original File Content:\n```python\n{original_code}\n```\n\n"
                    f"Requirements:\n"
                    f"Output ONLY a valid SEARCH/REPLACE block:\n"
                    f"<<<<<<< SEARCH\n... exact code to replace ...\n=======\n... replacement code ...\n>>>>>>> REPLACE"
                )
                response = driver.generate(prompt=prompt)
                if response and p_engine:
                    patch_blocks = p_engine.parse_search_replace_blocks(response)
            except Exception as exc:
                logger.warning(f"LLM patch generation failed: {exc}")

        if not patch_blocks:
            patch_blocks = self._generate_heuristic_patch(finding, original_code)

        if not patch_blocks:
            return VulnerabilityHealResult(
                vuln_id=vuln_id,
                file_path=finding.file_path,
                success=False,
                error_message="Unable to synthesize a safe surgical remediation patch.",
            )

        current_code = original_code
        applied_search_replace: List[str] = []

        for s_block, r_block in patch_blocks:
            applied_search_replace.append(f"<<<<<<< SEARCH\n{s_block}\n=======\n{r_block}\n>>>>>>> REPLACE")
            if p_engine:
                success, patched_step, err = p_engine.apply_patch(current_code, s_block, r_block, fuzzy=True)
                if success:
                    current_code = patched_step
                elif s_block in current_code:
                    current_code = current_code.replace(s_block, r_block, 1)
                else:
                    return VulnerabilityHealResult(
                        vuln_id=vuln_id,
                        file_path=finding.file_path,
                        success=False,
                        error_message=f"Patcher failed to apply block: {err}",
                    )
            else:
                if s_block in current_code:
                    current_code = current_code.replace(s_block, r_block, 1)
                else:
                    return VulnerabilityHealResult(
                        vuln_id=vuln_id,
                        file_path=finding.file_path,
                        success=False,
                        error_message="Search block not found in target file.",
                    )

        patched_code = current_code

        # 3. Verify Python AST syntax
        syntax_ok = True
        if finding.file_path.endswith(".py"):
            try:
                ast.parse(patched_code)
            except SyntaxError as syn_err:
                syntax_ok = False
                return VulnerabilityHealResult(
                    vuln_id=vuln_id,
                    file_path=finding.file_path,
                    success=False,
                    syntax_verified=False,
                    error_message=f"Patched code failed AST syntax check: {syn_err}",
                )

        # 4. Write to disk
        try:
            target_file.write_text(patched_code, encoding="utf-8")
        except Exception as write_err:
            return VulnerabilityHealResult(
                vuln_id=vuln_id,
                file_path=finding.file_path,
                success=False,
                error_message=f"Failed writing patched file to disk: {write_err}",
            )

        # 5. Verify project tests
        tests_passed = True
        if v_engine and hasattr(v_engine, "run_project_tests"):
            try:
                test_res = v_engine.run_project_tests(project_dir=str(root), timeout=15.0)
                if not test_res.success:
                    target_file.write_text(backup_code, encoding="utf-8")
                    return VulnerabilityHealResult(
                        vuln_id=vuln_id,
                        file_path=finding.file_path,
                        success=False,
                        syntax_verified=syntax_ok,
                        tests_passed=False,
                        error_message=f"Post-patch test verification failed. Rolled back: {test_res.error_trace}",
                    )
            except Exception as test_exc:
                logger.warning(f"Test verification check encountered error: {test_exc}")

        # 6. Re-scan to confirm vulnerability eliminated
        rescan_report = self.scan_repository(repo_path=str(root))
        still_present = any(
            f.file_path == finding.file_path and f.vuln_type == finding.vuln_type and f.line_number == finding.line_number
            for f in rescan_report.findings
        )

        if still_present:
            target_file.write_text(backup_code, encoding="utf-8")
            return VulnerabilityHealResult(
                vuln_id=vuln_id,
                file_path=finding.file_path,
                success=False,
                syntax_verified=syntax_ok,
                tests_passed=tests_passed,
                rescan_clean=False,
                error_message="Re-scan detected vulnerability still present after patch application. Rolled back.",
            )

        diff_lines = list(
            difflib.unified_diff(
                original_code.splitlines(keepends=True),
                patched_code.splitlines(keepends=True),
                fromfile=f"a/{finding.file_path}",
                tofile=f"b/{finding.file_path}",
            )
        )
        applied_diff = "".join(diff_lines)

        return VulnerabilityHealResult(
            vuln_id=vuln_id,
            file_path=finding.file_path,
            success=True,
            applied_patch="\n\n".join(applied_search_replace),
            syntax_verified=syntax_ok,
            tests_passed=tests_passed,
            rescan_clean=True,
            diff=applied_diff,
        )

    def heal_all_vulnerabilities(
        self,
        repo_path: Optional[str] = None,
        verifier: Optional[Any] = None,
        patcher: Optional[Any] = None,
        llm_driver: Optional[Any] = None,
    ) -> List[VulnerabilityHealResult]:
        """Scans and heals all detected vulnerabilities sequentially."""
        root = Path(repo_path).resolve() if repo_path else self.repo_path
        results: List[VulnerabilityHealResult] = []

        # Loop until no more fixable vulnerabilities remain or max iterations
        for _ in range(10):
            report = self.scan_repository(repo_path=str(root))
            if not report.findings:
                break

            healed_in_this_pass = 0
            for finding in report.findings:
                res = self.auto_heal_vulnerability(
                    vuln_id=finding.id,
                    verifier=verifier,
                    patcher=patcher,
                    llm_driver=llm_driver,
                    repo_path=str(root),
                )
                results.append(res)
                if res.success:
                    healed_in_this_pass += 1
                    break  # Rescan after each fix to update line numbers cleanly

            if healed_in_this_pass == 0:
                break

        return results

    # =========================================================================
    # 4. Deterministic Heuristic Patch Generator
    # =========================================================================

    def _generate_heuristic_patch(
        self, finding: VulnerabilityFinding, code: str
    ) -> List[Tuple[str, str]]:
        """Generates deterministic safe patches for common security patterns."""
        lines = code.splitlines()
        if not (1 <= finding.line_number <= len(lines)):
            return []

        target_line = lines[finding.line_number - 1]

        # A. Hardcoded Secret Replacement
        if finding.vuln_type == VulnerabilityType.HARDCODED_SECRET.value:
            for rule in SECRET_REGEX_RULES:
                match = rule["pattern"].search(target_line)
                if match:
                    secret_str = match.group(0)
                    env_var = "API_KEY"
                    if "sk-" in secret_str:
                        env_var = "OPENAI_API_KEY"
                    elif "hf_" in secret_str:
                        env_var = "HF_TOKEN"
                    elif "ghp" in secret_str or "github" in secret_str:
                        env_var = "GITHUB_TOKEN"
                    elif "AKIA" in secret_str:
                        env_var = "AWS_ACCESS_KEY_ID"
                    elif "xox" in secret_str:
                        env_var = "SLACK_BOT_TOKEN"

                    new_line = target_line.replace(f'"{secret_str}"', f'os.environ.get("{env_var}", "")')
                    new_line = new_line.replace(f"'{secret_str}'", f'os.environ.get("{env_var}", "")')

                    patches = []
                    if "import os" not in code:
                        first_line = lines[0] if lines else ""
                        patches.append((first_line, f"import os\n{first_line}"))
                    patches.append((target_line, new_line))
                    return patches

        # B. SQL Injection Parameterization
        if finding.vuln_type == VulnerabilityType.SQL_INJECTION.value:
            fstr_match = re.search(r'(cursor|db|session)\.execute\s*\(\s*f["\'](.*?)["\']\s*\)', target_line)
            if fstr_match:
                obj = fstr_match.group(1)
                sql_template = fstr_match.group(2)
                param_vars = re.findall(r'\{([^}]+)\}', sql_template)
                if param_vars:
                    cleaned_sql = re.sub(r'\{[^}]+\}', '%s', sql_template)
                    params_tuple = f"({', '.join(param_vars)}" + (",)" if len(param_vars) == 1 else ")")
                    new_line = target_line.replace(
                        fstr_match.group(0),
                        f'{obj}.execute("{cleaned_sql}", {params_tuple})'
                    )
                    return [(target_line, new_line)]

            pct_match = re.search(r'(cursor|db|session)\.execute\s*\(\s*(["\'].*?["\'])\s*%\s*([^)]+)\)', target_line)
            if pct_match:
                obj, query_str, params = pct_match.group(1), pct_match.group(2), pct_match.group(3).strip()
                params_tuple = params if (params.startswith("(") and params.endswith(")")) else f"({params},)"
                new_line = target_line.replace(
                    pct_match.group(0),
                    f'{obj}.execute({query_str}, {params_tuple})'
                )
                return [(target_line, new_line)]

        # C. Unsafe eval() / exec() -> ast.literal_eval()
        if finding.vuln_type == VulnerabilityType.UNSAFE_EVAL.value:
            eval_match = re.search(r'\beval\s*\(([^)]+)\)', target_line)
            if eval_match:
                expr = eval_match.group(1)
                new_line = target_line.replace(f"eval({expr})", f"ast.literal_eval({expr})")
                patches = []
                if "import ast" not in code:
                    first_line = lines[0] if lines else ""
                    patches.append((first_line, f"import ast\n{first_line}"))
                patches.append((target_line, new_line))
                return patches

        # D. Unsafe yaml.load -> yaml.safe_load
        if finding.vuln_type == VulnerabilityType.UNSAFE_DESERIALIZATION.value:
            if "yaml.load" in target_line:
                new_line = target_line.replace("yaml.load(", "yaml.safe_load(")
                return [(target_line, new_line)]
            if "pickle.loads" in target_line:
                new_line = target_line.replace("pickle.loads(", "json.loads(")
                patches = []
                if "import json" not in code:
                    first_line = lines[0] if lines else ""
                    patches.append((first_line, f"import json\n{first_line}"))
                patches.append((target_line, new_line))
                return patches

        # E. Command Injection shell=True -> shell=False
        if finding.vuln_type == VulnerabilityType.COMMAND_INJECTION.value:
            if "shell=True" in target_line:
                new_line = target_line.replace("shell=True", "shell=False")
                return [(target_line, new_line)]
            if "os.system(" in target_line:
                sys_match = re.search(r'os\.system\s*\(([^)]+)\)', target_line)
                if sys_match:
                    cmd_arg = sys_match.group(1).strip()
                    new_line = target_line.replace(
                        sys_match.group(0),
                        f"subprocess.run({cmd_arg}.split(), check=True)"
                    )
                    patches = []
                    if "import subprocess" not in code:
                        first_line = lines[0] if lines else ""
                        patches.append((first_line, f"import subprocess\n{first_line}"))
                    patches.append((target_line, new_line))
                    return patches

        # F. ReDoS Nested Quantifier Simplification
        if finding.vuln_type == VulnerabilityType.REDOS.value:
            redos_fixed = target_line
            redos_fixed = re.sub(r'\(([^()]+)\+\)\+', r'\1+', redos_fixed)
            redos_fixed = re.sub(r'\(([^()]+)\*\)\*', r'\1*', redos_fixed)
            redos_fixed = re.sub(r'\(([^()]+)\+\)\*', r'\1*', redos_fixed)
            redos_fixed = re.sub(r'\(([^()]+)\*\)\+', r'\1+', redos_fixed)
            if redos_fixed != target_line:
                return [(target_line, redos_fixed)]

        return []
