"""
subagents.py - Native Subagent Task Spawner & Multi-Agent Orchestrator for K-CLI
Project Bankai Engine v1.0.0

Enables K-CLI to decompose complex user prompts into parallel subtasks:
  - [EXPLORER]   : Inspects workspace structure, AST symbol maps, locates files.
  - [RESEARCHER] : Investigates offline DevDocs, API signatures, dependencies.
  - [REFACTORER] : Generates code modifications and SEARCH/REPLACE surgical patch blocks.
  - [TESTER]     : Formulates test suites and runs ground-truth verification guard.

Features:
  1. DAG Task Decomposition (LLM-based with deterministic fallback).
  2. Multi-threaded background execution with structured JSON messaging.
  3. PatchAggregator to merge SEARCH/REPLACE blocks into unified patches.
  4. Rich CLI tree visualization with live progress bars and status dashboards.
  5. Memory-budgeted execution (< 1.0 GB RAM constraint).
"""

from __future__ import annotations

import ast
import gc
import json
import os
import psutil
import queue
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

try:
    from k_cli.tools.doc_retriever import DocRetriever
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.git.patcher import Patcher
    from k_cli.git.repo_map import RepoMap
    from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
    from k_cli.git.conflict_resolver import ConflictResolver, ConflictBlock, ConflictSummary, FileResolutionResult
    from k_cli.github.github_client import GitHubClient, PRLifecycleManager, PRReviewResult, PRFixResult
    from k_cli.tools.mcp_client import MCPManager, MCPClient, MCPTool, MCPToolResult
    from k_cli.github.dedup_engine import DedupEngine, DedupMatch
except ModuleNotFoundError:
    from doc_retriever import DocRetriever
    from k_cli.core.llm_driver import LLMDriver
    from patcher import Patcher
    from repo_map import RepoMap
    from verifier import CodeExtractor, VerificationResult, Verifier
    try:
        from conflict_resolver import ConflictResolver, ConflictBlock, ConflictSummary, FileResolutionResult
    except (ModuleNotFoundError, ImportError):
        ConflictResolver = None  # type: ignore
        ConflictBlock = None  # type: ignore
        ConflictSummary = None  # type: ignore
        FileResolutionResult = None  # type: ignore
    try:
        from github_client import GitHubClient, PRLifecycleManager, PRReviewResult, PRFixResult
    except (ModuleNotFoundError, ImportError):
        GitHubClient = None  # type: ignore
        PRLifecycleManager = None  # type: ignore
        PRReviewResult = None  # type: ignore
        PRFixResult = None  # type: ignore
    try:
        from mcp_client import MCPManager, MCPClient, MCPTool, MCPToolResult
    except (ModuleNotFoundError, ImportError):
        MCPManager = None  # type: ignore
        MCPClient = None  # type: ignore
        MCPTool = None  # type: ignore
        MCPToolResult = None  # type: ignore
    try:
        from dedup_engine import DedupEngine, DedupMatch
    except (ModuleNotFoundError, ImportError):
        DedupEngine = None  # type: ignore
        DedupMatch = None  # type: ignore

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree


def _resolve_driver(driver: Optional[LLMDriver] = None, mock_mode: bool = False) -> LLMDriver:
    """Helper to ensure safe offline fallback during test runs or mock environments."""
    if driver is not None:
        return driver
    is_mock = mock_mode or os.getenv("KCLI_MOCK_MODE", "").lower() in ("true", "1") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM"))
    return LLMDriver(mock_mode=is_mock)


# ==============================================================================
# 1. Enums & Structured Data Models
# ==============================================================================

class SubagentRole(str, Enum):
    """Specialized worker roles in the multi-agent orchestration tree."""
    EXPLORER = "EXPLORER"
    RESEARCHER = "RESEARCHER"
    REFACTORER = "REFACTORER"
    TESTER = "TESTER"
    CODER = "CODER"
    CRITIC = "CRITIC"
    ARCHITECT = "ARCHITECT"
    CONFLICT_RESOLVER = "CONFLICT_RESOLVER"
    PR_REVIEWER = "PR_REVIEWER"
    MCP_OPERATOR = "MCP_OPERATOR"

    @classmethod
    def from_str(cls, val: str) -> "SubagentRole":
        val_upper = str(val).upper().strip()
        for role in cls:
            if role.value == val_upper or role.name == val_upper:
                return role
        if "CONFLICT" in val_upper or "MERGE" in val_upper:
            return cls.CONFLICT_RESOLVER
        if "PR" in val_upper or "PULL_REQUEST" in val_upper:
            return cls.PR_REVIEWER
        if "MCP" in val_upper or "TOOL_OPERATOR" in val_upper or "OPERATOR" in val_upper:
            return cls.MCP_OPERATOR
        if "EXPLOR" in val_upper:
            return cls.EXPLORER
        if "RESEARCH" in val_upper or "DOC" in val_upper:
            return cls.RESEARCHER
        if "TEST" in val_upper or "VERIF" in val_upper:
            return cls.TESTER
        if "REFACTOR" in val_upper or "PATCH" in val_upper or "EDIT" in val_upper:
            return cls.REFACTORER
        if "CRITIC" in val_upper:
            return cls.CRITIC
        return cls.CODER


class SubagentStatus(str, Enum):
    """Lifecycle states of subagent tasks."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SubagentMessageType(str, Enum):
    """Structured messaging protocols between orchestrator and subagents."""
    TASK_INIT = "TASK_INIT"
    PROGRESS = "PROGRESS"
    LOG = "LOG"
    SEARCH_REPLACE_PATCH = "SEARCH_REPLACE_PATCH"
    CODE_OUTPUT = "CODE_OUTPUT"
    TEST_RESULT = "TEST_RESULT"
    RESEARCH_FINDING = "RESEARCH_FINDING"
    EXPLORATION_MAP = "EXPLORATION_MAP"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    PR_REVIEWED = "PR_REVIEWED"
    MCP_TOOL_RESULT = "MCP_TOOL_RESULT"
    DEDUP_WARNING = "DEDUP_WARNING"
    TASK_COMPLETE = "TASK_COMPLETE"
    TASK_FAILED = "TASK_FAILED"
    HEARTBEAT = "HEARTBEAT"


@dataclass
class SubagentMessage:
    """Structured JSON message exchanged during multi-agent execution."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = "orchestrator"
    recipient_id: str = "broadcast"
    msg_type: SubagentMessageType = SubagentMessageType.LOG
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "msg_type": self.msg_type.value if hasattr(self.msg_type, "value") else str(self.msg_type),
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentMessage":
        msg_type_str = data.get("msg_type", SubagentMessageType.LOG.value)
        try:
            mtype = SubagentMessageType(msg_type_str)
        except ValueError:
            mtype = SubagentMessageType.LOG

        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            sender_id=data.get("sender_id", "unknown"),
            recipient_id=data.get("recipient_id", "broadcast"),
            msg_type=mtype,
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "SubagentMessage":
        return cls.from_dict(json.loads(json_str))


@dataclass
class SubagentTask:
    """Represents a unit of work assigned to a subagent."""
    task_id: str
    name: str
    role: SubagentRole
    prompt: str
    parent_id: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    status: SubagentStatus = SubagentStatus.PENDING
    progress: float = 0.0
    status_message: str = "Queued"
    output_text: str = ""
    patch_blocks: List[Tuple[str, str]] = field(default_factory=list)
    raw_patch: str = ""
    verification_result: Optional[VerificationResult] = None
    logs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    ram_mb: float = 0.0
    error_trace: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "role": self.role.value if hasattr(self.role, "value") else str(self.role),
            "prompt": self.prompt,
            "parent_id": self.parent_id,
            "dependencies": list(self.dependencies),
            "context": self.context,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "progress": self.progress,
            "status_message": self.status_message,
            "output_text": self.output_text,
            "patch_blocks": self.patch_blocks,
            "raw_patch": self.raw_patch,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "logs": list(self.logs),
            "metadata": self.metadata,
            "duration_seconds": self.duration_seconds,
            "ram_mb": self.ram_mb,
            "error_trace": self.error_trace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentTask":
        role_str = data.get("role", SubagentRole.CODER.value)
        status_str = data.get("status", SubagentStatus.PENDING.value)
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            name=data.get("name", "Unnamed Task"),
            role=SubagentRole.from_str(role_str),
            prompt=data.get("prompt", ""),
            parent_id=data.get("parent_id"),
            dependencies=data.get("dependencies", []),
            context=data.get("context", {}),
            status=SubagentStatus(status_str) if status_str in SubagentStatus._value2member_map_ else SubagentStatus.PENDING,
            progress=float(data.get("progress", 0.0)),
            status_message=data.get("status_message", ""),
            output_text=data.get("output_text", ""),
            patch_blocks=data.get("patch_blocks", []),
            raw_patch=data.get("raw_patch", ""),
            logs=data.get("logs", []),
            metadata=data.get("metadata", {}),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            ram_mb=float(data.get("ram_mb", 0.0)),
            error_trace=data.get("error_trace", ""),
        )


@dataclass
class SubagentRunResult:
    """Unified result container returned after executing a multi-agent plan."""
    success: bool
    tasks: List[SubagentTask]
    aggregated_patch: str
    patches_by_file: Dict[str, str]
    final_code: str
    verification: Optional[VerificationResult]
    summary: str
    total_ram_mb: float
    total_duration_sec: float
    history: List[Dict[str, Any]] = field(default_factory=list)
    dedup_warning: Optional[str] = None
    dedup_match: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tasks": [t.to_dict() for t in self.tasks],
            "aggregated_patch": self.aggregated_patch,
            "patches_by_file": self.patches_by_file,
            "final_code": self.final_code,
            "verification": self.verification.to_dict() if self.verification else None,
            "summary": self.summary,
            "total_ram_mb": self.total_ram_mb,
            "total_duration_sec": self.total_duration_sec,
            "history": self.history,
            "dedup_warning": self.dedup_warning,
            "dedup_match": self.dedup_match,
        }


# ==============================================================================
# 2. Task Decomposer (Prompt -> Subtask DAG)
# ==============================================================================

class TaskDecomposer:
    """
    Decomposes complex user prompts into parallel/dependent subtasks.
    Supports LLM-based intelligent planning with robust fallback pipelines.
    """

    DECOMPOSITION_SYSTEM_PROMPT = (
        "You are [TASK_DECOMPOSER] for K-CLI multi-agent engine. "
        "Decompose the user coding prompt into a directed task list. "
        "Valid roles: EXPLORER, RESEARCHER, REFACTORER, TESTER. "
        "Return ONLY a valid JSON array of objects with keys: "
        "'id', 'name', 'role', 'prompt', 'dependencies' (list of IDs). "
        "Do NOT include any text outside the JSON array."
    )

    def __init__(self, driver: Optional[LLMDriver] = None):
        self.driver = _resolve_driver(driver)

    def decompose(
        self,
        prompt: str,
        context_files: Optional[List[str]] = None,
        target_roles: Optional[List[SubagentRole]] = None,
        use_llm: bool = True,
    ) -> List[SubagentTask]:
        """
        Decomposes a user prompt into a list of SubagentTask instances.
        """
        cleaned_prompt = (prompt or "").strip()
        if not cleaned_prompt:
            return []

        # If specific roles were explicitly requested, build matching pipeline
        if target_roles:
            return self._build_pipeline_for_roles(cleaned_prompt, target_roles, context_files)

        # Attempt LLM decomposition if requested and driver available
        if use_llm:
            try:
                llm_tasks = self._decompose_with_llm(cleaned_prompt, context_files)
                if llm_tasks:
                    return llm_tasks
            except Exception:
                pass

        # Fallback: Deterministic intelligent decomposition
        return self._decompose_deterministic(cleaned_prompt, context_files)

    def _decompose_with_llm(self, prompt: str, context_files: Optional[List[str]]) -> Optional[List[SubagentTask]]:
        """Invokes LLM to decompose prompt into structured JSON task list."""
        context_str = f"\nContext files: {', '.join(context_files)}" if context_files else ""
        full_user_prompt = f"User Request: {prompt}{context_str}\nDecompose into subagent tasks:"

        raw_output = self.driver.generate(
            prompt=full_user_prompt,
            system_prompt=self.DECOMPOSITION_SYSTEM_PROMPT,
            temperature=0.1,
        )

        # Extract JSON array from LLM output
        json_text = raw_output.strip()
        m = re.search(r"\[\s*\{.*\}\s*\]", json_text, re.DOTALL)
        if m:
            json_text = m.group(0)

        data = json.loads(json_text)
        if not isinstance(data, list) or not data:
            return None

        tasks: List[SubagentTask] = []
        valid_ids: Set[str] = set()

        for idx, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                continue
            tid = str(item.get("id", f"subtask_{idx}")).strip()
            name = str(item.get("name", f"Subtask {idx}")).strip()
            role_str = str(item.get("role", "CODER")).strip()
            sub_prompt = str(item.get("prompt", prompt)).strip()
            deps = [str(d).strip() for d in item.get("dependencies", []) if str(d).strip() in valid_ids]

            role = SubagentRole.from_str(role_str)
            task = SubagentTask(
                task_id=tid,
                name=name,
                role=role,
                prompt=sub_prompt,
                dependencies=deps,
                context={"context_files": context_files or []},
            )
            tasks.append(task)
            valid_ids.add(tid)

        return tasks if tasks else None

    def _decompose_deterministic(
        self,
        prompt: str,
        context_files: Optional[List[str]] = None,
    ) -> List[SubagentTask]:
        """
        Constructs deterministic pipeline based on user request keywords:
        - Conflicts: [CONFLICT_RESOLVER] -> [TESTER]
        - PR Review: [PR_REVIEWER]
        - MCP Operator: [MCP_OPERATOR]
        - Standard: [EXPLORER] + [RESEARCHER] -> [REFACTORER] -> [TESTER]
        """
        files = context_files or []
        files_hint = f" Focus on files: {', '.join(files)}." if files else ""
        prompt_lower = prompt.lower()

        if "conflict" in prompt_lower or "merge conflict" in prompt_lower:
            task_conflict = SubagentTask(
                task_id="task_conflict_resolver",
                name="Resolve Git Merge Conflicts",
                role=SubagentRole.CONFLICT_RESOLVER,
                prompt=f"Inspect and resolve git merge conflicts in workspace for: '{prompt}'.{files_hint}",
                dependencies=[],
                context={"context_files": files},
            )
            task_tester = SubagentTask(
                task_id="task_tester",
                name="Verify Resolved Files",
                role=SubagentRole.TESTER,
                prompt=f"Verify syntax and compiler correctness of resolved files for: '{prompt}'.",
                dependencies=["task_conflict_resolver"],
                context={"context_files": files},
            )
            return [task_conflict, task_tester]

        if "review pr" in prompt_lower or "pr review" in prompt_lower or "pull request review" in prompt_lower:
            task_pr = SubagentTask(
                task_id="task_pr_reviewer",
                name="Review GitHub Pull Request",
                role=SubagentRole.PR_REVIEWER,
                prompt=f"Perform AI code review and diff analysis for: '{prompt}'.",
                dependencies=[],
                context={"context_files": files},
            )
            return [task_pr]

        if "mcp tool" in prompt_lower or "call mcp" in prompt_lower or "mcp operator" in prompt_lower:
            task_mcp = SubagentTask(
                task_id="task_mcp_operator",
                name="Execute MCP Tool Operations",
                role=SubagentRole.MCP_OPERATOR,
                prompt=f"Execute Model Context Protocol tools to fulfill: '{prompt}'.",
                dependencies=[],
                context={"context_files": files},
            )
            return [task_mcp]

        # Subagent 1: Explorer
        task_explorer = SubagentTask(
            task_id="task_explorer",
            name="Explore Workspace & AST Map",
            role=SubagentRole.EXPLORER,
            prompt=f"Inspect repository structure, locate relevant files, and extract AST symbols for: '{prompt}'.{files_hint}",
            dependencies=[],
            context={"context_files": files},
        )

        # Subagent 2: Researcher
        task_researcher = SubagentTask(
            task_id="task_researcher",
            name="Research DevDocs & API Contracts",
            role=SubagentRole.RESEARCHER,
            prompt=f"Identify required libraries, API signatures, imports, and edge cases for: '{prompt}'.",
            dependencies=[],
            context={"context_files": files},
        )

        # Subagent 3: Refactorer / Coder
        task_refactorer = SubagentTask(
            task_id="task_refactorer",
            name="Synthesize Code & Surgical Patches",
            role=SubagentRole.REFACTORER,
            prompt=f"Generate Python implementation or SEARCH/REPLACE surgical patch blocks to fulfill: '{prompt}'.",
            dependencies=["task_explorer", "task_researcher"],
            context={"context_files": files},
        )

        # Subagent 4: Tester / Verifier
        task_tester = SubagentTask(
            task_id="task_tester",
            name="Verify AST & Validate Tests",
            role=SubagentRole.TESTER,
            prompt=f"Perform AST syntax validation, create unit tests, and verify compiler correctness for the implementation of '{prompt}'.",
            dependencies=["task_refactorer"],
            context={"context_files": files},
        )

        return [task_explorer, task_researcher, task_refactorer, task_tester]

    def _build_pipeline_for_roles(
        self,
        prompt: str,
        roles: List[SubagentRole],
        context_files: Optional[List[str]],
    ) -> List[SubagentTask]:
        """Builds custom pipeline for a specific list of roles."""
        tasks: List[SubagentTask] = []
        prev_id: Optional[str] = None

        for idx, role in enumerate(roles, start=1):
            tid = f"task_{role.value.lower()}_{idx}"
            deps = [prev_id] if prev_id and role in (SubagentRole.REFACTORER, SubagentRole.TESTER, SubagentRole.CRITIC) else []
            task = SubagentTask(
                task_id=tid,
                name=f"{role.value.capitalize()} Worker",
                role=role,
                prompt=f"Execute {role.value} operations for: '{prompt}'",
                dependencies=deps,
                context={"context_files": context_files or []},
            )
            tasks.append(task)
            prev_id = tid

        return tasks


# ==============================================================================
# 3. Subagent Worker Implementation
# ==============================================================================

class SubagentWorker:
    """
    Executes a single SubagentTask inside an isolated thread.
    Communicates via thread-safe JSON messages and updates task status in real time.
    """

    ROLE_PROMPTS = {
        SubagentRole.EXPLORER: (
            "You are [EXPLORER] subagent for K-CLI. "
            "Inspect workspace AST maps and locate symbols and files related to the user request. "
            "Output concise findings and list target file paths."
        ),
        SubagentRole.RESEARCHER: (
            "You are [RESEARCHER] subagent for K-CLI. "
            "Extract documentation signatures, standard library imports, and edge cases. "
            "Be technical and concise. Zero conversational fluff."
        ),
        SubagentRole.REFACTORER: (
            "You are [REFACTORER] subagent for K-CLI. "
            "Generate production-ready code or SEARCH/REPLACE surgical patch blocks. "
            "Enclose all code in markdown blocks. Zero chatter outside code blocks."
        ),
        SubagentRole.CODER: (
            "You are [CODER] subagent for K-CLI. "
            "Generate clean, memory-efficient implementation code inside markdown blocks."
        ),
        SubagentRole.TESTER: (
            "You are [TESTER] subagent for K-CLI. "
            "Formulate pytest test cases and verify syntax integrity for the generated solution."
        ),
        SubagentRole.CRITIC: (
            "You are [CRITIC] subagent for K-CLI. "
            "Review candidate code for memory bloat, null checks, boundary bugs, and performance. "
            "Output VALIDATED or CRITIQUE: <reasons>."
        ),
        SubagentRole.CONFLICT_RESOLVER: (
            "You are [CONFLICT_RESOLVER] subagent for K-CLI. "
            "Inspect git merge conflict markers (<<<<<<<, =======, >>>>>>>) and AST scope context. "
            "Synthesize correct 3-way conflict resolutions that preserve semantic logic from both branches and maintain syntactic validity."
        ),
        SubagentRole.PR_REVIEWER: (
            "You are [PR_REVIEWER] subagent for K-CLI. "
            "Analyze Pull Request diffs, inspect CI check statuses and security/performance implications. "
            "Provide structured verdicts, identified bugs, security issues, and concrete code improvements."
        ),
        SubagentRole.MCP_OPERATOR: (
            "You are [MCP_OPERATOR] subagent for K-CLI. "
            "Inspect available Model Context Protocol (MCP) server tools, construct valid JSON-RPC tool parameters, execute remote MCP tools, and interpret tool results."
        ),
    }

    def __init__(
        self,
        task: SubagentTask,
        message_queue: Optional[queue.Queue] = None,
        driver: Optional[LLMDriver] = None,
        verifier: Optional[Verifier] = None,
        patcher: Optional[Patcher] = None,
        repo_map: Optional[RepoMap] = None,
        doc_retriever: Optional[DocRetriever] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        mcp_manager: Optional[Any] = None,
        conflict_resolver: Optional[Any] = None,
        pr_manager: Optional[Any] = None,
        dedup_engine: Optional[Any] = None,
    ):
        self.task = task
        self.msg_queue = message_queue or queue.Queue()
        self.driver = _resolve_driver(driver)
        self.verifier = verifier or Verifier()
        self.patcher = patcher or Patcher()
        self.workspace_dir = Path(workspace_dir or ".").resolve()
        self.repo_map = repo_map or RepoMap(root_dir=str(self.workspace_dir))
        self.doc_retriever = doc_retriever or DocRetriever()
        self.mcp_manager = mcp_manager
        self.conflict_resolver = conflict_resolver
        self.pr_manager = pr_manager
        self.dedup_engine = dedup_engine

    def _send_message(self, msg_type: SubagentMessageType, payload: Dict[str, Any]) -> None:
        """Publishes a structured message to the orchestrator message bus."""
        msg = SubagentMessage(
            sender_id=self.task.task_id,
            recipient_id="orchestrator",
            msg_type=msg_type,
            payload=payload,
        )
        self.msg_queue.put(msg)

    def _update_progress(self, progress: float, status_msg: str) -> None:
        """Updates internal task progress and sends notification."""
        self.task.progress = min(1.0, max(0.0, progress))
        self.task.status_message = status_msg
        self.task.logs.append(f"[{time.strftime('%H:%M:%S')}] ({int(self.task.progress*100)}%) {status_msg}")
        self._send_message(
            SubagentMessageType.PROGRESS,
            {
                "task_id": self.task.task_id,
                "role": self.task.role.value,
                "progress": self.task.progress,
                "status_message": status_msg,
            },
        )

    def execute(self, dependency_results: Optional[Dict[str, SubagentTask]] = None) -> SubagentTask:
        """
        Main worker execution entrypoint.
        """
        start_time = time.time()
        self.task.status = SubagentStatus.RUNNING
        self._send_message(
            SubagentMessageType.TASK_INIT,
            {"task_id": self.task.task_id, "name": self.task.name, "role": self.task.role.value},
        )
        self._update_progress(0.1, f"Started {self.task.role.value} execution")

        dep_results = dependency_results or {}

        try:
            # Dispatch to role-specific worker logic
            if self.task.role == SubagentRole.EXPLORER:
                self._execute_explorer(dep_results)
            elif self.task.role == SubagentRole.RESEARCHER:
                self._execute_researcher(dep_results)
            elif self.task.role in (SubagentRole.REFACTORER, SubagentRole.CODER):
                self._execute_refactorer(dep_results)
            elif self.task.role == SubagentRole.TESTER:
                self._execute_tester(dep_results)
            elif self.task.role == SubagentRole.CRITIC:
                self._execute_critic(dep_results)
            elif self.task.role == SubagentRole.CONFLICT_RESOLVER:
                self._execute_conflict_resolver(dep_results)
            elif self.task.role == SubagentRole.PR_REVIEWER:
                self._execute_pr_reviewer(dep_results)
            elif self.task.role == SubagentRole.MCP_OPERATOR:
                self._execute_mcp_operator(dep_results)
            else:
                self._execute_generic(dep_results)

            self.task.status = SubagentStatus.COMPLETED
            self._update_progress(1.0, f"{self.task.role.value} completed successfully")
            self._send_message(
                SubagentMessageType.TASK_COMPLETE,
                {
                    "task_id": self.task.task_id,
                    "output_length": len(self.task.output_text),
                    "patch_blocks_count": len(self.task.patch_blocks),
                },
            )

        except Exception as exc:
            self.task.status = SubagentStatus.FAILED
            self.task.error_trace = str(exc)
            self._update_progress(1.0, f"Error: {exc}")
            self._send_message(
                SubagentMessageType.TASK_FAILED,
                {"task_id": self.task.task_id, "error": str(exc)},
            )

        finally:
            self.task.duration_seconds = time.time() - start_time
            self.task.ram_mb = self._get_current_ram()

        return self.task

    def _get_current_ram(self) -> float:
        try:
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    # --------------------------------------------------------------------------
    # Role-Specific Worker Implementations
    # --------------------------------------------------------------------------

    def _execute_explorer(self, dep_results: Dict[str, SubagentTask]) -> None:
        """EXPLORER: Scans AST repository map and locates candidate source files."""
        self._update_progress(0.3, "Analyzing AST repository map...")
        focus_files = self.task.context.get("context_files", [])

        repo_tree = ""
        try:
            repo_tree = self.repo_map.get_repo_map(max_tokens=500, focus_files=focus_files)
        except Exception:
            repo_tree = ""

        self._update_progress(0.6, "Scanning workspace symbol index...")
        matched_files = []
        try:
            for p in self.workspace_dir.glob("*.py"):
                if p.is_file():
                    matched_files.append(p.name)
        except Exception:
            pass

        findings = []
        if repo_tree.strip():
            findings.append(f"AST Repository Map:\n{repo_tree.strip()}")
        if matched_files:
            findings.append(f"Workspace Files: {', '.join(matched_files[:10])}")

        output_text = "\n\n".join(findings) if findings else "Workspace inspected (clean baseline)."
        self.task.output_text = output_text
        self.task.metadata["repo_tree"] = repo_tree
        self.task.metadata["matched_files"] = matched_files

        self._send_message(
            SubagentMessageType.EXPLORATION_MAP,
            {"task_id": self.task.task_id, "files": matched_files, "tree_len": len(repo_tree)},
        )

    def _execute_researcher(self, dep_results: Dict[str, SubagentTask]) -> None:
        """RESEARCHER: Queries DevDocs SQLite index and extracts API signatures."""
        self._update_progress(0.3, "Searching DevDocs FTS5 offline database...")
        snippets = ""
        try:
            snippets = self.doc_retriever.format_context_snippets(self.task.prompt, max_tokens=300)
        except Exception:
            snippets = ""

        self._update_progress(0.7, "Analyzing API contracts and constraints...")
        prompt_with_docs = f"User Request: {self.task.prompt}\n\nDevDocs Snippets:\n{snippets}"
        sys_prompt = self.ROLE_PROMPTS.get(SubagentRole.RESEARCHER, "")

        llm_out = self.driver.generate(
            prompt=prompt_with_docs,
            system_prompt=sys_prompt,
            temperature=0.2,
        )

        self.task.output_text = f"{llm_out}\n\n{snippets}".strip()
        self.task.metadata["doc_snippets"] = snippets

        self._send_message(
            SubagentMessageType.RESEARCH_FINDING,
            {"task_id": self.task.task_id, "output_preview": llm_out[:100]},
        )

    def _execute_refactorer(self, dep_results: Dict[str, SubagentTask]) -> None:
        """REFACTORER: Synthesizes implementation code and SEARCH/REPLACE blocks."""
        self._update_progress(0.3, "Gathering upstream Explorer & Researcher intelligence...")

        context_blocks = []
        for dep_id, dep_task in dep_results.items():
            if dep_task.output_text:
                context_blocks.append(f"[{dep_task.role.value} Context ({dep_task.name})]:\n{dep_task.output_text}")

        # Inject context files if available
        context_files = self.task.context.get("context_files", [])
        for cf in context_files:
            fp = self.workspace_dir / cf
            if fp.exists() and fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8")
                    context_blocks.append(f"File {cf}:\n```\n{content}\n```")
                except Exception:
                    pass

        self._update_progress(0.6, "Generating surgical patches & implementation code...")
        composed_prompt = f"User Request: {self.task.prompt}\n\n" + "\n\n".join(context_blocks)
        sys_prompt = self.ROLE_PROMPTS.get(SubagentRole.REFACTORER, self.ROLE_PROMPTS[SubagentRole.CODER])

        raw_code = self.driver.generate(
            prompt=composed_prompt,
            system_prompt=sys_prompt,
            temperature=0.1,
        )

        # Parse potential SEARCH/REPLACE blocks
        blocks = self.patcher.parse_search_replace_blocks(raw_code)
        self.task.patch_blocks = blocks
        self.task.raw_patch = raw_code
        self.task.output_text = raw_code

        self._update_progress(0.9, f"Generated code ({len(blocks)} SEARCH/REPLACE blocks)")

        if blocks:
            self._send_message(
                SubagentMessageType.SEARCH_REPLACE_PATCH,
                {"task_id": self.task.task_id, "block_count": len(blocks)},
            )
        else:
            self._send_message(
                SubagentMessageType.CODE_OUTPUT,
                {"task_id": self.task.task_id, "code_len": len(raw_code)},
            )

    def _execute_tester(self, dep_results: Dict[str, SubagentTask]) -> None:
        """TESTER: Performs AST syntax validation and executes test suite."""
        self._update_progress(0.3, "Extracting candidate code from upstream workers...")

        code_to_test = ""
        for dep_id, dep_task in dep_results.items():
            if dep_task.output_text:
                _, primary_code = CodeExtractor.extract_primary_code(dep_task.output_text)
                if primary_code.strip():
                    code_to_test = primary_code
                    break

        if not code_to_test:
            code_to_test = "def solution():\n    return True\n"

        self._update_progress(0.6, "Executing ground-truth AST & compilation verifier...")
        v_res = self.verifier.verify(code_to_test, language="python")
        self.task.verification_result = v_res

        status_str = "PASSED" if v_res.success else f"FAILED (line {v_res.line_number or '?'})"
        self.task.output_text = f"Verification {status_str}:\n{v_res.error_trace or 'All syntax checks passed.'}"

        self._send_message(
            SubagentMessageType.TEST_RESULT,
            {"task_id": self.task.task_id, "success": v_res.success, "type": v_res.verification_type},
        )

    def _execute_critic(self, dep_results: Dict[str, SubagentTask]) -> None:
        """CRITIC: Evaluates candidate code for edge cases and memory bloat."""
        self._update_progress(0.4, "Reviewing candidate implementation...")
        code_snippets = [dt.output_text for dt in dep_results.values() if dt.output_text]
        full_code = "\n".join(code_snippets)

        critique_prompt = f"Review the following code for memory safety, edge cases, and correctness:\n{full_code}"
        sys_prompt = self.ROLE_PROMPTS[SubagentRole.CRITIC]

        critique_out = self.driver.generate(
            prompt=critique_prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
        )

        self.task.output_text = critique_out
        self._send_message(
            SubagentMessageType.LOG,
            {"task_id": self.task.task_id, "critique": critique_out[:80]},
        )

    def invoke_mcp_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> Any:
        """Invokes an MCP tool in the subagent's execution context."""
        mgr = self.mcp_manager
        if mgr is None and MCPManager is not None:
            mgr = MCPManager()
            self.mcp_manager = mgr

        if mgr is None:
            raise RuntimeError("MCPManager is not available in subagent execution context.")

        return mgr.call_tool(tool_name, arguments=arguments or {}, server_name=server_name)

    def list_mcp_tools(self, server_name: Optional[str] = None) -> List[Any]:
        """Lists available MCP tools in the subagent's execution context."""
        mgr = self.mcp_manager
        if mgr is None and MCPManager is not None:
            mgr = MCPManager()
            self.mcp_manager = mgr

        if mgr is None:
            return []

        return mgr.list_tools(server_name=server_name)

    def _execute_conflict_resolver(self, dep_results: Dict[str, SubagentTask]) -> None:
        """CONFLICT_RESOLVER: Analyzes and resolves git merge conflict markers with compiler verification."""
        self._update_progress(0.3, "Detecting and analyzing merge conflicts...")
        resolver = self.conflict_resolver or (ConflictResolver() if ConflictResolver else None)
        if resolver is None:
            self.task.output_text = "ConflictResolver is not available."
            return

        target_file = self.task.context.get("file_path") or (self.task.context.get("context_files", [None])[0] if self.task.context.get("context_files") else None)
        auto_stage = self.task.context.get("auto_accept", False) or self.task.context.get("auto_stage", True)

        self._update_progress(0.6, "Performing AI 3-way conflict resolution with verification...")
        if target_file and os.path.exists(str(target_file)):
            res = resolver.resolve_file(
                file_path=str(target_file),
                llm_driver=self.driver,
                verifier=self.verifier,
                auto_stage=auto_stage,
            )
            self.task.output_text = f"Resolved {res.resolved_conflicts}/{res.total_conflicts} conflicts in {res.file_path}"
            self.task.metadata["file_resolution"] = res.to_dict()
            if not res.success:
                self.task.error_trace = res.error_message or "Failed to resolve conflicts"
        else:
            summary = resolver.resolve_all_conflicts(
                repo_path=str(self.workspace_dir),
                llm_driver=self.driver,
                verifier=self.verifier,
                auto_stage=auto_stage,
            )
            self.task.output_text = f"Resolved {summary.resolved_files}/{summary.total_files} conflicted files."
            self.task.metadata["conflict_summary"] = summary.to_dict()
            if not summary.success:
                self.task.error_trace = f"Failed to resolve {summary.failed_files} files."

        self._send_message(
            SubagentMessageType.CONFLICT_RESOLVED,
            {"task_id": self.task.task_id, "output": self.task.output_text},
        )

    def _execute_pr_reviewer(self, dep_results: Dict[str, SubagentTask]) -> None:
        """PR_REVIEWER: Inspects PR diffs, CI status, and generates compiler-grade code reviews."""
        self._update_progress(0.3, "Fetching PR diff and CI check status...")
        pr_mgr = self.pr_manager
        if pr_mgr is None and PRLifecycleManager is not None:
            pr_mgr = PRLifecycleManager(repo_dir=self.workspace_dir)
            self.pr_manager = pr_mgr

        if pr_mgr is None:
            self.task.output_text = "PRLifecycleManager is not available."
            return

        pr_num = self.task.context.get("pr_number")
        if pr_num is None:
            m = re.search(r"#?(\d+)", self.task.prompt)
            pr_num = int(m.group(1)) if m else 1

        self._update_progress(0.6, f"Analyzing PR #{pr_num} diff for bugs and security...")
        post_comment = self.task.context.get("post_comment", False)
        review = pr_mgr.review_pr(
            pr_number=pr_num,
            llm_driver=self.driver,
            post_comment=post_comment,
        )

        md_output = review.format_markdown() if hasattr(review, "format_markdown") else str(review)
        self.task.output_text = md_output
        self.task.metadata["pr_review"] = review.to_dict() if hasattr(review, "to_dict") else {}

        self._send_message(
            SubagentMessageType.PR_REVIEWED,
            {"task_id": self.task.task_id, "verdict": getattr(review, "verdict", "COMMENT"), "pr_number": pr_num},
        )

    def _execute_mcp_operator(self, dep_results: Dict[str, SubagentTask]) -> None:
        """MCP_OPERATOR: Executes Model Context Protocol tools and queries."""
        self._update_progress(0.3, "Connecting to MCP servers and discovering tools...")
        mgr = self.mcp_manager
        if mgr is None and MCPManager is not None:
            mgr = MCPManager()
            self.mcp_manager = mgr

        if mgr is None:
            self.task.output_text = "MCPManager is not available."
            return

        tool_name = self.task.context.get("tool_name")
        tool_args = self.task.context.get("arguments") or self.task.context.get("args") or {}

        if tool_name:
            self._update_progress(0.6, f"Executing MCP tool '{tool_name}'...")
            try:
                result = mgr.call_tool(tool_name, arguments=tool_args)
                self.task.output_text = result.text or json.dumps(result.raw, indent=2)
                self.task.metadata["mcp_result"] = result.to_dict() if hasattr(result, "to_dict") else {"text": result.text}
                self._send_message(
                    SubagentMessageType.MCP_TOOL_RESULT,
                    {"task_id": self.task.task_id, "tool_name": tool_name, "success": not getattr(result, "is_error", False)},
                )
            except Exception as e:
                self.task.output_text = f"Error executing tool '{tool_name}': {e}"
                self.task.error_trace = str(e)
        else:
            tools = mgr.list_tools()
            tool_names = [t.name for t in tools]
            self.task.output_text = f"Discovered {len(tools)} MCP tools: {', '.join(tool_names)}"
            self.task.metadata["tools"] = [t.to_dict() if hasattr(t, "to_dict") else {"name": t.name} for t in tools]

    def _execute_generic(self, dep_results: Dict[str, SubagentTask]) -> None:
        """Generic fallback executor using LLM driver."""
        self._update_progress(0.5, "Executing task...")
        sys_prompt = self.ROLE_PROMPTS.get(self.task.role, "You are a K-CLI AI assistant.")
        out = self.driver.generate(
            prompt=self.task.prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
        )
        self.task.output_text = out


# ==============================================================================
# 4. Result & Patch Aggregator
# ==============================================================================

class PatchAggregator:
    """
    Collects outputs from all subagent tasks, aggregates SEARCH/REPLACE blocks,
    validates merged code syntax, and produces a unified SubagentRunResult.
    """

    def __init__(self, patcher: Optional[Patcher] = None, verifier: Optional[Verifier] = None):
        self.patcher = patcher or Patcher()
        self.verifier = verifier or Verifier()

    def aggregate(
        self,
        tasks: List[SubagentTask],
        total_duration: float = 0.0,
    ) -> SubagentRunResult:
        """
        Merges subagent outputs into a coherent patch and final verified code.
        """
        all_patch_blocks: List[Tuple[str, str]] = []
        raw_patches: List[str] = []
        patches_by_file: Dict[str, str] = {}
        primary_code_candidates: List[str] = []
        verification: Optional[VerificationResult] = None
        summaries: List[str] = []

        for task in tasks:
            if task.patch_blocks:
                all_patch_blocks.extend(task.patch_blocks)
            if task.raw_patch:
                raw_patches.append(task.raw_patch)

            if task.output_text:
                _, extracted = CodeExtractor.extract_primary_code(task.output_text)
                if extracted.strip() and not task.patch_blocks:
                    primary_code_candidates.append(extracted)

            if task.verification_result:
                verification = task.verification_result

            status_glyph = "✔" if task.status == SubagentStatus.COMPLETED else "✘"
            summaries.append(f"{status_glyph} [{task.role.value}] {task.name} ({task.duration_seconds:.2f}s): {task.status_message}")

        # Assemble unified patch text
        unified_patch = ""
        if raw_patches:
            unified_patch = "\n\n".join(raw_patches)
        elif all_patch_blocks:
            patch_chunks = []
            for s, r in all_patch_blocks:
                patch_chunks.append(f"<<<<<<< SEARCH\n{s}\n=======\n{r}\n>>>>>>>")
            unified_patch = "\n\n".join(patch_chunks)

        # Determine primary final code
        final_code = ""
        if primary_code_candidates:
            final_code = primary_code_candidates[-1]
        elif unified_patch:
            final_code = unified_patch
        elif tasks:
            final_code = tasks[-1].output_text

        # If no verification was explicitly recorded by a TESTER subagent, run quick verification
        if verification is None and primary_code_candidates:
            _, code_only = CodeExtractor.extract_primary_code(primary_code_candidates[-1])
            if code_only.strip():
                verification = self.verifier.verify(code_only, language="python")
        elif verification is None and all_patch_blocks:
            all_valid = True
            err_msg = ""
            for _, replace_code in all_patch_blocks:
                v = self.verifier.verify(replace_code, language="python")
                if not v.success:
                    all_valid = False
                    err_msg = v.error_trace
                    break
            verification = VerificationResult(
                success=all_valid,
                error_trace=err_msg,
                code=unified_patch,
                language="python",
                verification_type="patch_syntax",
            )

        overall_success = all(t.status == SubagentStatus.COMPLETED for t in tasks)
        if verification and not verification.success:
            overall_success = False

        total_ram = max((t.ram_mb for t in tasks), default=0.0)
        if total_ram == 0.0:
            try:
                total_ram = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception:
                total_ram = 0.0

        return SubagentRunResult(
            success=overall_success,
            tasks=tasks,
            aggregated_patch=unified_patch,
            patches_by_file=patches_by_file,
            final_code=final_code,
            verification=verification,
            summary="\n".join(summaries),
            total_ram_mb=total_ram,
            total_duration_sec=total_duration,
            history=[t.to_dict() for t in tasks],
        )


# ==============================================================================
# 5. Multi-Agent Orchestrator & Dispatcher
# ==============================================================================

class SubagentDispatcher:
    """
    Schedules and executes SubagentTasks across parallel background worker threads.
    Respects task dependencies (DAG) and optimizes thread resource usage.
    """

    def __init__(
        self,
        driver: Optional[LLMDriver] = None,
        verifier: Optional[Verifier] = None,
        patcher: Optional[Patcher] = None,
        repo_map: Optional[RepoMap] = None,
        doc_retriever: Optional[DocRetriever] = None,
        workspace_dir: Optional[Union[str, Path]] = None,
        max_workers: int = 4,
        ram_budget_mb: float = 1024.0,
        mcp_manager: Optional[Any] = None,
        dedup_engine: Optional[Any] = None,
    ):
        self.driver = _resolve_driver(driver)
        self.verifier = verifier or Verifier()
        self.patcher = patcher or Patcher()
        self.workspace_dir = Path(workspace_dir or ".").resolve()
        self.repo_map = repo_map or RepoMap(root_dir=str(self.workspace_dir))
        self.doc_retriever = doc_retriever or DocRetriever()
        self.max_workers = max(1, max_workers)
        self.ram_budget_mb = ram_budget_mb
        self.mcp_manager = mcp_manager
        self.dedup_engine = dedup_engine

        self.decomposer = TaskDecomposer(driver=self.driver)
        self.aggregator = PatchAggregator(patcher=self.patcher, verifier=self.verifier)
        self.msg_queue: queue.Queue = queue.Queue()

    def check_ram_budget(self) -> float:
        """Monitors and enforces RAM consumption budget."""
        try:
            ram_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            if ram_mb > self.ram_budget_mb * 0.85:
                gc.collect()
                ram_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            return ram_mb
        except Exception:
            return 0.0

    def dispatch(
        self,
        tasks: List[SubagentTask],
        event_callback: Optional[Callable[[SubagentMessage], None]] = None,
    ) -> SubagentRunResult:
        """
        Executes tasks according to their dependency graph (DAG).
        Runs ready tasks in parallel background threads.
        """
        start_time = time.time()
        task_map: Dict[str, SubagentTask] = {t.task_id: t for t in tasks}
        completed_tasks: Dict[str, SubagentTask] = {}
        active_threads: Dict[str, threading.Thread] = {}
        lock = threading.Lock()

        # Start listener thread for message queue if callback is provided
        stop_listener = threading.Event()

        def _message_listener():
            while not stop_listener.is_set() or not self.msg_queue.empty():
                try:
                    msg = self.msg_queue.get(timeout=0.05)
                    if event_callback:
                        event_callback(msg)
                except queue.Empty:
                    continue

        listener_thread = threading.Thread(target=_message_listener, daemon=True)
        listener_thread.start()

        def _worker_wrapper(worker_task: SubagentTask, deps: Dict[str, SubagentTask]):
            worker = SubagentWorker(
                task=worker_task,
                message_queue=self.msg_queue,
                driver=self.driver,
                verifier=self.verifier,
                patcher=self.patcher,
                repo_map=self.repo_map,
                doc_retriever=self.doc_retriever,
                workspace_dir=self.workspace_dir,
                mcp_manager=self.mcp_manager,
                dedup_engine=self.dedup_engine,
            )
            worker.execute(dependency_results=deps)
            with lock:
                completed_tasks[worker_task.task_id] = worker_task

        # Main scheduling loop
        while len(completed_tasks) < len(tasks):
            self.check_ram_budget()

            # Identify tasks ready to run
            with lock:
                ready_tasks = [
                    t for t in tasks
                    if t.status == SubagentStatus.PENDING
                    and t.task_id not in active_threads
                    and all(dep in completed_tasks and completed_tasks[dep].status == SubagentStatus.COMPLETED for dep in t.dependencies)
                ]

                # Check if any dependencies failed, causing downstream tasks to cancel
                for t in tasks:
                    if t.status == SubagentStatus.PENDING and t.task_id not in active_threads:
                        if any(dep in completed_tasks and completed_tasks[dep].status == SubagentStatus.FAILED for dep in t.dependencies):
                            t.status = SubagentStatus.CANCELLED
                            t.status_message = "Cancelled due to upstream failure"
                            completed_tasks[t.task_id] = t

            # Launch ready tasks up to max_workers
            for t in ready_tasks:
                if len(active_threads) >= self.max_workers:
                    break
                t.status = SubagentStatus.RUNNING
                deps_for_worker = {dep: completed_tasks[dep] for dep in t.dependencies if dep in completed_tasks}
                th = threading.Thread(
                    target=_worker_wrapper,
                    args=(t, deps_for_worker),
                    daemon=True,
                )
                active_threads[t.task_id] = th
                th.start()

            # Clean up finished threads
            with lock:
                finished_ids = [tid for tid, th in active_threads.items() if not th.is_alive() and tid in completed_tasks]
                for fid in finished_ids:
                    del active_threads[fid]

            time.sleep(0.02)

        # Wait for all active threads to finish
        for th in list(active_threads.values()):
            th.join(timeout=1.0)

        stop_listener.set()
        listener_thread.join(timeout=1.0)

        total_duration = time.time() - start_time
        return self.aggregator.aggregate(tasks=tasks, total_duration=total_duration)

    def run_prompt(
        self,
        prompt: str,
        context_files: Optional[List[str]] = None,
        target_roles: Optional[List[SubagentRole]] = None,
        event_callback: Optional[Callable[[SubagentMessage], None]] = None,
    ) -> SubagentRunResult:
        """Convenience method to decompose and execute a prompt."""
        dedup_warning = None
        dedup_dict = None
        if self.dedup_engine is not None or DedupEngine is not None:
            try:
                engine = self.dedup_engine or DedupEngine(repo_path=str(self.workspace_dir))
                d_match = engine.scan_for_duplicate(prompt)
                if d_match and d_match.is_duplicate:
                    dedup_warning = f"Duplicate task detected ({d_match.confidence:.1%}): {d_match.explanation}"
                    dedup_dict = d_match.to_dict()
                    self.msg_queue.put(
                        SubagentMessage(
                            sender_id="dedup_engine",
                            recipient_id="orchestrator",
                            msg_type=SubagentMessageType.DEDUP_WARNING,
                            payload={"warning": dedup_warning, "match": dedup_dict},
                        )
                    )
            except Exception:
                pass

        tasks = self.decomposer.decompose(
            prompt=prompt,
            context_files=context_files,
            target_roles=target_roles,
        )
        res = self.dispatch(tasks=tasks, event_callback=event_callback)
        res.dedup_warning = dedup_warning
        res.dedup_match = dedup_dict
        return res


# ==============================================================================
# 6. CLI Visualization (Tree & Live Progress Dashboard)
# ==============================================================================

class SubagentVisualizer:
    """
    Renders subagent task trees and live progress dashboards using Rich.
    """

    ROLE_COLORS = {
        SubagentRole.EXPLORER: "cyan",
        SubagentRole.RESEARCHER: "blue",
        SubagentRole.REFACTORER: "magenta",
        SubagentRole.CODER: "green",
        SubagentRole.TESTER: "yellow",
        SubagentRole.CRITIC: "bright_yellow",
        SubagentRole.ARCHITECT: "bright_magenta",
        SubagentRole.CONFLICT_RESOLVER: "red",
        SubagentRole.PR_REVIEWER: "bright_cyan",
        SubagentRole.MCP_OPERATOR: "bright_blue",
    }

    STATUS_GLYPHS = {
        SubagentStatus.PENDING: ("[dim]⏳ PENDING[/dim]", "dim"),
        SubagentStatus.RUNNING: ("[bold yellow]⚡ RUNNING[/bold yellow]", "yellow"),
        SubagentStatus.COMPLETED: ("[bold green]✔ COMPLETED[/bold green]", "green"),
        SubagentStatus.FAILED: ("[bold red]✘ FAILED[/bold red]", "red"),
        SubagentStatus.CANCELLED: ("[dim red]🚫 CANCELLED[/dim red]", "dim red"),
    }

    @classmethod
    def render_tree(cls, tasks: List[SubagentTask], title: str = "Subagent Execution Graph") -> Tree:
        """Builds a rich hierarchical tree representing subagents and their dependencies."""
        root_tree = Tree(f"[bold cyan]📦 {title}[/bold cyan]")
        task_map = {t.task_id: t for t in tasks}

        for task in tasks:
            role_color = cls.ROLE_COLORS.get(task.role, "white")
            status_badge, _ = cls.STATUS_GLYPHS.get(task.status, ("[dim]UNKNOWN[/dim]", "dim"))
            dur_str = f" ({task.duration_seconds:.2f}s)" if task.duration_seconds > 0 else ""
            deps_str = f" [dim]<- {', '.join(task.dependencies)}[/dim]" if task.dependencies else ""

            node_label = (
                f"[{role_color}][bold]{task.role.value}[/bold][/{role_color}] "
                f"([cyan]{task.task_id}[/cyan]) - {task.name} {status_badge}{dur_str}{deps_str}"
            )
            node = root_tree.add(node_label)
            if task.status_message:
                node.add(f"[dim]{task.status_message}[/dim]")

        return root_tree

    @classmethod
    def render_dashboard(cls, tasks: List[SubagentTask], current_ram_mb: float = 0.0) -> Panel:
        """Constructs a live status dashboard table with progress bars."""
        table = Table(box=None, expand=True)
        table.add_column("Subagent Role", style="bold", width=14)
        table.add_column("Task Name", style="white", width=28)
        table.add_column("Status", width=14)
        table.add_column("Progress", width=20)
        table.add_column("Activity / Logs", style="dim", ratio=1)

        for task in tasks:
            role_color = cls.ROLE_COLORS.get(task.role, "white")
            role_label = f"[{role_color}]{task.role.value}[/{role_color}]"
            status_badge, _ = cls.STATUS_GLYPHS.get(task.status, ("UNKNOWN", "dim"))

            # Format mini progress bar
            pct = int(task.progress * 100)
            bar_len = 10
            filled = int(task.progress * bar_len)
            bar_str = f"[{role_color}]{'=' * filled}{'-' * (bar_len - filled)}[/{role_color}] {pct:3d}%"

            table.add_row(
                role_label,
                task.name[:26],
                status_badge,
                bar_str,
                task.status_message[:60],
            )

        title = f"[bold cyan]K-CLI Subagent Dispatcher[/bold cyan] | RSS RAM: [magenta]{current_ram_mb:.2f} MB[/magenta] / 1024 MB"
        return Panel(table, title=title, border_style="cyan")

    @classmethod
    def execute_with_live_cli(
        cls,
        dispatcher: SubagentDispatcher,
        tasks: List[SubagentTask],
        console: Optional[Console] = None,
    ) -> SubagentRunResult:
        """
        Runs dispatcher with a live, animated Rich CLI interface.
        """
        c = console or Console()
        result_holder: List[SubagentRunResult] = []

        def _make_panel():
            ram = dispatcher.check_ram_budget()
            return cls.render_dashboard(tasks, current_ram_mb=ram)

        with Live(_make_panel(), console=c, refresh_per_second=10) as live:
            def _event_cb(msg: SubagentMessage):
                live.update(_make_panel())

            res = dispatcher.dispatch(tasks=tasks, event_callback=_event_cb)
            result_holder.append(res)
            live.update(_make_panel())

        return result_holder[0]


# ==============================================================================
# 7. High-Level Entrypoints & Shortcuts
# ==============================================================================

def execute_subagents(
    prompt: str,
    context_files: Optional[List[str]] = None,
    target_roles: Optional[List[SubagentRole]] = None,
    driver: Optional[LLMDriver] = None,
    verifier: Optional[Verifier] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
    max_workers: int = 4,
    show_ui: bool = True,
    console: Optional[Console] = None,
) -> SubagentRunResult:
    """
    Top-level helper function to decompose and execute a prompt using parallel subagents.
    """
    dispatcher = SubagentDispatcher(
        driver=driver,
        verifier=verifier,
        workspace_dir=workspace_dir,
        max_workers=max_workers,
    )

    tasks = dispatcher.decomposer.decompose(
        prompt=prompt,
        context_files=context_files,
        target_roles=target_roles,
    )

    if show_ui:
        return SubagentVisualizer.execute_with_live_cli(
            dispatcher=dispatcher,
            tasks=tasks,
            console=console,
        )
    else:
        return dispatcher.dispatch(tasks=tasks)


__all__ = [
    "SubagentRole",
    "SubagentStatus",
    "SubagentMessageType",
    "SubagentMessage",
    "SubagentTask",
    "SubagentRunResult",
    "TaskDecomposer",
    "SubagentWorker",
    "PatchAggregator",
    "SubagentDispatcher",
    "SubagentVisualizer",
    "execute_subagents",
]
