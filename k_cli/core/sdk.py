"""
sdk.py - Universal Python SDK & Agentic Framework for K-CLI
Project Bankai Engine v1.0.0

Provides a clean, unified Python API for programmatic integration:
```python
from k_cli import KCLI

# 1. Initialize K-CLI Agent
with KCLI(model="deepseek-reasoner", local_fallback="qwen2.5-coder:1.5b") as kcli:
    # 2. Multi-Model Inference
    response = kcli.generate("Write a lock-free queue in C++23")

    # 3. Autonomous GitHub Agent
    kcli.github.solve_issue(12, auto_pr=True)
    kcli.github.create_release(tag_name="v1.0.0")

    # 4. Conflict Resolution & Security Healing
    kcli.conflicts.resolve_all()
    kcli.security.heal_all()

    # 5. Visual Architecture Diagrams
    kcli.diagrams.generate_mermaid_architecture(output_file="ARCHITECTURE.md")
```
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from k_cli.core.llm_driver import LLMDriver, ProviderType
from k_cli.core.models_hub import ModelBenchmarkResult, ModelHub, ModelSpec
from k_cli.github.github_engine import GitHubEngine, IssueSolveResult
from k_cli.github.github_client import GitHubClient, PRLifecycleManager
from k_cli.git.conflict_resolver import ConflictResolver, ConflictSummary
from k_cli.github.dedup_engine import DedupEngine, DedupMatch
from k_cli.tools.mcp_client import MCPManager
from k_cli.tools.incident_triage import IncidentHealResult, IncidentReport, IncidentTriageEngine
from k_cli.tools.diagram_generator import DiagramGenerator
from k_cli.git.smart_git import SmartCommitProposal, SmartGitEngine
from k_cli.tools.security_healer import SecurityHealer, VulnerabilityHealResult, SecurityScanReport
from k_cli.git.verifier import Verifier
from k_cli.git.patcher import Patcher
from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult
from k_cli.core.session import SessionManager
from dataclasses import dataclass, field


@dataclass
class PlanResult:
    """Result of a planning operation with optional deduplication warning."""
    goal: str
    steps: List[str] = field(default_factory=list)
    dedup_warning: Optional[str] = None
    dedup_match: Optional[Dict[str, Any]] = None

    workspace: Optional[Path] = None
    relevant_files: List[str] = field(default_factory=list)
    detected_tools: List[str] = field(default_factory=list)
    repo_map: str = ""
    project_guidance: Optional[str] = None

    def render_markdown(self) -> str:
        """Render the plan as a markdown string."""
        lines = ["# protected plan", f"## Plan: {self.goal}", ""]
        if self.project_guidance:
            lines += ["### Project guidance", self.project_guidance, ""]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step}")
        if self.dedup_warning:
            lines += ["", f"> **Deduplication warning**: {self.dedup_warning}"]
        return "\n".join(lines)


def create_plan(
    goal: str,
    workspace_dir: Union[str, Path] = ".",
    max_files: int = 10,
) -> PlanResult:
    """Generate a protected, read-only change plan with deduplication check."""
    workspace_path = Path(workspace_dir).resolve()
    dedup = DedupEngine()
    match = dedup.scan_for_duplicate(query=goal, repo_path=str(workspace_path))
    warning = None
    match_info = None
    if match and match.is_duplicate and match.confidence > 0.6:
        warning = f"Similar work detected (confidence {match.confidence:.0%}): {match.explanation}"
        match_info = {"is_duplicate": True, "confidence": match.confidence, "explanation": match.explanation}
    steps = [
        f"Analyse codebase and understand context for: {goal}",
        "Identify files and modules that need to change",
        "Generate a minimal surgical diff",
        "Verify changes with AST parser and project tests",
        "Commit with conventional message and open PR",
    ]
    return PlanResult(
        goal=goal,
        steps=steps,
        dedup_warning=warning,
        dedup_match=match_info,
        workspace=workspace_path,
    )

logger = logging.getLogger("k_cli.sdk")


class KCLI:
    """
    Main K-CLI Agentic SDK Client.
    Provides direct programmatic access to all local & cloud AI models,
    autonomous GitHub operations, merge conflict resolvers, and security healers.
    """

    def __init__(
        self,
        model: str = "qwen2.5-coder:1.5b",
        provider: Optional[Union[ProviderType, str]] = None,
        repo_path: str = ".",
        mock_mode: bool = False,
        github_token: Optional[str] = None,
        ram_budget_mb: float = 1024.0,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.active_model_name = model
        self.mock_mode = mock_mode

        # Core Engines
        self.models = ModelHub()
        self.verifier = Verifier()
        self.patcher = Patcher()
        self.driver = LLMDriver(
            model_name=model,
            provider=provider,
            mock_mode=mock_mode,
        )
        self.dedup = DedupEngine(repo_path=str(self.repo_path))
        self.orchestrator = Orchestrator(
            driver=self.driver,
            verifier=self.verifier,
            dedup_engine=self.dedup,
            ram_budget_mb=ram_budget_mb,
        )
        self.session = SessionManager(
            workspace_dir=str(self.repo_path),
            model_name=model,
            mock_mode=mock_mode,
        )

        # Specialized Tooling
        self.github = GitHubEngine(token=github_token, repo_path=str(self.repo_path))
        self.pr_lifecycle = PRLifecycleManager(client=GitHubClient(token=github_token))
        self.github.client = self.pr_lifecycle.client
        self.conflicts = ConflictResolver()
        self.mcp = MCPManager()
        self.security = SecurityHealer(repo_path=str(self.repo_path), llm_driver=self.driver)
        self.triage = IncidentTriageEngine(repo_path=str(self.repo_path))
        self.diagrams = DiagramGenerator(repo_path=str(self.repo_path))
        self.smart_git = SmartGitEngine(repo_path=str(self.repo_path), llm_driver=self.driver)

    def __enter__(self) -> KCLI:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    # =========================================================================
    # High-Level Agent Methods
    # =========================================================================

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generates AI response across any local or cloud model."""
        target_driver = self.driver
        if model and model != self.active_model_name:
            target_driver = LLMDriver(model_name=model, mock_mode=self.mock_mode)

        return target_driver.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            stream_callback=stream_callback,
        )

    def run(
        self,
        task: str,
        language: str = "python",
        test_code: Optional[str] = None,
        stream_callback: Optional[Callable[[Any, str], None]] = None,
    ) -> OrchestratorResult:
        """Executes full verified 5-stage persona pipeline."""
        return self.orchestrator.execute_pipeline(
            user_prompt=task,
            language=language,
            test_code=test_code,
            token_stream_callback=stream_callback,
        )

    def plan(self, goal: str, max_files: int = 10) -> PlanResult:
        """Generates a protected, read-only change plan with deduplication check."""
        return create_plan(
            goal=goal,
            workspace_dir=str(self.repo_path),
            max_files=max_files,
        )

    def resolve_conflicts(self, repo_path: Optional[str] = None) -> ConflictSummary:
        """Automatically resolves all git merge conflicts with compiler verification."""
        target_path = repo_path or str(self.repo_path)
        return self.conflicts.resolve_all_conflicts(
            repo_path=target_path,
            llm_driver=self.driver,
            verifier=self.verifier,
        )

    def solve_issue(self, issue_number: int, auto_pr: bool = True) -> IssueSolveResult:
        """Autonomously investigates, fixes, verifies, and PRs a GitHub issue."""
        return self.github.solve_issue(
            issue_number=issue_number,
            llm_driver=self.driver,
            verifier=self.verifier,
            patcher=self.patcher,
            auto_pr=auto_pr,
        )

    def scan_security(self) -> SecurityScanReport:
        """Scans repository for security vulnerabilities."""
        return self.security.scan_repository()

    def heal_security(self) -> List[VulnerabilityHealResult]:
        """Scans and surgically auto-heals security vulnerabilities."""
        return self.security.heal_all_vulnerabilities(
            verifier=self.verifier,
            patcher=self.patcher,
            llm_driver=self.driver,
        )

    def generate_diagram(self, output_file: Optional[str] = None) -> str:
        """Generates visual Mermaid architecture diagrams."""
        return self.diagrams.generate_mermaid_architecture(output_file=output_file)

    def commit(self, push: bool = False) -> SmartCommitProposal:
        """Generates AST Conventional Commit and optionally pushes."""
        proposal = self.smart_git.generate_smart_commit()
        if proposal.subject:
            self.smart_git.auto_stage_and_commit(message=proposal.full_message, push=push)
        return proposal

    # =========================================================================
    # 10 Killer Agentic Features
    # =========================================================================

    def watch_prs(self, interval_seconds: int = 30, max_iterations: Optional[int] = 1, auto_merge: bool = False) -> List[Any]:
        """Feature 1: Autonomous PR Review & Watcher Daemon."""
        from k_cli.github.pr_watcher import PRWatcherDaemon
        daemon = PRWatcherDaemon(
            repo_path=str(self.repo_path),
            github_client=self.github.client if hasattr(self.github, "client") else None,
            llm_driver=self.driver,
            auto_merge_approved=auto_merge,
        )
        return daemon.run_loop(interval_seconds=interval_seconds, max_iterations=max_iterations)

    def bisect(self, test_command: str = "pytest tests/ -q", good_commit: str = "HEAD~5", bad_commit: str = "HEAD") -> Any:
        """Feature 2: AI-Powered Git Bisect & Regression Hunter."""
        from k_cli.git.ai_bisect import AIBisectEngine
        engine = AIBisectEngine(repo_path=str(self.repo_path), llm_driver=self.driver, verifier=self.verifier, patcher=self.patcher)
        return engine.run_bisect(test_command=test_command, good_commit=good_commit, bad_commit=bad_commit)

    def route(self, task_prompt: str) -> Any:
        """Feature 3: Cost & Latency Smart Model Router."""
        from k_cli.core.smart_router import SmartModelRouter
        router = SmartModelRouter(hub=self.models)
        return router.route(task_prompt=task_prompt)

    def garden(self) -> Any:
        """Feature 4: Nightly Autonomous Repo Maintenance & Health Engine."""
        from k_cli.tools.repo_gardener import RepoGardener
        gardener = RepoGardener(repo_path=str(self.repo_path))
        return gardener.run_garden_sweep()

    def explain(self, query: str) -> Any:
        """Feature 5: Codebase Natural Language Search & Semantic Q&A."""
        from k_cli.tools.codebase_qa import CodebaseQAEngine
        qa = CodebaseQAEngine(repo_path=str(self.repo_path), llm_driver=self.driver)
        return qa.ask(query=query)

    def ghost(self, command_str: str) -> int:
        """Feature 6: Ghost Terminal Autopilot & Error Healer Daemon."""
        from k_cli.tools.ghost_daemon import GhostTerminalDaemon
        ghost_d = GhostTerminalDaemon(repo_path=str(self.repo_path), llm_driver=self.driver, verifier=self.verifier, patcher=self.patcher)
        return ghost_d.run_wrapped_command(command_str=command_str)

    def swarm_adversarial(self, task_prompt: str, language: str = "python") -> Any:
        """Feature 7: Adversarial Red Team / Blue Team Consensus Loop."""
        from k_cli.agents.adversarial_swarm import AdversarialConsensusSwarm
        swarm = AdversarialConsensusSwarm(llm_driver=self.driver, verifier=self.verifier)
        return swarm.run_consensus(task_prompt=task_prompt, language=language)

    def synapse(self, query: str) -> Any:
        """Feature 8: AST Neural Code Graph & Context Compressor."""
        from k_cli.tools.synapse_graph import SynapseCodeGraph
        graph = SynapseCodeGraph(repo_path=str(self.repo_path))
        return graph.extract_subgraph_slice(query=query)

    def airgap(self) -> Any:
        """Feature 9: Sovereign Air-Gapped Offline Engine."""
        from k_cli.core.airgap import AirgapManager
        mgr = AirgapManager()
        return mgr.audit_environment()

    def scaffold(self, spec_prompt: str, target_dir: str = "./scaffolded_app", write_to_disk: bool = False) -> Any:
        """Feature 10: Natural Language Full-Stack Scaffolder."""
        from k_cli.agents.scaffold_engine import FullStackScaffolder
        scaffolder = FullStackScaffolder(llm_driver=self.driver, verifier=self.verifier)
        return scaffolder.scaffold(spec_prompt=spec_prompt, target_dir=target_dir, write_to_disk=write_to_disk)
