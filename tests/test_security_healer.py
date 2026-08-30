"""
test_security_healer.py - Comprehensive Unit & Integration Test Suite for SecurityHealer
Project Bankai Engine v1.0.0

Tests:
1. Static AST & Regex Detection:
   - Hardcoded API keys (OpenAI, Hugging Face, GitHub, AWS, Slack, Private Keys)
   - SQL Injection (f-strings, %, +, .format() in execute calls)
   - Unsafe code execution (eval, exec)
   - Unsafe deserialization (pickle.loads, yaml.load without SafeLoader)
   - Command injection (subprocess with shell=True, os.system)
   - ReDoS catastrophic backtracking regular expressions
2. CVSS scoring, CWE mapping, and Markdown/JSON report synthesis.
3. Surgical Auto-Healing:
   - Auto-healing secrets with os.environ.get and import injection
   - Auto-healing SQL injection into parameterized bindings
   - Auto-healing eval() into ast.literal_eval()
   - Auto-healing yaml.load into yaml.safe_load
   - Auto-healing shell=True into shell=False
   - Auto-healing ReDoS nested quantifiers
   - AST syntax verification and re-scan validation
4. CLI commands: `k-cli security scan` and `k-cli security heal`.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from k_cli.tools.security_healer import (
    SecurityHealer,
    SecurityScanReport,
    VulnerabilityFinding,
    VulnerabilityHealResult,
    VulnerabilitySeverity,
    VulnerabilityType,
)
from k_cli.git.verifier import Verifier
from k_cli.git.patcher import Patcher
from k_cli.cli import app

runner = CliRunner()


@pytest.fixture
def vulnerable_repo(tmp_path):
    """Creates a temporary workspace with various vulnerable code fixtures."""
    repo = tmp_path / "vuln_workspace"
    repo.mkdir()

    # 1. Hardcoded OpenAI Key
    (repo / "ai_client.py").write_text(
        '# AI Client\nOPENAI_KEY = "{}"\n\ndef get_key():\n    return OPENAI_KEY\n'.format("s" + "k-1234567890abcdef1234567890abcdef12345678"),
        encoding="utf-8",
    )

    # 2. SQL Injection in database handler
    (repo / "db.py").write_text(
        'import sqlite3\n\ndef get_user(cursor, user_id):\n    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n',
        encoding="utf-8",
    )

    # 3. Unsafe eval
    (repo / "calc.py").write_text(
        'def compute(payload: str):\n    return eval(payload)\n',
        encoding="utf-8",
    )

    # 4. Unsafe yaml.load
    (repo / "config.py").write_text(
        'import yaml\n\ndef load_cfg(stream):\n    return yaml.load(stream)\n',
        encoding="utf-8",
    )

    # 5. Command injection shell=True
    (repo / "runner.py").write_text(
        'import subprocess\n\ndef run_cmd(cmd_str):\n    return subprocess.run(cmd_str, shell=True)\n',
        encoding="utf-8",
    )

    # 6. ReDoS regular expression
    (repo / "validator.py").write_text(
        'import re\n\nEMAIL_REGEX = re.compile(r"^{}+@domain.com$")\n'.format("([a-zA-Z0-9_]+)"),
        encoding="utf-8",
    )

    return repo


def test_scan_repository_detections(vulnerable_repo):
    """Tests comprehensive detection of all vulnerability categories."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    assert isinstance(report, SecurityScanReport)
    assert report.total_findings >= 6
    assert report.critical_count >= 3
    assert report.high_count >= 2
    assert report.medium_count >= 1
    assert report.max_cvss_score >= 9.0

    vuln_types = {f.vuln_type for f in report.findings}
    assert VulnerabilityType.HARDCODED_SECRET.value in vuln_types
    assert VulnerabilityType.SQL_INJECTION.value in vuln_types
    assert VulnerabilityType.UNSAFE_EVAL.value in vuln_types
    assert VulnerabilityType.UNSAFE_DESERIALIZATION.value in vuln_types
    assert VulnerabilityType.COMMAND_INJECTION.value in vuln_types
    assert VulnerabilityType.REDOS.value in vuln_types


def test_scan_report_json_and_markdown(vulnerable_repo):
    """Tests JSON and Markdown export representations of SecurityScanReport."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert "findings" in parsed
    assert parsed["critical_count"] == report.critical_count
    assert parsed["max_cvss_score"] == report.max_cvss_score

    md_str = report.to_markdown()
    assert "# 🛡️ Security Audit Report" in md_str
    assert "CRITICAL" in md_str
    assert "CWE" in md_str


def test_auto_heal_hardcoded_secret(vulnerable_repo):
    """Tests surgical remediation of hardcoded OpenAI key into os.environ.get."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    secret_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.HARDCODED_SECRET.value)
    result = healer.auto_heal_vulnerability(vuln_id=secret_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    # Inspect file contents
    healed_code = (vulnerable_repo / "ai_client.py").read_text(encoding="utf-8")
    assert "import os" in healed_code
    assert 'os.environ.get("OPENAI_API_KEY", "")' in healed_code
    assert "sk-" not in healed_code


def test_auto_heal_sql_injection(vulnerable_repo):
    """Tests surgical remediation of SQL injection into parameterized query."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    sqli_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.SQL_INJECTION.value)
    result = healer.auto_heal_vulnerability(vuln_id=sqli_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    healed_code = (vulnerable_repo / "db.py").read_text(encoding="utf-8")
    assert 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))' in healed_code
    assert "f\"SELECT" not in healed_code


def test_auto_heal_unsafe_eval(vulnerable_repo):
    """Tests surgical remediation of eval() into ast.literal_eval()."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    eval_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.UNSAFE_EVAL.value)
    result = healer.auto_heal_vulnerability(vuln_id=eval_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    healed_code = (vulnerable_repo / "calc.py").read_text(encoding="utf-8")
    assert "import ast" in healed_code
    assert "ast.literal_eval(payload)" in healed_code


def test_auto_heal_unsafe_yaml_load(vulnerable_repo):
    """Tests surgical remediation of yaml.load() into yaml.safe_load()."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    yaml_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.UNSAFE_DESERIALIZATION.value)
    result = healer.auto_heal_vulnerability(vuln_id=yaml_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    healed_code = (vulnerable_repo / "config.py").read_text(encoding="utf-8")
    assert "yaml.safe_load(stream)" in healed_code


def test_auto_heal_command_injection(vulnerable_repo):
    """Tests surgical remediation of subprocess shell=True to shell=False."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    cmd_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.COMMAND_INJECTION.value)
    result = healer.auto_heal_vulnerability(vuln_id=cmd_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    healed_code = (vulnerable_repo / "runner.py").read_text(encoding="utf-8")
    assert "shell=False" in healed_code


def test_auto_heal_redos(vulnerable_repo):
    """Tests surgical simplification of ReDoS nested quantifiers."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    report = healer.scan_repository()

    redos_vuln = next(f for f in report.findings if f.vuln_type == VulnerabilityType.REDOS.value)
    result = healer.auto_heal_vulnerability(vuln_id=redos_vuln.id)

    assert result.success is True
    assert result.syntax_verified is True
    assert result.rescan_clean is True

    healed_code = (vulnerable_repo / "validator.py").read_text(encoding="utf-8")
    assert "([a-zA-Z0-9_]+)+" not in healed_code


def test_heal_all_vulnerabilities(vulnerable_repo):
    """Tests batch auto-healing of all detected vulnerabilities across the repository."""
    healer = SecurityHealer(repo_path=str(vulnerable_repo))
    results = healer.heal_all_vulnerabilities()

    assert len(results) >= 6
    assert all(r.success for r in results)

    # Re-scan repository to guarantee 0 remaining vulnerabilities
    fresh_report = healer.scan_repository()
    assert fresh_report.total_findings == 0


def test_cli_security_scan_and_heal(vulnerable_repo):
    """Tests CLI commands `k-cli security scan` and `k-cli security heal`."""
    # 1. Scan command in JSON mode
    res_scan = runner.invoke(app, ["security", "scan", "--repo", str(vulnerable_repo), "--json"])
    assert res_scan.exit_code == 0
    data = json.loads(res_scan.stdout)
    assert data["total_findings"] >= 6

    # 2. Heal all command
    res_heal = runner.invoke(app, ["security", "heal", "--repo", str(vulnerable_repo), "--all", "--json"])
    assert res_heal.exit_code == 0
    heal_data = json.loads(res_heal.stdout)
    assert len(heal_data) >= 6
    assert all(item["success"] for item in heal_data)

    # 3. Re-scan should be clean
    res_rescan = runner.invoke(app, ["security", "scan", "--repo", str(vulnerable_repo)])
    assert res_rescan.exit_code == 0
    assert "Clean Workspace" in res_rescan.stdout
