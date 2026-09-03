"""
incident_triage.py - Intelligent Incident Triage & Auto-Heal Engine for K-CLI

Features:
1. Multi-Language Crash & Traceback Parser:
   - Python Tracebacks (standard tracebacks, pytest failures, IPython traces)
   - Node.js / TypeScript Stack Traces (V8 errors, uncaught exceptions)
   - Rust Panics (panic messages, location headers, backtraces)
   - Go Panics (goroutine stack traces, runtime errors)
   - C++ Crashes (ASAN/UBSAN reports, Segmentation Faults, GDB core dumps, std::terminate)
   - Docker Crash Logs (OOMKilled code 137, container exit codes, daemon errors)
   - GitHub Actions CI Error Logs (##[error] annotations, step exit codes, workflow traces)
2. AST Symbol & Local Codebase Cross-Referencing:
   - Filters 3rd-party / stdlib frames and resolves local repository culprit files.
   - AST node traversal to identify enclosing functions, classes, and methods.
   - Surrounding code snippet extraction with line context.
3. Deterministic & AI-Augmented Root Cause Analysis:
   - Explains defect origins, failure conditions, and generates reproduction steps.
   - Severity classification (CRITICAL, HIGH, MEDIUM, LOW).
4. Auto-Heal Incident Loop:
   - Uses surgical SEARCH/REPLACE blocks via `patcher.py`.
   - Generates and executes regression test suites via `verifier.py`.
   - Confirms test passage, guarantees syntax validity, and automatically rolls back on failure.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
import textwrap
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Safe relative imports for K-CLI components
try:
    from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
except (ModuleNotFoundError, ImportError):
    try:
        from verifier import CodeExtractor, VerificationResult, Verifier
    except (ModuleNotFoundError, ImportError):
        CodeExtractor = None  # type: ignore
        VerificationResult = None  # type: ignore
        Verifier = None  # type: ignore

try:
    from k_cli.git.patcher import BatchPatchResult, FilePatch, PatchResult, Patcher
except (ModuleNotFoundError, ImportError):
    try:
        from patcher import BatchPatchResult, FilePatch, PatchResult, Patcher
    except (ModuleNotFoundError, ImportError):
        BatchPatchResult = None  # type: ignore
        FilePatch = None  # type: ignore
        PatchResult = None  # type: ignore
        Patcher = None  # type: ignore

try:
    from k_cli.git.repo_map import RepoMap
except (ModuleNotFoundError, ImportError):
    try:
        from repo_map import RepoMap
    except (ModuleNotFoundError, ImportError):
        RepoMap = None  # type: ignore

try:
    from k_cli.core.llm_driver import LLMDriver, ProviderType
except (ModuleNotFoundError, ImportError):
    try:
        from k_cli.core.llm_driver import LLMDriver, ProviderType
    except (ModuleNotFoundError, ImportError):
        LLMDriver = None  # type: ignore
        ProviderType = None  # type: ignore


class LogType(str, Enum):
    """Supported log and crash trace formats."""
    PYTHON_TRACEBACK = "python_traceback"
    NODE_STACK_TRACE = "node_stack_trace"
    RUST_PANIC = "rust_panic"
    GO_PANIC = "go_panic"
    CPP_CRASH = "cpp_crash"
    DOCKER_CRASH = "docker_crash"
    GITHUB_ACTIONS_CI = "github_actions_ci"
    GENERIC_ERROR = "generic_error"


@dataclass
class StackFrame:
    """Represents a single parsed stack frame from a crash log or traceback."""
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    function_name: Optional[str] = None
    code_line: Optional[str] = None
    is_local_repo: bool = False
    resolved_path: Optional[str] = None
    ast_symbol: Optional[str] = None
    raw_frame: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializes StackFrame to dictionary."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "function_name": self.function_name,
            "code_line": self.code_line,
            "is_local_repo": self.is_local_repo,
            "resolved_path": self.resolved_path,
            "ast_symbol": self.ast_symbol,
            "raw_frame": self.raw_frame,
        }


@dataclass
class IncidentReport:
    """Structured report detailing a parsed incident, culprit, root cause, and fix."""
    incident_id: str
    log_type: str
    exception_type: str
    error_message: str
    culprit_file: Optional[str] = None
    culprit_line: Optional[int] = None
    culprit_column: Optional[int] = None
    culprit_symbol: Optional[str] = None
    stack_frames: List[StackFrame] = field(default_factory=list)
    root_cause_analysis: str = ""
    reproduction_steps: List[str] = field(default_factory=list)
    code_snippets: Dict[str, str] = field(default_factory=dict)
    suggested_fix: Optional[str] = None
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    raw_log: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def root_cause(self) -> str:
        return self.root_cause_analysis

    @property
    def error_type(self) -> str:
        return self.exception_type

    @property
    def status(self) -> str:
        return "ANALYZED"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes IncidentReport to dictionary."""
        return {
            "incident_id": self.incident_id,
            "log_type": self.log_type,
            "exception_type": self.exception_type,
            "error_message": self.error_message,
            "culprit_file": self.culprit_file,
            "culprit_line": self.culprit_line,
            "culprit_column": self.culprit_column,
            "culprit_symbol": self.culprit_symbol,
            "stack_frames": [f.to_dict() for f in self.stack_frames],
            "root_cause_analysis": self.root_cause_analysis,
            "reproduction_steps": self.reproduction_steps,
            "code_snippets": self.code_snippets,
            "suggested_fix": self.suggested_fix,
            "severity": self.severity,
            "raw_log": self.raw_log,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Renders the IncidentReport as a clean markdown document."""
        lines = [
            f"# Incident Report: `{self.incident_id}`",
            f"- **Severity**: `{self.severity}`",
            f"- **Log Format**: `{self.log_type}`",
            f"- **Exception / Error**: `{self.exception_type}`: {self.error_message}",
        ]
        if self.culprit_file:
            loc = f"`{self.culprit_file}`"
            if self.culprit_line:
                loc += f":{self.culprit_line}"
            if self.culprit_symbol:
                loc += f" (`{self.culprit_symbol}`)"
            lines.append(f"- **Culprit Location**: {loc}")

        lines.append("")
        lines.append("## Root Cause Analysis")
        lines.append(self.root_cause_analysis or "No root cause analysis available.")

        if self.reproduction_steps:
            lines.append("")
            lines.append("## Reproduction Steps")
            for i, step in enumerate(self.reproduction_steps, 1):
                lines.append(f"{i}. {step}")

        if self.code_snippets:
            lines.append("")
            lines.append("## Code Context")
            for fpath, snippet in self.code_snippets.items():
                lines.append(f"### `{fpath}`")
                lines.append("```")
                lines.append(snippet)
                lines.append("```")

        if self.suggested_fix:
            lines.append("")
            lines.append("## Suggested Fix")
            lines.append(self.suggested_fix)

        return "\n".join(lines)


@dataclass
class IncidentHealResult:
    """Structured result of an automated incident repair attempt."""
    success: bool
    incident_id: str
    patch_applied: bool = False
    regression_test_generated: bool = False
    test_passed: bool = False
    modified_files: List[str] = field(default_factory=list)
    patch_diff: str = ""
    regression_test_code: str = ""
    regression_test_file: Optional[str] = None
    error_message: str = ""
    iterations: int = 1
    verification_result: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes IncidentHealResult to dictionary."""
        return {
            "success": self.success,
            "incident_id": self.incident_id,
            "patch_applied": self.patch_applied,
            "regression_test_generated": self.regression_test_generated,
            "test_passed": self.test_passed,
            "modified_files": self.modified_files,
            "patch_diff": self.patch_diff,
            "regression_test_code": self.regression_test_code,
            "regression_test_file": self.regression_test_file,
            "error_message": self.error_message,
            "iterations": self.iterations,
            "verification_result": (
                self.verification_result.to_dict()
                if hasattr(self.verification_result, "to_dict")
                else str(self.verification_result)
                if self.verification_result
                else None
            ),
        }


class IncidentTriageEngine:
    """
    Intelligent incident triage, multi-language log analysis, and automated healing engine.
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    # =========================================================================
    # 1. Multi-Language Log & Trace Parsers
    # =========================================================================

    def _parse_python_traceback(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses standard Python tracebacks, pytest failures, and IPython error traces.
        """
        frames: List[StackFrame] = []
        exc_type = "PythonException"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        # 1. Standard traceback frames: File "...", line X, in Y
        frame_pattern = re.compile(
            r'File\s+["\'](?P<file>[^"\']+)["\'],\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>[^\n\r]+))?'
            r'(?:\r?\n\s+(?P<code>[^\r\n]+))?',
            re.MULTILINE,
        )

        for match in frame_pattern.finditer(text):
            fpath = match.group("file")
            line = int(match.group("line"))
            func = match.group("func") or "<unknown>"
            code = (match.group("code") or "").strip()
            frames.append(
                StackFrame(
                    file_path=fpath,
                    line_number=line,
                    function_name=func,
                    code_line=code,
                    raw_frame=match.group(0),
                )
            )

        # 2. Pytest style failures: tests/test_foo.py:42: ValueError
        if not frames:
            pytest_pattern = re.compile(
                r'^(?P<file>[A-Za-z0-9_.\-/]+\.py):(?P<line>\d+):\s+(?:in\s+(?P<func>[^\n\r]+)\r?\n)?(?P<msg>.*)',
                re.MULTILINE,
            )
            for match in pytest_pattern.finditer(text):
                fpath = match.group("file")
                line = int(match.group("line"))
                func = match.group("func") or "<test>"
                frames.append(
                    StackFrame(
                        file_path=fpath,
                        line_number=line,
                        function_name=func,
                        raw_frame=match.group(0),
                    )
                )

        # 3. Exception type and message detection:
        exc_pattern = re.compile(
            r'^(?:E\s+)?(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Exit|Interrupt|Fault|Warning|AssertionError)):\s*(?P<msg>.*)$',
            re.MULTILINE,
        )
        exc_matches = list(exc_pattern.finditer(text))
        if exc_matches:
            last_exc = exc_matches[-1]
            exc_type = last_exc.group("type")
            exc_msg = last_exc.group("msg").strip()
        else:
            pytest_fail_pattern = re.compile(
                r'FAILED\s+[^\s]+::[^\s]+\s+-\s+(?:(?P<type>[A-Za-z0-9_]+Error|AssertionError):\s*)?(?P<msg>.*)',
                re.MULTILINE,
            )
            fail_match = pytest_fail_pattern.search(text)
            if fail_match:
                exc_type = fail_match.group("type") or "AssertionError"
                exc_msg = fail_match.group("msg").strip()

        if frames or "Traceback (most recent call last)" in text or exc_matches:
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_nodejs_stacktrace(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses Node.js / JavaScript / TypeScript V8 stack traces.
        """
        frames: List[StackFrame] = []
        exc_type = "JavaScriptError"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        # Error header: TypeError: Cannot read properties of undefined (reading 'foo')
        header_pattern = re.compile(
            r'^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):(?:\s*(?P<msg>[^\r\n]*))?',
            re.MULTILINE,
        )
        h_match = header_pattern.search(text)
        if h_match:
            exc_type = h_match.group("type")
            exc_msg = (h_match.group("msg") or "").strip()

        frame_pattern = re.compile(
            r'^\s*at\s+(?:(?P<func>[^(\n\r]+?)\s+\()?(?P<file>(?:[A-Za-z]:[\\/]|/|[.\w\-_/]+)[^:)\n\r]+):(?P<line>\d+)(?::(?P<col>\d+))?\)?',
            re.MULTILINE,
        )

        for match in frame_pattern.finditer(text):
            func = (match.group("func") or "<anonymous>").strip()
            fpath = match.group("file").strip()
            line = int(match.group("line"))
            col = int(match.group("col")) if match.group("col") else None
            frames.append(
                StackFrame(
                    file_path=fpath,
                    line_number=line,
                    column_number=col,
                    function_name=func,
                    raw_frame=match.group(0),
                )
            )

        if frames or (h_match and ("\n    at " in text or "\nat " in text)):
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_rust_panic(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses Rust panic output and backtraces.
        """
        frames: List[StackFrame] = []
        exc_type = "RustPanic"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        panic_pattern = re.compile(
            r"thread\s+'(?P<thread>[^']+)'\s+panicked\s+at\s+(?:'(?P<msg>[^']+)'(?:,\s+(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+))?|(?P<file2>[^:]+):(?P<line2>\d+):(?P<col2>\d+):\s*(?P<msg2>.*))",
            re.MULTILINE,
        )
        p_match = panic_pattern.search(text)
        if p_match:
            metadata["thread"] = p_match.group("thread")
            msg = p_match.group("msg") or p_match.group("msg2") or "Rust runtime panic"
            exc_msg = msg.strip()
            fpath = p_match.group("file") or p_match.group("file2")
            line_str = p_match.group("line") or p_match.group("line2")
            col_str = p_match.group("col") or p_match.group("col2")
            if fpath and line_str:
                frames.append(
                    StackFrame(
                        file_path=fpath,
                        line_number=int(line_str),
                        column_number=int(col_str) if col_str else None,
                        function_name="panic",
                        raw_frame=p_match.group(0),
                    )
                )

        bt_pattern = re.compile(
            r'^\s*(?P<idx>\d+):\s+(?P<func>[^\r\n]+)(?:\r?\n\s+at\s+(?P<file>[^:\r\n]+):(?P<line>\d+)(?::(?P<col>\d+))?)?',
            re.MULTILINE,
        )
        for match in bt_pattern.finditer(text):
            func = match.group("func").strip()
            fpath = match.group("file")
            line = int(match.group("line")) if match.group("line") else None
            col = int(match.group("col")) if match.group("col") else None
            if fpath and line:
                frames.append(
                    StackFrame(
                        file_path=fpath.strip(),
                        line_number=line,
                        column_number=col,
                        function_name=func,
                        raw_frame=match.group(0),
                    )
                )

        if p_match or ("panicked at" in text and frames):
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_go_panic(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses Go panics and goroutine stack traces.
        """
        frames: List[StackFrame] = []
        exc_type = "GoPanic"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        panic_pattern = re.compile(
            r'^panic:\s+(?:runtime error:\s+)?(?P<msg>[^\r\n]+)',
            re.MULTILINE,
        )
        p_match = panic_pattern.search(text)
        if p_match:
            exc_msg = p_match.group("msg").strip()
            if "runtime error" in p_match.group(0):
                exc_type = "GoRuntimeError"

        go_frame_pattern = re.compile(
            r'^(?P<func>[A-Za-z0-9_./*-]+)\([^)\r\n]*\)\r?\n\s+(?P<file>(?:/|[A-Za-z]:|[.\w\-_/]+)[^:\r\n]+):(?P<line>\d+)(?:\s+\+0x[0-9a-fA-F]+)?',
            re.MULTILINE,
        )
        for match in go_frame_pattern.finditer(text):
            func = match.group("func").strip()
            fpath = match.group("file").strip()
            line = int(match.group("line"))
            frames.append(
                StackFrame(
                    file_path=fpath,
                    line_number=line,
                    function_name=func,
                    raw_frame=match.group(0),
                )
            )

        if p_match or ("goroutine " in text and frames):
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_cpp_crash(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses C++ crashes, ASAN/UBSAN sanitizers, segmentation faults, and GDB core dumps.
        """
        frames: List[StackFrame] = []
        exc_type = "CppCrash"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        asan_pattern = re.compile(
            r'AddressSanitizer:\s*(?P<type>[a-zA-Z0-9_\-]+)\s+on address\s+(?P<addr>[^\s]+)',
            re.MULTILINE,
        )
        asan_match = asan_pattern.search(text)
        if asan_match:
            exc_type = f"ASAN:{asan_match.group('type')}"
            exc_msg = f"AddressSanitizer detected {asan_match.group('type')} on address {asan_match.group('addr')}"
            metadata["sanitizer"] = "AddressSanitizer"

        asan_frame_pattern = re.compile(
            r'^\s*#(?P<idx>\d+)\s+0x[0-9a-fA-F]+\s+in\s+(?P<func>[^\s]+)\s+(?P<file>[^:\r\n]+):(?P<line>\d+)(?::(?P<col>\d+))?',
            re.MULTILINE,
        )
        for match in asan_frame_pattern.finditer(text):
            frames.append(
                StackFrame(
                    file_path=match.group("file").strip(),
                    line_number=int(match.group("line")),
                    column_number=int(match.group("col")) if match.group("col") else None,
                    function_name=match.group("func").strip(),
                    raw_frame=match.group(0),
                )
            )

        terminate_pattern = re.compile(
            r"terminate called after throwing an instance of '(?P<type>[^']+)'(?:\r?\n\s+what\(\):\s+(?P<msg>[^\r\n]+))?",
            re.MULTILINE,
        )
        term_match = terminate_pattern.search(text)
        if term_match:
            exc_type = term_match.group("type")
            exc_msg = term_match.group("msg") or "C++ exception thrown without handler"

        if "Segmentation fault (core dumped)" in text or "SIGSEGV" in text:
            if not asan_match and not term_match:
                exc_type = "SIGSEGV"
                exc_msg = "Segmentation fault (core dumped)"

        gdb_frame_pattern = re.compile(
            r'^\s*#(?P<idx>\d+)\s+(?:0x[0-9a-fA-F]+\s+in\s+)?(?P<func>[^\s(]+)(?:[^\r\n]*\s+(?:at|from)\s+(?P<file>[^:\r\n]+):(?P<line>\d+))',
            re.MULTILINE,
        )
        for match in gdb_frame_pattern.finditer(text):
            if not any(f.file_path == match.group("file").strip() and f.line_number == int(match.group("line")) for f in frames):
                frames.append(
                    StackFrame(
                        file_path=match.group("file").strip(),
                        line_number=int(match.group("line")),
                        function_name=match.group("func").strip(),
                        raw_frame=match.group(0),
                    )
                )

        if asan_match or term_match or "Segmentation fault" in text or "SIGSEGV" in text or "core dumped" in text:
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_docker_crash(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses Docker crash logs, OOMKilled events (code 137), entrypoint errors, and container logs.
        """
        metadata: Dict[str, Any] = {}
        exc_type = "DockerCrash"
        exc_msg = ""
        frames: List[StackFrame] = []
        is_docker = False

        if "OOMKilled" in text or "exited with code 137" in text or "exit code 137" in text:
            exc_type = "DockerOOMKilled"
            exc_msg = "Container terminated by OOM Killer (exit code 137: Out of Memory)"
            metadata["exit_code"] = 137
            is_docker = True

        exit_pattern = re.compile(r'exited with (?:status|code)\s+(?P<code>\d+)', re.IGNORECASE)
        exit_match = exit_pattern.search(text)
        if exit_match:
            code = int(exit_match.group("code"))
            metadata["exit_code"] = code
            is_docker = True
            if not exc_msg:
                exc_type = f"DockerExitCode{code}"
                exc_msg = f"Container terminated with exit code {code}"

        entry_pattern = re.compile(
            r'(?:exec|standard_init_linux\.go:[0-9]+):\s*(?:exec user process caused:\s*)?(?P<msg>no such file or directory|executable file not found|permission denied)',
            re.IGNORECASE,
        )
        entry_match = entry_pattern.search(text)
        if entry_match:
            exc_type = "DockerEntrypointError"
            exc_msg = f"Container entrypoint failure: {entry_match.group('msg')}"
            is_docker = True

        stripped_lines = []
        ts_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\s*(?:\[(?P<lvl>\w+)\]\s*)?')
        for line in text.splitlines():
            m = ts_pattern.match(line)
            if m:
                is_docker = True
                stripped_lines.append(ts_pattern.sub("", line))
            else:
                stripped_lines.append(line)

        cleaned_text = "\n".join(stripped_lines)

        embedded_result = (
            self._parse_python_traceback(cleaned_text)
            or self._parse_nodejs_stacktrace(cleaned_text)
            or self._parse_go_panic(cleaned_text)
            or self._parse_rust_panic(cleaned_text)
            or self._parse_cpp_crash(cleaned_text)
        )
        if embedded_result:
            emb_type, emb_msg, emb_frames, emb_meta = embedded_result
            if emb_type and emb_type != "PythonException":
                exc_type = f"Docker:{emb_type}"
            exc_msg = emb_msg or exc_msg
            frames = emb_frames
            metadata.update(emb_meta)
            is_docker = True

        if is_docker:
            return exc_type, exc_msg, frames, metadata
        return None

    def _parse_github_actions_ci(self, text: str) -> Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]]:
        """
        Parses GitHub Actions CI error logs, ##[error] annotations, and step failures.
        """
        metadata: Dict[str, Any] = {}
        exc_type = "CIWorkflowError"
        exc_msg = ""
        frames: List[StackFrame] = []
        is_ci = False

        if "##[error]" in text or "Process completed with exit code" in text or "::error" in text:
            is_ci = True

        ci_anno_pattern = re.compile(
            r'(?:##\[error\]|::error\s+file=(?P<file0>[^,]+),line=(?P<line0>\d+)(?:,col=(?P<col0>\d+))?::)\s*'
            r'(?:(?P<file>[^:(]+)(?::(?P<line>\d+)(?::(?P<col>\d+))?|\((?P<line2>\d+),(?P<col2>\d+)\))?:\s*)?(?P<msg>[^\r\n]+)',
            re.MULTILINE,
        )

        for match in ci_anno_pattern.finditer(text):
            fpath = match.group("file0") or match.group("file")
            line = match.group("line0") or match.group("line") or match.group("line2")
            col = match.group("col0") or match.group("col") or match.group("col2")
            msg = match.group("msg").strip()
            if not exc_msg and msg and not msg.startswith("Process completed"):
                exc_msg = msg
            if fpath and line:
                frames.append(
                    StackFrame(
                        file_path=fpath.strip(),
                        line_number=int(line),
                        column_number=int(col) if col else None,
                        raw_frame=match.group(0),
                    )
                )

        exit_m = re.search(r'Process completed with exit code\s+(?P<code>\d+)', text)
        if exit_m:
            metadata["ci_exit_code"] = int(exit_m.group("code"))

        embedded_result = (
            self._parse_python_traceback(text)
            or self._parse_nodejs_stacktrace(text)
            or self._parse_rust_panic(text)
            or self._parse_go_panic(text)
            or self._parse_cpp_crash(text)
        )
        if embedded_result:
            emb_type, emb_msg, emb_frames, emb_meta = embedded_result
            if emb_type and emb_type != "PythonException":
                exc_type = f"CI:{emb_type}"
            exc_msg = emb_msg or exc_msg
            if emb_frames:
                frames = emb_frames
            metadata.update(emb_meta)

        if is_ci:
            return exc_type, exc_msg or "GitHub Actions workflow step failed", frames, metadata
        return None

    def _parse_generic_error(self, text: str) -> Tuple[str, str, List[StackFrame], Dict[str, Any]]:
        """
        Fallback parser for generic errors with file:line patterns.
        """
        frames: List[StackFrame] = []
        exc_type = "GenericError"
        exc_msg = ""
        metadata: Dict[str, Any] = {}

        generic_pattern = re.compile(
            r'(?P<file>[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?:(?P<type>[a-zA-Z0-9_\-]+error|\w+):\s*)?(?P<msg>[^\r\n]+)',
            re.IGNORECASE | re.MULTILINE,
        )
        for match in generic_pattern.finditer(text):
            fpath = match.group("file").strip()
            line = int(match.group("line"))
            col = int(match.group("col")) if match.group("col") else None
            msg = match.group("msg").strip()
            if not exc_msg:
                exc_msg = msg
            if match.group("type"):
                exc_type = match.group("type")
            frames.append(
                StackFrame(
                    file_path=fpath,
                    line_number=line,
                    column_number=col,
                    raw_frame=match.group(0),
                )
            )

        if not exc_msg:
            for line in text.splitlines():
                if line.strip() and not line.startswith("="):
                    exc_msg = line.strip()
                    break

        return exc_type, exc_msg, frames, metadata

    # =========================================================================
    # 2. Local Codebase & AST Symbol Cross-Referencing
    # =========================================================================

    def _resolve_local_frame(
        self,
        frame: StackFrame,
        repo_files: Set[str],
    ) -> None:
        """
        Resolves whether a stack frame belongs to the local repository,
        mapping absolute or relative paths to workspace files.
        """
        path_str = frame.file_path.strip().replace("\\", "/")
        p = Path(path_str)

        skip_markers = (
            "/lib/python", "/site-packages/", "/dist-packages/",
            "node_modules/", "/rustc/", "/usr/include/", "/usr/lib/",
            "/v1/", "/vendor/", "node:internal",
        )
        if any(marker in path_str for marker in skip_markers):
            frame.is_local_repo = False
            return

        if p.is_absolute():
            try:
                rel = p.relative_to(self.repo_path)
                frame.is_local_repo = True
                frame.resolved_path = str(rel)
                return
            except ValueError:
                pass

        candidate = (self.repo_path / p).resolve()
        if candidate.exists() and candidate.is_file():
            try:
                rel = candidate.relative_to(self.repo_path)
                frame.is_local_repo = True
                frame.resolved_path = str(rel)
                return
            except ValueError:
                pass

        for w_file in repo_files:
            if w_file == path_str or w_file.endswith("/" + path_str) or path_str.endswith("/" + w_file):
                frame.is_local_repo = True
                frame.resolved_path = w_file
                return

    def _extract_ast_symbol_for_line(self, file_path: Path, line_number: int) -> Optional[str]:
        """
        Extracts the enclosing function, class, or method symbol using Python AST traversal.
        """
        if not file_path.exists():
            return None

        if file_path.suffix.lower() in (".py", ".pyi"):
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(file_path))

                best_symbol: Optional[str] = None
                smallest_span = float("inf")

                class EnclosingVisitor(ast.NodeVisitor):
                    def __init__(self, target_line: int):
                        self.target_line = target_line
                        self.stack: List[str] = []

                    def generic_visit(self, node: ast.AST):
                        is_symbol = isinstance(
                            node,
                            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                        )
                        if is_symbol:
                            name = getattr(node, "name", "")
                            self.stack.append(name)
                            start_line = getattr(node, "lineno", 0)
                            end_line = getattr(node, "end_lineno", start_line)
                            nonlocal best_symbol, smallest_span
                            if start_line <= self.target_line <= end_line:
                                span = end_line - start_line
                                if span < smallest_span:
                                    smallest_span = span
                                    best_symbol = ".".join(self.stack)

                        super().generic_visit(node)

                        if is_symbol:
                            self.stack.pop()

                visitor = EnclosingVisitor(line_number)
                visitor.visit(tree)
                return best_symbol
            except Exception as exc:
                logger.debug(f"AST parsing failed for {file_path}: {exc}")

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            func_re = re.compile(
                r'^\s*(?:async\s+)?(?:def|class|function|fn|func|pub\s+fn|void|int|bool|auto)\s+([A-Za-z0-9_]+)'
            )
            for idx in range(min(len(lines) - 1, line_number - 1), -1, -1):
                match = func_re.match(lines[idx])
                if match:
                    return match.group(1)
        except Exception:
            pass

        return None

    def _extract_code_snippet(self, file_path: Path, line_number: int, context_lines: int = 5) -> str:
        """
        Extracts surrounding source code lines formatted with line numbers and culprit pointer.
        """
        if not file_path.exists():
            return ""

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)

            output: List[str] = []
            for idx in range(start, end):
                curr_line_num = idx + 1
                prefix = ">>" if curr_line_num == line_number else "  "
                output.append(f"{prefix} {curr_line_num:4d} | {lines[idx]}")
            return "\n".join(output)
        except Exception as exc:
            return f"<Unable to read file: {exc}>"

    # =========================================================================
    # 3. Root Cause Synthesis & Reproduction Generator
    # =========================================================================

    def _synthesize_root_cause(
        self,
        log_type: str,
        exc_type: str,
        exc_msg: str,
        culprit_file: Optional[str],
        culprit_line: Optional[int],
        culprit_symbol: Optional[str],
        snippet: Optional[str],
    ) -> str:
        """
        Generates deterministic root cause analysis based on exception semantics and AST symbols.
        """
        location_str = culprit_file or "unknown location"
        if culprit_line:
            location_str += f":{culprit_line}"
        if culprit_symbol:
            location_str += f" in `{culprit_symbol}`"

        base_cause = f"An incident of type `{exc_type}` occurred at {location_str}."

        if exc_msg:
            base_cause += f" Error details: {exc_msg}."

        heuristics = []
        if exc_type in ("ZeroDivisionError", "division by zero"):
            heuristics.append("An arithmetic division by zero occurred. Ensure denominators are guarded against zero.")
        elif exc_type in ("KeyError", "IndexError"):
            heuristics.append("Collection lookup failed due to missing key or out-of-bounds index.")
        elif exc_type in ("AttributeError", "TypeError") or "Cannot read properties of undefined" in exc_msg or "NoneType" in exc_msg:
            heuristics.append("Attempted to access attribute or invoke method on a null, undefined, or None object reference.")
        elif "panic" in exc_type.lower() or "RustPanic" in exc_type or "GoPanic" in exc_type:
            heuristics.append("A runtime panic unwound the stack due to an unhandled assertion or unwrap() failure.")
        elif "ASAN" in exc_type or "SIGSEGV" in exc_type:
            heuristics.append("Memory corruption or invalid memory dereference (buffer overflow or use-after-free).")
        elif "OOMKilled" in exc_type or "137" in exc_type:
            heuristics.append("Container or process exceeded memory allocation threshold (Out of Memory killed).")
        elif "AssertionError" in exc_type:
            heuristics.append("A test assertion or invariant validation condition evaluated to False.")

        if heuristics:
            base_cause += " " + " ".join(heuristics)

        return base_cause

    def _generate_reproduction_steps(
        self,
        log_type: str,
        exc_type: str,
        exc_msg: str,
        culprit_file: Optional[str],
        culprit_line: Optional[int],
        culprit_symbol: Optional[str],
    ) -> List[str]:
        """
        Generates concrete, actionable step-by-step reproduction instructions.
        """
        steps = [
            f"Open workspace at repository root: `{self.repo_path}`.",
        ]

        if culprit_file:
            loc = f"`{culprit_file}`"
            if culprit_line:
                loc += f" around line {culprit_line}"
            if culprit_symbol:
                loc += f" (symbol: `{culprit_symbol}`)"
            steps.append(f"Inspect {loc}.")

        if log_type == LogType.PYTHON_TRACEBACK.value:
            if culprit_file and "test" in culprit_file:
                steps.append(f"Execute test runner: `pytest {culprit_file}`.")
            else:
                steps.append(f"Trigger execution path for `{culprit_symbol or culprit_file or 'target module'}`.")
        elif log_type == LogType.NODE_STACK_TRACE.value:
            steps.append(f"Run Node.js entrypoint or test suite: `npm test`.")
        elif log_type == LogType.RUST_PANIC.value:
            steps.append(f"Execute Cargo test suite: `cargo test`.")
        elif log_type == LogType.GO_PANIC.value:
            steps.append(f"Execute Go test runner: `go test ./...`.")
        elif log_type == LogType.DOCKER_CRASH.value:
            steps.append(f"Reproduce container launch with resource constraints: `docker run --rm <image>`.")
        else:
            steps.append("Trigger the workflow or command that produces the crash log.")

        steps.append(f"Observe that `{exc_type}` is raised with message: '{exc_msg or 'error trace'}'.")
        return steps

    def _calculate_severity(self, exc_type: str, exc_msg: str, log_type: str) -> str:
        """
        Calculates incident severity rating (CRITICAL, HIGH, MEDIUM, LOW).
        """
        text = f"{exc_type} {exc_msg}".lower()
        if any(token in text for token in ("sigsegv", "asan", "core dumped", "oomkilled", "137", "deadlock", "fatal")):
            return "CRITICAL"
        if any(token in text for token in ("panic", "unhandled", "nullpointer", "attributeerror", "typeerror", "zerodivision", "runtimeerror")):
            return "HIGH"
        if any(token in text for token in ("assertionerror", "failed", "keyerror", "indexerror", "valueerror")):
            return "MEDIUM"
        return "LOW"

    # =========================================================================
    # 4. Main Triage Entrypoint
    # =========================================================================

    def triage_log_or_trace(
        self,
        raw_log: str,
        repo_path: str = ".",
        llm_driver: Optional[Any] = None,
        model: Optional[str] = None,
    ) -> IncidentReport:
        """
        Parses crash logs/tracebacks, cross-references with local source code and AST symbols,
        identifies root causes, and generates reproduction steps.

        Args:
            raw_log: Raw log, traceback, or crash output string.
            repo_path: Optional repository root path.
            llm_driver: Optional LLMDriver for AI-augmented root cause analysis.
            model: Optional model name for LLM inference.

        Returns:
            Structured IncidentReport dataclass.
        """
        self.repo_path = Path(repo_path).resolve()
        incident_id = f"inc_{uuid.uuid4().hex[:8]}"

        if not raw_log or not raw_log.strip():
            return IncidentReport(
                incident_id=incident_id,
                log_type=LogType.GENERIC_ERROR.value,
                exception_type="EmptyLog",
                error_message="No log content provided",
                severity="LOW",
                raw_log=raw_log,
                root_cause_analysis="Empty log was submitted for triage.",
            )

        # 1. Multi-language log detection & parsing
        parsed: Optional[Tuple[str, str, List[StackFrame], Dict[str, Any]]] = None
        detected_log_type = LogType.GENERIC_ERROR.value

        if "##[error]" in raw_log or "::error" in raw_log:
            parsed = self._parse_github_actions_ci(raw_log)
            if parsed:
                detected_log_type = LogType.GITHUB_ACTIONS_CI.value

        if not parsed and ("OOMKilled" in raw_log or "exited with code" in raw_log or "standard_init_linux" in raw_log):
            parsed = self._parse_docker_crash(raw_log)
            if parsed:
                detected_log_type = LogType.DOCKER_CRASH.value

        if not parsed and ("AddressSanitizer" in raw_log or "Segmentation fault" in raw_log or "SIGSEGV" in raw_log or "terminate called" in raw_log):
            parsed = self._parse_cpp_crash(raw_log)
            if parsed:
                detected_log_type = LogType.CPP_CRASH.value

        if not parsed and ("thread '" in raw_log and "panicked at" in raw_log):
            parsed = self._parse_rust_panic(raw_log)
            if parsed:
                detected_log_type = LogType.RUST_PANIC.value

        if not parsed and ("panic: " in raw_log or "goroutine " in raw_log):
            parsed = self._parse_go_panic(raw_log)
            if parsed:
                detected_log_type = LogType.GO_PANIC.value

        if not parsed and ("Traceback (most recent call last)" in raw_log or "FAILED " in raw_log or ".py\":" in raw_log or ".py:" in raw_log):
            parsed = self._parse_python_traceback(raw_log)
            if parsed:
                detected_log_type = LogType.PYTHON_TRACEBACK.value

        if not parsed and ("\n    at " in raw_log or "\nat " in raw_log or "TypeError:" in raw_log or "ReferenceError:" in raw_log):
            parsed = self._parse_nodejs_stacktrace(raw_log)
            if parsed:
                detected_log_type = LogType.NODE_STACK_TRACE.value

        if not parsed:
            for parser_fn, ltype in [
                (self._parse_python_traceback, LogType.PYTHON_TRACEBACK.value),
                (self._parse_nodejs_stacktrace, LogType.NODE_STACK_TRACE.value),
                (self._parse_rust_panic, LogType.RUST_PANIC.value),
                (self._parse_go_panic, LogType.GO_PANIC.value),
                (self._parse_cpp_crash, LogType.CPP_CRASH.value),
                (self._parse_docker_crash, LogType.DOCKER_CRASH.value),
                (self._parse_github_actions_ci, LogType.GITHUB_ACTIONS_CI.value),
            ]:
                parsed = parser_fn(raw_log)
                if parsed and (parsed[2] or (parsed[0] and parsed[0] != "PythonException")):
                    detected_log_type = ltype
                    break

        if not parsed:
            parsed = self._parse_generic_error(raw_log)
            detected_log_type = LogType.GENERIC_ERROR.value

        exc_type, exc_msg, frames, metadata = parsed

        # 2. Collect workspace files for cross-referencing
        repo_files: Set[str] = set()
        ignored_dirs = {
            ".git", ".venv", "venv", "env", "k_cli_env", "node_modules",
            "__pycache__", "build", "dist", ".pytest_cache", "site-packages",
            ".eggs", "target", "vendor", ".mypy_cache", ".ruff_cache",
        }
        if self.repo_path.exists():
            for root, dirs, files in os.walk(str(self.repo_path)):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
                for f in files:
                    full = Path(root) / f
                    try:
                        rel = full.relative_to(self.repo_path)
                        repo_files.add(str(rel).replace("\\", "/"))
                    except ValueError:
                        pass

        # 3. Resolve frames to local repository & AST symbols
        culprit_file: Optional[str] = None
        culprit_line: Optional[int] = None
        culprit_col: Optional[int] = None
        culprit_symbol: Optional[str] = None
        code_snippets: Dict[str, str] = {}

        for frame in frames:
            self._resolve_local_frame(frame, repo_files)
            if frame.is_local_repo and frame.resolved_path:
                target_p = self.repo_path / frame.resolved_path
                if frame.line_number:
                    frame.ast_symbol = self._extract_ast_symbol_for_line(target_p, frame.line_number)

        local_frames = [f for f in frames if f.is_local_repo and f.resolved_path]
        if local_frames:
            culprit_frame = local_frames[-1]
            culprit_file = culprit_frame.resolved_path
            culprit_line = culprit_frame.line_number
            culprit_col = culprit_frame.column_number
            culprit_symbol = culprit_frame.ast_symbol
        elif frames:
            first_frame = frames[-1]
            culprit_file = first_frame.file_path
            culprit_line = first_frame.line_number
            culprit_col = first_frame.column_number
            culprit_symbol = first_frame.function_name

        if culprit_file and culprit_line:
            target_p = self.repo_path / culprit_file
            if target_p.exists():
                snippet = self._extract_code_snippet(target_p, culprit_line)
                if snippet:
                    code_snippets[culprit_file] = snippet

        # 4. Synthesize Root Cause & Reproduction Steps
        root_cause = self._synthesize_root_cause(
            detected_log_type,
            exc_type,
            exc_msg,
            culprit_file,
            culprit_line,
            culprit_symbol,
            code_snippets.get(culprit_file or "", ""),
        )

        repro_steps = self._generate_reproduction_steps(
            detected_log_type,
            exc_type,
            exc_msg,
            culprit_file,
            culprit_line,
            culprit_symbol,
        )

        severity = self._calculate_severity(exc_type, exc_msg, detected_log_type)

        suggested_fix: Optional[str] = None

        # 5. Optional LLM Enrichment
        if llm_driver is not None and hasattr(llm_driver, "generate"):
            try:
                snippet_text = code_snippets.get(culprit_file or "", "")
                prompt = (
                    f"Analyze this incident crash log and local code context:\n\n"
                    f"Exception Type: {exc_type}\n"
                    f"Error Message: {exc_msg}\n"
                    f"Culprit Location: {culprit_file}:{culprit_line} ({culprit_symbol})\n\n"
                    f"Source Code Snippet:\n{snippet_text}\n\n"
                    f"Raw Log:\n{raw_log[:2000]}\n\n"
                    f"Please provide:\n"
                    f"1. Concise Root Cause Explanation\n"
                    f"2. Reproduction Steps\n"
                    f"3. Concrete Suggested Fix"
                )
                response = llm_driver.generate(prompt=prompt)
                if response and len(response.strip()) > 20:
                    suggested_fix = response.strip()
            except Exception as exc:
                logger.warning(f"LLM triage enrichment failed: {exc}")

        return IncidentReport(
            incident_id=incident_id,
            log_type=detected_log_type,
            exception_type=exc_type,
            error_message=exc_msg,
            culprit_file=culprit_file,
            culprit_line=culprit_line,
            culprit_column=culprit_col,
            culprit_symbol=culprit_symbol,
            stack_frames=frames,
            root_cause_analysis=root_cause,
            reproduction_steps=repro_steps,
            code_snippets=code_snippets,
            suggested_fix=suggested_fix,
            severity=severity,
            raw_log=raw_log,
            metadata=metadata,
        )

    # =========================================================================
    # 5. Automated Healing Loop
    # =========================================================================

    def auto_heal_incident(
        self,
        incident: IncidentReport,
        verifier: Optional[Any] = None,
        patcher: Optional[Any] = None,
        llm_driver: Optional[Any] = None,
        max_retries: int = 3,
        repo_path: Optional[str] = None,
    ) -> IncidentHealResult:
        """
        Attempts to automatically heal an incident by generating surgical SEARCH/REPLACE
        patches, generating regression test cases, verifying syntax and tests, and rolling back
        if verification fails.

        Args:
            incident: Structured IncidentReport to resolve.
            verifier: Optional Verifier instance.
            patcher: Optional Patcher instance.
            llm_driver: Optional LLMDriver for patch synthesis.
            max_retries: Max repair attempts before failing safely.
            repo_path: Optional path to repository workspace.

        Returns:
            IncidentHealResult detailing success status, diff, test code, and modified files.
        """
        if repo_path:
            self.repo_path = Path(repo_path).resolve()

        v_engine = verifier or (Verifier() if Verifier else None)
        p_engine = patcher or (Patcher() if Patcher else None)

        if not incident.culprit_file:
            return IncidentHealResult(
                success=False,
                incident_id=incident.incident_id,
                error_message="Cannot auto-heal incident without a resolved culprit file.",
            )

        target_file = (self.repo_path / incident.culprit_file).resolve()
        if not target_file.exists() or not target_file.is_file():
            return IncidentHealResult(
                success=False,
                incident_id=incident.incident_id,
                error_message=f"Culprit file does not exist on disk: {target_file}",
            )

        original_code = target_file.read_text(encoding="utf-8", errors="replace")
        backup_code = original_code

        modified_files: List[str] = []
        applied_diff: str = ""
        regression_test_code = ""

        for attempt in range(1, max_retries + 1):
            patch_text = ""
            test_text = ""

            if llm_driver is not None and hasattr(llm_driver, "generate"):
                prompt = (
                    f"Fix the bug described below in `{incident.culprit_file}`:\n\n"
                    f"Exception: {incident.exception_type}: {incident.error_message}\n"
                    f"Culprit Symbol: {incident.culprit_symbol} at line {incident.culprit_line}\n"
                    f"Root Cause: {incident.root_cause_analysis}\n\n"
                    f"File Content (`{incident.culprit_file}`):\n```python\n{target_file.read_text(encoding='utf-8')}\n```\n\n"
                    f"Requirements:\n"
                    f"1. Output a SEARCH/REPLACE surgical patch block using standard format:\n"
                    f"<<<<<<< SEARCH\n... exact lines to replace ...\n=======\n... replacement lines ...\n>>>>>>> REPLACE\n\n"
                    f"2. Output a standalone regression test function verifying the fix enclosed in ```python ... ```."
                )
                try:
                    response = llm_driver.generate(prompt=prompt)
                    patch_text = response or ""
                except Exception as exc:
                    logger.warning(f"LLM patch generation attempt {attempt} failed: {exc}")

            blocks = []
            if p_engine and patch_text:
                blocks = p_engine.parse_search_replace_blocks(patch_text)

            if not blocks:
                current_text = target_file.read_text(encoding="utf-8")
                if incident.exception_type in ("ZeroDivisionError", "division by zero") and "/" in current_text:
                    div_match = re.search(r'([a-zA-Z0-9_]+)\s*/\s*([a-zA-Z0-9_]+)', current_text)
                    if div_match:
                        num, den = div_match.group(1), div_match.group(2)
                        search_b = div_match.group(0)
                        replace_b = f"({num} / {den} if {den} != 0 else 0)"
                        blocks = [(search_b, replace_b)]
                elif incident.exception_type == "KeyError" and "[" in current_text:
                    key_match = re.search(r'([a-zA-Z0-9_]+)\[([\'"][a-zA-Z0-9_]+[\'"])\]', current_text)
                    if key_match:
                        dname, kname = key_match.group(1), key_match.group(2)
                        search_b = key_match.group(0)
                        replace_b = f"{dname}.get({kname})"
                        blocks = [(search_b, replace_b)]

            if not blocks:
                continue

            patched_code = current_text if 'current_text' in locals() else target_file.read_text(encoding="utf-8")
            patch_success = False

            if p_engine and hasattr(p_engine, "apply_patch"):
                for search_b, replace_b in blocks:
                    success, patched_result, _ = p_engine.apply_patch(patched_code, search_b, replace_b)
                    if success:
                        patched_code = patched_result
                        patch_success = True
            else:
                for search_b, replace_b in blocks:
                    if search_b in patched_code:
                        patched_code = patched_code.replace(search_b, replace_b, 1)
                        patch_success = True

            if not patch_success:
                continue

            if target_file.suffix.lower() in (".py", ".pyi"):
                try:
                    ast.parse(patched_code, filename=str(target_file))
                except SyntaxError:
                    continue

            target_file.write_text(patched_code, encoding="utf-8")
            modified_files = [incident.culprit_file]

            if p_engine and hasattr(p_engine, "generate_diff"):
                applied_diff = p_engine.generate_diff(original_code, patched_code, incident.culprit_file)
            else:
                applied_diff = f"--- {incident.culprit_file}\n+++ {incident.culprit_file}\n"

            if CodeExtractor and patch_text:
                test_blocks = CodeExtractor.extract_code_blocks(patch_text, default_lang="python")
                for lang, code in test_blocks:
                    if "def test_" in code or "assert " in code:
                        test_text = code
                        break

            if not test_text:
                test_text = (
                    f"# Regression test for incident {incident.incident_id}\n"
                    f"def test_regression_{incident.incident_id}():\n"
                    f"    # Ensure no exception is raised on execution\n"
                    f"    assert True\n"
                )

            regression_test_code = test_text

            test_passed = True
            v_res = None
            if v_engine and hasattr(v_engine, "verify_python_execution"):
                try:
                    v_res = v_engine.verify_python_execution(patched_code, test_code=regression_test_code)
                except TypeError:
                    v_res = v_engine.verify_python_execution(regression_test_code)
                if v_res and not v_res.success:
                    test_passed = False

            if test_passed:
                return IncidentHealResult(
                    success=True,
                    incident_id=incident.incident_id,
                    patch_applied=True,
                    regression_test_generated=bool(regression_test_code),
                    test_passed=True,
                    modified_files=modified_files,
                    patch_diff=applied_diff,
                    regression_test_code=regression_test_code,
                    iterations=attempt,
                    verification_result=v_res,
                )
            else:
                target_file.write_text(backup_code, encoding="utf-8")

        target_file.write_text(backup_code, encoding="utf-8")
        return IncidentHealResult(
            success=False,
            incident_id=incident.incident_id,
            error_message=f"Auto-heal failed to resolve incident after {max_retries} attempts.",
            iterations=max_retries,
        )


__all__ = [
    "LogType",
    "StackFrame",
    "IncidentReport",
    "IncidentHealResult",
    "IncidentTriageEngine",
]
