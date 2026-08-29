"""
test_incident_triage.py - Comprehensive Unit Tests for Incident Triage & Auto-Heal Engine
"""

import ast
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k_cli.tools.incident_triage import (
    IncidentHealResult,
    IncidentReport,
    IncidentTriageEngine,
    LogType,
    StackFrame,
)
from k_cli.git.patcher import Patcher
from k_cli.git.verifier import VerificationResult, Verifier


@pytest.fixture
def temp_workspace():
    """Creates a temporary workspace with sample multi-language source files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Python source file
        py_file = tmp_path / "math_service.py"
        py_file.write_text(
            "class MathService:\n"
            "    def calculate_average(self, numbers):\n"
            "        total = sum(numbers)\n"
            "        count = len(numbers)\n"
            "        return total / count\n\n"
            "    def get_user_value(self, user_dict, key):\n"
            "        return user_dict[key]\n",
            encoding="utf-8",
        )

        # JS source file
        js_file = tmp_path / "index.js"
        js_file.write_text(
            "function processUser(user) {\n"
            "    return user.profile.name;\n"
            "}\n",
            encoding="utf-8",
        )

        # Rust source file
        rs_file = tmp_path / "main.rs"
        rs_file.write_text(
            "fn compute() {\n"
            "    let opt: Option<i32> = None;\n"
            "    let val = opt.unwrap();\n"
            "}\n",
            encoding="utf-8",
        )

        # Go source file
        go_file = tmp_path / "main.go"
        go_file.write_text(
            "package main\n"
            "func processItem(items []string) string {\n"
            "    return items[5]\n"
            "}\n",
            encoding="utf-8",
        )

        # C++ source file
        cpp_file = tmp_path / "server.cpp"
        cpp_file.write_text(
            "#include <iostream>\n"
            "void handle_packet(int* ptr) {\n"
            "    *ptr = 42;\n"
            "}\n",
            encoding="utf-8",
        )

        yield tmp_path


# =============================================================================
# 1. Python Traceback Parsing Tests
# =============================================================================

def test_parse_python_traceback_standard(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{temp_workspace}/math_service.py", line 5, in calculate_average\n'
        "    return total / count\n"
        "ZeroDivisionError: division by zero\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.PYTHON_TRACEBACK.value
    assert report.exception_type == "ZeroDivisionError"
    assert report.error_message == "division by zero"
    assert report.culprit_file == "math_service.py"
    assert report.culprit_line == 5
    assert report.culprit_symbol == "MathService.calculate_average"
    assert "division by zero" in report.root_cause_analysis.lower()
    assert report.severity in ("HIGH", "CRITICAL")
    assert len(report.reproduction_steps) > 0
    assert "math_service.py" in report.code_snippets


def test_parse_python_pytest_failure(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "FAILED tests/test_calc.py::test_division - ZeroDivisionError: division by zero\n"
        "math_service.py:5: ZeroDivisionError\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.PYTHON_TRACEBACK.value
    assert report.exception_type == "ZeroDivisionError"
    assert report.culprit_file == "math_service.py"
    assert report.culprit_line == 5


def test_parse_python_attribute_error(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{temp_workspace}/math_service.py", line 8, in get_user_value\n'
        "    return user_dict[key]\n"
        "AttributeError: 'NoneType' object has no attribute 'profile'\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.exception_type == "AttributeError"
    assert "NoneType" in report.error_message
    assert report.culprit_symbol == "MathService.get_user_value"


# =============================================================================
# 2. Node.js / TypeScript Stack Trace Tests
# =============================================================================

def test_parse_nodejs_stacktrace(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "TypeError: Cannot read properties of undefined (reading 'name')\n"
        f"    at processUser ({temp_workspace}/index.js:2:19)\n"
        "    at Module._compile (node:internal/modules/cjs/loader:1256:14)\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.NODE_STACK_TRACE.value
    assert report.exception_type == "TypeError"
    assert "Cannot read properties of undefined" in report.error_message
    assert report.culprit_file == "index.js"
    assert report.culprit_line == 2
    assert report.culprit_column == 19
    assert report.culprit_symbol == "processUser"


# =============================================================================
# 3. Rust Panic Parsing Tests
# =============================================================================

def test_parse_rust_panic(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        f"thread 'main' panicked at 'called Option::unwrap() on a None value', {temp_workspace}/main.rs:3:15\n"
        "stack backtrace:\n"
        "   0: rust_begin_unwind\n"
        f"   1: compute\n      at {temp_workspace}/main.rs:3:15\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.RUST_PANIC.value
    assert "RustPanic" in report.exception_type or "panic" in report.exception_type.lower()
    assert "called Option::unwrap() on a None value" in report.error_message
    assert report.culprit_file == "main.rs"
    assert report.culprit_line == 3
    assert report.severity in ("CRITICAL", "HIGH")


# =============================================================================
# 4. Go Panic Parsing Tests
# =============================================================================

def test_parse_go_panic(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "panic: runtime error: index out of range [5] with length 2\n\n"
        "goroutine 1 [running]:\n"
        "main.processItem(0x0, 0x0)\n"
        f"\t{temp_workspace}/main.go:3 +0x39\n"
        "main.main()\n"
        f"\t{temp_workspace}/main.go:8 +0x24\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.GO_PANIC.value
    assert "index out of range" in report.error_message
    assert report.culprit_file == "main.go"
    assert report.culprit_line == 8 or report.culprit_line == 3


# =============================================================================
# 5. C++ Crash / ASAN / Core Dump Tests
# =============================================================================

def test_parse_cpp_asan_crash(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "=================================================================\n"
        "==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000014\n"
        "WRITE of size 4 at 0x602000000014 thread T0\n"
        f"    #0 0x55d7f1 in handle_packet {temp_workspace}/server.cpp:3:11\n"
        f"    #1 0x55d8e2 in main {temp_workspace}/server.cpp:10:5\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.CPP_CRASH.value
    assert "ASAN" in report.exception_type
    assert report.culprit_file == "server.cpp"
    assert report.culprit_line in (3, 10)
    assert report.severity == "CRITICAL"


def test_parse_cpp_segfault():
    engine = IncidentTriageEngine()

    raw_trace = (
        "Program received signal SIGSEGV, Segmentation fault.\n"
        "0x0000555555555189 in crash_func () at src/crash.cpp:12\n"
        "12\t    *ptr = 0;\n"
    )

    report = engine.triage_log_or_trace(raw_trace)

    assert report.log_type == LogType.CPP_CRASH.value
    assert report.exception_type == "SIGSEGV"
    assert report.severity == "CRITICAL"


def test_parse_cpp_std_terminate():
    engine = IncidentTriageEngine()

    raw_trace = (
        "terminate called after throwing an instance of 'std::runtime_error'\n"
        "  what(): database connection timeout on port 5432\n"
        "Aborted (core dumped)\n"
    )

    report = engine.triage_log_or_trace(raw_trace)

    assert report.log_type == LogType.CPP_CRASH.value
    assert report.exception_type == "std::runtime_error"
    assert "database connection timeout" in report.error_message


# =============================================================================
# 6. Docker Crash & OOMKilled Tests
# =============================================================================

def test_parse_docker_oomkilled():
    engine = IncidentTriageEngine()

    raw_trace = (
        "2026-08-22T10:15:30.123456Z [ERROR] app: container memory limit exceeded\n"
        "container 8f3a9e21b exited with code 137 (OOMKilled)\n"
    )

    report = engine.triage_log_or_trace(raw_trace)

    assert report.log_type == LogType.DOCKER_CRASH.value
    assert report.exception_type == "DockerOOMKilled"
    assert "137" in report.error_message or "Memory" in report.error_message
    assert report.severity == "CRITICAL"


def test_parse_docker_embedded_python_trace(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "2026-08-22T10:00:01.000Z [INFO] Starting container worker...\n"
        "2026-08-22T10:00:02.000Z Traceback (most recent call last):\n"
        f'2026-08-22T10:00:02.000Z   File "{temp_workspace}/math_service.py", line 5, in calculate_average\n'
        "2026-08-22T10:00:02.000Z     return total / count\n"
        "2026-08-22T10:00:02.000Z ZeroDivisionError: division by zero\n"
        "container exited with status 1\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert "Docker" in report.log_type or report.log_type == LogType.PYTHON_TRACEBACK.value or "ZeroDivision" in report.exception_type
    assert report.culprit_file == "math_service.py"
    assert report.culprit_line == 5


# =============================================================================
# 7. GitHub Actions CI Error Tests
# =============================================================================

def test_parse_github_actions_ci(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        f"##[error]{temp_workspace}/math_service.py(5,9): error: ZeroDivisionError: division by zero\n"
        "Error: Process completed with exit code 1.\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    assert report.log_type == LogType.GITHUB_ACTIONS_CI.value
    assert report.culprit_file == "math_service.py"
    assert report.culprit_line == 5


# =============================================================================
# 8. Report Serialization & Markdown Formatting
# =============================================================================

def test_incident_report_to_dict_and_markdown(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{temp_workspace}/math_service.py", line 5, in calculate_average\n'
        "    return total / count\n"
        "ZeroDivisionError: division by zero\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["incident_id"] == report.incident_id
    assert d["culprit_file"] == "math_service.py"
    assert d["culprit_line"] == 5

    md = report.to_markdown()
    assert f"# Incident Report: `{report.incident_id}`" in md
    assert "ZeroDivisionError" in md
    assert "Root Cause Analysis" in md
    assert "Reproduction Steps" in md


def test_empty_log_handling():
    engine = IncidentTriageEngine()
    report = engine.triage_log_or_trace("")

    assert report.exception_type == "EmptyLog"
    assert report.severity == "LOW"


# =============================================================================
# 9. LLM-Enriched Triage Test
# =============================================================================

def test_triage_with_mock_llm_driver(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Root Cause: Zero division occurred. Fix: Guard count > 0."

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{temp_workspace}/math_service.py", line 5, in calculate_average\n'
        "    return total / count\n"
        "ZeroDivisionError: division by zero\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace), llm_driver=mock_llm)

    assert mock_llm.generate.called
    assert report.suggested_fix is not None
    assert "Guard count > 0" in report.suggested_fix


# =============================================================================
# 10. Auto-Heal Incident Loop Tests
# =============================================================================

def test_auto_heal_incident_deterministic(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    # Buggy file
    target_file = temp_workspace / "calculator.py"
    target_file.write_text(
        "def compute_ratio(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{target_file}", line 2, in compute_ratio\n'
        "    return a / b\n"
        "ZeroDivisionError: division by zero\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))
    assert report.culprit_file == "calculator.py"

    verifier = Verifier()
    patcher = Patcher()

    heal_res = engine.auto_heal_incident(
        incident=report,
        verifier=verifier,
        patcher=patcher,
        repo_path=str(temp_workspace),
    )

    assert heal_res.success is True
    assert heal_res.patch_applied is True
    assert heal_res.test_passed is True
    assert "calculator.py" in heal_res.modified_files
    assert len(heal_res.patch_diff) > 0

    # Ensure file content was patched safely and syntax is valid
    new_content = target_file.read_text(encoding="utf-8")
    assert "b != 0" in new_content
    ast.parse(new_content)


def test_auto_heal_incident_with_llm_patch(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    target_file = temp_workspace / "service.py"
    target_file.write_text(
        "def get_item(data, key):\n"
        "    return data[key]\n",
        encoding="utf-8",
    )

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{target_file}", line 2, in get_item\n'
        "    return data[key]\n"
        "KeyError: 'missing_key'\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    mock_llm = MagicMock()
    mock_llm.generate.return_value = (
        "<<<<<<< SEARCH\n"
        "    return data[key]\n"
        "=======\n"
        "    return data.get(key, None)\n"
        ">>>>>>> REPLACE\n\n"
        "```python\n"
        "def test_get_item():\n"
        "    d = {'a': 1}\n"
        "    assert d.get('b', None) is None\n"
        "```\n"
    )

    verifier = Verifier()
    patcher = Patcher()

    heal_res = engine.auto_heal_incident(
        incident=report,
        verifier=verifier,
        patcher=patcher,
        llm_driver=mock_llm,
        repo_path=str(temp_workspace),
    )

    assert heal_res.success is True
    assert heal_res.patch_applied is True
    assert "service.py" in heal_res.modified_files
    assert "return data.get(key, None)" in target_file.read_text(encoding="utf-8")


def test_auto_heal_rollback_on_test_failure(temp_workspace):
    engine = IncidentTriageEngine(repo_path=str(temp_workspace))

    target_file = temp_workspace / "broken.py"
    original_text = "def broken():\n    return 10 / 0\n"
    target_file.write_text(original_text, encoding="utf-8")

    raw_trace = (
        "Traceback (most recent call last):\n"
        f'  File "{target_file}", line 2, in broken\n'
        "    return 10 / 0\n"
        "ZeroDivisionError: division by zero\n"
    )

    report = engine.triage_log_or_trace(raw_trace, repo_path=str(temp_workspace))

    # Mock LLM provides patch that fails regression assertion
    mock_llm = MagicMock()
    mock_llm.generate.return_value = (
        "<<<<<<< SEARCH\n"
        "    return 10 / 0\n"
        "=======\n"
        "    return 0\n"
        ">>>>>>> REPLACE\n\n"
        "```python\n"
        "def test_failing_regression():\n"
        "    assert False, 'Intentional test failure'\n"
        "```\n"
    )

    verifier = Verifier()
    patcher = Patcher()

    heal_res = engine.auto_heal_incident(
        incident=report,
        verifier=verifier,
        patcher=patcher,
        llm_driver=mock_llm,
        max_retries=1,
        repo_path=str(temp_workspace),
    )

    assert heal_res.success is False
    # File content must have been rolled back to original text!
    assert target_file.read_text(encoding="utf-8") == original_text
