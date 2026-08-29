"""K-CLI: AI-powered agentic developer workstation for the terminal."""

import warnings
warnings.filterwarnings("ignore")

__version__ = "1.0.0"

from k_cli.core.credentials import CredentialsManager, SUPPORTED_KEYS
CredentialsManager.load_all_credentials()

# ── Core AI & SDK ──────────────────────────────────────────────────────────
from k_cli.core.sdk import KCLI, PlanResult, create_plan
from k_cli.core.models_hub import ModelBenchmarkResult, ModelHub, ModelProvider, ModelSpec
from k_cli.core.llm_driver import LLMDriver, ProviderType
from k_cli.core.session import SessionManager
from k_cli.core.smart_router import SmartModelRouter, RouteDecision, TaskTier
from k_cli.core.airgap import AirgapManager, AirgapAuditReport

# ── GitHub & Deduplication ─────────────────────────────────────────────────
from k_cli.github.github_engine import GitHubEngine, GitHubIssue, GitHubRelease, IssueSolveResult, WorkflowRun
from k_cli.github.github_client import CIStatus, GitHubAPIError, GitHubClient, PRFixResult, PRLifecycleManager, PRReviewResult, PullRequest
from k_cli.github.dedup_engine import CommitRecord, DedupEngine, DedupMatch, SimilarityScorer, SymbolRecord
from k_cli.github.pr_watcher import PRWatcherDaemon, WatchEvent

# ── Git & Code Patching ────────────────────────────────────────────────────
from k_cli.git.conflict_resolver import ConflictBlock, ConflictResolution, ConflictResolver, ConflictSummary, FileResolutionResult
from k_cli.git.smart_git import AtomicCommitGroup, CommitType, FileChangeAnalysis, PRDescriptionProposal, SmartCommitProposal, SmartGitEngine
from k_cli.git.verifier import Verifier, VerificationResult
from k_cli.git.patcher import Patcher
from k_cli.git.ai_bisect import AIBisectEngine, BisectResult, BisectStep

# ── Agents & Orchestration ─────────────────────────────────────────────────
from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult, Persona
from k_cli.agents.subagents import SubagentDispatcher, SubagentRole, SubagentStatus
from k_cli.agents.adversarial_swarm import AdversarialConsensusSwarm, SwarmConsensusResult, AdversarialAttack
from k_cli.agents.scaffold_engine import FullStackScaffolder, ScaffoldResult, GeneratedFile

# ── Tools & Diagnostics ───────────────────────────────────────────────────
from k_cli.tools.security_healer import SecurityHealer, SecurityScanReport, VulnerabilityFinding, VulnerabilityHealResult, VulnerabilitySeverity, VulnerabilityType
from k_cli.tools.incident_triage import IncidentHealResult, IncidentReport, IncidentTriageEngine, LogType, StackFrame
from k_cli.tools.diagram_generator import DiagramGenerator, DiagramType
from k_cli.tools.mcp_client import MCPClient, MCPManager, MCPPrompt, MCPResource, MCPServerConfig, MCPTool, MCPToolResult
from k_cli.tools.repo_gardener import RepoGardener, GardenReport, GardenFinding
from k_cli.tools.codebase_qa import CodebaseQAEngine, QAResult
from k_cli.tools.ghost_daemon import GhostTerminalDaemon, GhostHealPrompt
from k_cli.tools.synapse_graph import SynapseCodeGraph, SynapseSlice, CodeNode

__all__ = [
    # Core
    "KCLI", "PlanResult", "create_plan", "ModelHub", "ModelSpec", "ModelProvider", "ModelBenchmarkResult",
    "LLMDriver", "ProviderType", "SessionManager", "SmartModelRouter", "RouteDecision", "TaskTier",
    "AirgapManager", "AirgapAuditReport",
    # GitHub
    "GitHubEngine", "GitHubIssue", "GitHubRelease", "WorkflowRun", "IssueSolveResult",
    "GitHubClient", "PRLifecycleManager", "PullRequest", "CIStatus", "PRReviewResult", "PRFixResult", "GitHubAPIError",
    "DedupEngine", "DedupMatch", "CommitRecord", "SimilarityScorer", "SymbolRecord",
    "PRWatcherDaemon", "WatchEvent",
    # Git
    "ConflictBlock", "ConflictResolution", "ConflictResolver", "ConflictSummary", "FileResolutionResult",
    "SmartGitEngine", "SmartCommitProposal", "PRDescriptionProposal", "AtomicCommitGroup", "FileChangeAnalysis", "CommitType",
    "Verifier", "VerificationResult", "Patcher",
    "AIBisectEngine", "BisectResult", "BisectStep",
    # Agents
    "Orchestrator", "OrchestratorResult", "Persona", "SubagentDispatcher", "SubagentRole", "SubagentStatus",
    "AdversarialConsensusSwarm", "SwarmConsensusResult", "AdversarialAttack",
    "FullStackScaffolder", "ScaffoldResult", "GeneratedFile",
    # Tools
    "SecurityHealer", "SecurityScanReport", "VulnerabilityFinding", "VulnerabilityHealResult", "VulnerabilitySeverity", "VulnerabilityType",
    "IncidentHealResult", "IncidentReport", "IncidentTriageEngine", "LogType", "StackFrame",
    "DiagramGenerator", "DiagramType",
    "MCPClient", "MCPManager", "MCPServerConfig", "MCPTool", "MCPToolResult", "MCPResource", "MCPPrompt",
    "RepoGardener", "GardenReport", "GardenFinding",
    "CodebaseQAEngine", "QAResult",
    "GhostTerminalDaemon", "GhostHealPrompt",
    "SynapseCodeGraph", "SynapseSlice", "CodeNode",
]
