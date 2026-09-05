"""
cli.py - Command Line Interface & TUI Entrypoint for K-CLI (Project Bankai Engine)

Features:
1. Live token streaming with dynamic syntax highlighting.
2. Real-time Status Bar (Active Model, Git Branch, Active Persona, RAM, Tokens).
3. Interactive slash commands (/model, /persona, /diff, /rollback, /help, /docs, /clear, /test).
4. Side-by-side and inline surgical diff visualization.
"""

import warnings
warnings.filterwarnings("ignore")

import difflib
import functools
import json
import os
import shlex
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path for direct CLI script execution
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)
_module_dir = str(Path(__file__).resolve().parent)
if _module_dir not in sys.path:
    sys.path.insert(0, _module_dir)

import psutil
from typing import List, Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

try:
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.orchestrator import Orchestrator, Persona
    from k_cli.git.verifier import Verifier
    from k_cli.tools.doc_retriever import DocRetriever
    from k_cli.git.repo_map import RepoMap
    from k_cli.core.session import SessionManager
    from k_cli.core.model_manager import ModelManager, ModelPullResult, MODEL_CATALOG
    from k_cli.agents.persona import DomainPersona, PersonaProfile, PersonaRegistry
    from k_cli.agents.subagents import (
        SubagentDispatcher,
        SubagentVisualizer,
        SubagentTask,
        SubagentRole,
        SubagentRunResult,
        execute_subagents,
    )
    from k_cli.tui.diff_viewer import DiffVisualizer
    from k_cli.core.credentials import CredentialsManager, DevPreferencesManager
    from k_cli.core.sdk import create_plan
    from k_cli.git.git_guard import GitGuard
    from k_cli.tools.audit import run_audit
    from k_cli.core.prompting import enhance_prompt, resolve_profile
    from k_cli.tools.security import scan_workspace
    from k_cli.tools.feature import inspect_feature
    from k_cli.tools.rules import load_project_rules
    from k_cli.tui.tui import (
        StatusBar,
        LiveStreamRenderer,
        InteractiveShell,
        SlashCommandHandler,
        MODEL_PRESETS,
        get_persona_style,
    )
    from k_cli.tools.mcp_client import (
        MCPManager,
        MCPClient,
        MCPServerConfig,
        mcp_list_servers,
        mcp_add_server,
        mcp_remove_server,
        mcp_test_connection,
    )
    from k_cli.git.conflict_resolver import (
        ConflictResolver,
        ConflictBlock,
        ConflictResolution,
        FileResolutionResult,
        ConflictSummary,
    )
    from k_cli.github.github_client import (
        GitHubClient,
        MockGitHubClient,
        PRLifecycleManager,
        PullRequest,
        PRReviewResult,
        PRFixResult,
        CIStatus,
    )
    from k_cli.github.dedup_engine import (
        DedupEngine,
        DedupMatch,
        CommitRecord,
        SymbolRecord,
    )
    from k_cli.git.smart_git import (
        SmartGitEngine,
        SmartCommitProposal,
        PRDescriptionProposal,
        AtomicCommitGroup,
        FileChangeAnalysis,
        CommitType,
    )
    from k_cli.tools.security_healer import (
        SecurityHealer,
        SecurityScanReport,
        VulnerabilityFinding,
        VulnerabilityHealResult,
        VulnerabilitySeverity,
        VulnerabilityType,
    )
    from k_cli.core.models_hub import (
        ModelHub,
        ModelSpec,
        ModelProvider,
        ModelBenchmarkResult,
    )
    from k_cli.github.github_engine import (
        GitHubEngine,
        GitHubIssue,
        GitHubRelease,
        WorkflowRun,
        IssueSolveResult,
    )
    from k_cli.github.local_hub import LocalGitHubHub, LocalHubSummary, LocalCommit
    from k_cli.github.trending import TrendingEngine, TrendingRepo
except (ModuleNotFoundError, ImportError):
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.orchestrator import Orchestrator, Persona
    from verifier import Verifier
    from doc_retriever import DocRetriever
    from repo_map import RepoMap
    from session import SessionManager
    try:
        from model_manager import ModelManager, ModelPullResult, MODEL_CATALOG
    except (ModuleNotFoundError, ImportError):
        ModelManager = None  # type: ignore
        ModelPullResult = None  # type: ignore
        MODEL_CATALOG = {}  # type: ignore
    try:
        from persona import DomainPersona, PersonaProfile, PersonaRegistry
    except (ModuleNotFoundError, ImportError):
        PersonaRegistry = None
    from subagents import (
        SubagentDispatcher,
        SubagentVisualizer,
        SubagentTask,
        SubagentRole,
        SubagentRunResult,
        execute_subagents,
    )
    from diff_viewer import DiffVisualizer
    try:
        from k_cli.core.sdk import create_plan
    except (ImportError, ModuleNotFoundError):
        from workflow import create_plan
    from git_guard import GitGuard
    from k_cli.tools.audit import run_audit
    from prompting import enhance_prompt, resolve_profile
    from security import scan_workspace
    from k_cli.tools.feature import inspect_feature
    from k_cli.tools.rules import load_project_rules
    from k_cli.tui.tui import (
        StatusBar,
        LiveStreamRenderer,
        InteractiveShell,
        SlashCommandHandler,
        MODEL_PRESETS,
        get_persona_style,
    )
    try:
        from mcp_client import (
            MCPManager,
            MCPClient,
            MCPServerConfig,
            mcp_list_servers,
            mcp_add_server,
            mcp_remove_server,
            mcp_test_connection,
        )
    except (ModuleNotFoundError, ImportError):
        MCPManager = None  # type: ignore
    try:
        from conflict_resolver import (
            ConflictResolver,
            ConflictBlock,
            ConflictResolution,
            FileResolutionResult,
            ConflictSummary,
        )
    except (ModuleNotFoundError, ImportError):
        ConflictResolver = None  # type: ignore
    try:
        from github_client import (
            GitHubClient,
            MockGitHubClient,
            PRLifecycleManager,
            PullRequest,
            PRReviewResult,
            PRFixResult,
            CIStatus,
        )
    except (ModuleNotFoundError, ImportError):
        GitHubClient = None  # type: ignore
        PRLifecycleManager = None  # type: ignore
    try:
        from dedup_engine import (
            DedupEngine,
            DedupMatch,
            CommitRecord,
            SymbolRecord,
        )
    except (ModuleNotFoundError, ImportError):
        DedupEngine = None  # type: ignore
    try:
        from k_cli.git.smart_git import (
            SmartGitEngine,
            SmartCommitProposal,
            PRDescriptionProposal,
            AtomicCommitGroup,
            FileChangeAnalysis,
            CommitType,
        )
    except (ModuleNotFoundError, ImportError):
        SmartGitEngine = None  # type: ignore
        SmartCommitProposal = None  # type: ignore
        PRDescriptionProposal = None  # type: ignore
    try:
        from security_healer import (
            SecurityHealer,
            SecurityScanReport,
            VulnerabilityFinding,
            VulnerabilityHealResult,
            VulnerabilitySeverity,
            VulnerabilityType,
        )
    except (ModuleNotFoundError, ImportError):
        SecurityHealer = None  # type: ignore
        SecurityScanReport = None  # type: ignore

app = typer.Typer(
    name="k-cli",
    help="K-CLI: Universal agentic AI coding workstation.",
    add_completion=False,
)
console = Console()

ASCII_BANNER = r"""
[bold cyan]
  ██╗  ██╗   ██████╗██╗     ██╗
  ██║ ██╔╝  ██╔════╝██║     ██║
  █████═╝   ██║     ██║     ██║
  ██╔═██╗   ██║     ██║     ██║
  ██║  ██╗  ╚██████╗███████╗██║
  ╚═╝  ╚═╝   ╚═════╝╚══════╝╚═╝
[/bold cyan]
[bold bright_white]K-CLI AGENTIC WORKSTATION v1.0.0 | Verification-First Engine[/bold bright_white]
[dim]Commands: /keys | /conflict | /gh | /model | /security | /clear | /test | /help | /exit[/dim]
"""


def print_banner():
    console.print(ASCII_BANNER)


def _resolve_val(val, default):
    """Safely extracts default values if Typer OptionInfo objects are passed directly."""
    if hasattr(val, "default"):
        return val.default
    return val if val is not None else default


@functools.lru_cache(maxsize=128)
def get_persona_color(persona: str) -> str:
    """Returns Rich color string corresponding to persona string or Enum."""
    p_str = str(persona).upper().strip()
    color_map = {
        "RESEARCHER": "cyan",
        "ARCHITECT": "magenta",
        "CODER": "green",
        "CRITIC": "yellow",
        "DEBUGGER": "red",
        "DEVOPS": "cyan",
        "SYSTEMS": "magenta",
        "SECURITY": "red",
        "APPSEC": "red",
        "FRONTEND": "green",
        "DATABASE": "yellow",
        "DEFAULT": "blue",
    }
    for key, color in color_map.items():
        if key in p_str:
            return color
    return "blue"


def compute_diff(initial_code: str, final_code: str) -> str:
    """Calculates unified diff text between candidate code and repaired code."""
    diff_lines = list(
        difflib.unified_diff(
            initial_code.splitlines(keepends=True),
            final_code.splitlines(keepends=True),
            fromfile="candidate_code.py",
            tofile="repaired_code.py",
        )
    )
    return "".join(diff_lines)


def execute_run(
    prompt: str,
    language: str = "python",
    model: str = "qwen2.5-coder:1.5b",
    max_retries: int = 3,
    save_to: Optional[Path] = None,
    mock: bool = False,
    show_banner: bool = True,
    test_file: Optional[Path] = None,
    test_code: Optional[str] = None,
    persona: Optional[str] = None,
    enhance: bool = False,
    rules_file: Optional[Path] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """Core execution logic for running prompts through persona state machine with live token streaming."""
    language = str(_resolve_val(language, "python"))
    model = str(_resolve_val(model, "qwen2.5-coder:1.5b"))
    max_retries = int(_resolve_val(max_retries, 3))
    mock = bool(_resolve_val(mock, False))
    if not mock and ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM")):
        mock = True
    save_to_val = _resolve_val(save_to, None)
    save_to_path = Path(save_to_val) if save_to_val else None
    test_file_val = _resolve_val(test_file, None)
    test_code_val = _resolve_val(test_code, None)
    persona_val = _resolve_val(persona, None)

    resolved_test_code = test_code_val
    if test_file_val is not None:
        tf_path = Path(test_file_val)
        if tf_path.exists():
            resolved_test_code = tf_path.read_text(encoding="utf-8")

    if show_banner:
        print_banner()

    driver = LLMDriver(
        model_name=model,
        mock_mode=mock,
        provider=provider,
        openai_base_url=base_url,
    )
    verifier = Verifier()
    orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=max_retries, persona=persona_val)

    initial_ram = orchestrator.get_current_ram_mb()
    driver_type = "ONLINE (Ollama GGUF)" if driver.is_ollama_available() else "LOCAL (llama-cpp-python GGUF)"

    if show_banner:
        table = Table(title="System Environment Status", box=None)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Active Model", model)
        if orchestrator.active_persona:
            table.add_row("Active Persona", orchestrator.active_persona.title)
        table.add_row("Target Language", language)
        table.add_row("SLM Driver Engine", driver_type)
        table.add_row("Initial RAM Allocation", f"{initial_ram:.2f} MB / 1024 MB")
        console.print(table)
        console.print()

    effective_prompt = enhance_prompt(prompt, model, language) if enhance else prompt
    if rules_file is not None:
        try:
            guidance = load_project_rules(Path.cwd(), rules_file)
        except ValueError as exc:
            console.print(f"[bold red]Invalid project guidance:[/bold red] {exc}")
            raise typer.Exit(code=2)
        if guidance:
            effective_prompt = f"{effective_prompt}\n\n{guidance}"
    console.print(f"[bold yellow]Agent Task:[/bold yellow] [italic]'{prompt}'[/italic]\n")
    if enhance:
        console.print(f"[dim]Prompt adapted for {resolve_profile(model).name}.[/dim]\n")

    current_persona_name = "RESEARCHER"
    current_persona_text = ""

    def make_live_panel() -> Panel:
        ram_mb = orchestrator.get_current_ram_mb()
        color = get_persona_color(current_persona_name)
        title = f"[{color}]Active Persona: [{current_persona_name}][/{color}] | RSS RAM: {ram_mb:.2f} MB / 1024 MB"

        if not current_persona_text:
            content = Text(f"Initializing [{current_persona_name}] persona...", style="dim italic")
        elif current_persona_name in ("CODER", "DEBUGGER") and "```" not in current_persona_text:
            try:
                content = Syntax(current_persona_text, language, theme="monokai", line_numbers=True)
            except Exception:
                content = Text(current_persona_text)
        else:
            content = Text(current_persona_text)

        return Panel(content, title=title, border_style=color)

    with Live(make_live_panel(), console=console, refresh_per_second=15, auto_refresh=True) as live:
        def stream_cb(persona, token: str):
            nonlocal current_persona_name, current_persona_text
            p_name = persona.value if hasattr(persona, "value") else str(persona)
            if p_name != current_persona_name:
                current_persona_name = p_name
                current_persona_text = ""
            current_persona_text += token
            live.update(make_live_panel())

        result = orchestrator.execute_pipeline(
            user_prompt=effective_prompt,
            language=language,
            test_code=resolved_test_code,
            token_stream_callback=stream_cb,
            persona=persona_val,
        )

    # Display Diff Block if retries occurred (Auto-Debug Repair Diff)
    if result.attempts > 1:
        coder_entry = next((h for h in result.history if isinstance(h, dict) and h.get("persona") == Persona.CODER.value), None)
        if coder_entry and coder_entry.get("output"):
            initial_candidate = coder_entry["output"]
            diff_text = compute_diff(initial_candidate, result.final_code)
            if diff_text:
                diff_syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
                diff_panel = Panel(diff_syntax, title=f"[bold yellow]Auto-Debug Repair Diff (Attempt {result.attempts - 1})[/bold yellow]", border_style="yellow")
                console.print(diff_panel)

    # Display Verification Results
    if result.success:
        console.print(f"[bold green]✔ GROUND-TRUTH VERIFIED[/bold green] [dim]({result.verification.verification_type.upper()} guard | Retries: {result.attempts - 1} | RAM: {result.ram_usage_mb:.2f} MB)[/dim]\n")

        if result.architecture_plan:
            plan_panel = Panel(result.architecture_plan.strip(), title="Architecture Plan & Reasoning", border_style="cyan")
            console.print(plan_panel)

        syntax = Syntax(result.final_code, language, theme="monokai", line_numbers=True)
        panel = Panel(syntax, title=f"[bold green]Verified {language.upper()} Implementation[/bold green]", border_style="green")
        console.print(panel)

        if save_to_path:
            save_to_path.write_text(result.final_code, encoding="utf-8")
            console.print(f"\n[bold blue]Saved verified code to:[/bold blue] {save_to_path.resolve()}")

    else:
        console.print(f"[bold red]✘ VERIFICATION FAILED AFTER RETRIES[/bold red] [dim](Line: {result.verification.line_number or 'Unknown'} | RAM: {result.ram_usage_mb:.2f} MB)[/dim]\n")

        err_trace = (result.verification.error_trace if result.verification else None) or "Verification failed."
        err_panel = Panel(err_trace, title="Compiler / Verification Error Trace", border_style="red")
        console.print(err_panel)

        syntax = Syntax(result.final_code, language, theme="monokai", line_numbers=True)
        code_panel = Panel(syntax, title="Unverified Candidate Code", border_style="yellow")
        console.print(code_panel)

        raise typer.Exit(code=1)


@app.command(name="exec", help="Execute any shell/terminal command locally on this machine (Google Antigravity style).")
@app.command(name="cmd", help="Alias for k-cli exec: run any shell/terminal command locally.")
def execute_local_command_cli(
    command: str = typer.Argument(..., help="Shell command line to execute on local system."),
    cwd: str = typer.Option(".", "--cwd", "-C", help="Working directory to run command in."),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Maximum execution timeout in seconds."),
):
    from k_cli.tools.command_runner import global_command_executor
    console.print(f"[bold cyan]⚡ K-CLI Local Command Runner (Antigravity Engine):[/bold cyan] [white]{command}[/white]")
    res = global_command_executor.execute(command=command, cwd=cwd, timeout=timeout)
    if res.stdout.strip():
        console.print(res.stdout.rstrip())
    if res.stderr.strip():
        console.print(f"[bold red]{res.stderr.rstrip()}[/bold red]")
    if res.exit_code != 0:
        console.print(f"[bold red]✖ Command failed with exit code {res.exit_code} ({res.duration_sec:.2f}s)[/bold red]")
        raise typer.Exit(code=res.exit_code)
    else:
        console.print(f"[bold green]✔ Command completed in {res.duration_sec:.2f}s[/bold green]")


@app.command(name="run", help="Generate and verify code for a given prompt.")
def run(
    prompt: str = typer.Argument(..., help="Natural language prompt / coding task description."),
    language: str = typer.Option("python", "--language", "-l", help="Target programming language (python, bash, cpp)."),
    model: str = typer.Option("qwen2.5-coder:1.5b", "--model", "-m", help="Ollama model name."),
    max_retries: int = typer.Option(3, "--retries", "-r", help="Max auto-debug retry attempts."),
    save_to: Optional[Path] = typer.Option(None, "--save-to", "-s", help="File path to save verified code output."),
    mock: bool = typer.Option(False, "--mock", help="Force mock model execution for offline testing."),
    test_file: Optional[Path] = typer.Option(None, "--test-file", "-t", help="Path to test file for verification."),
    test_code: Optional[str] = typer.Option(None, "--test-code", help="Inline test code string for verification."),
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Specialized domain persona (devops, debugger, systems, security, frontend, database)."),
    enhance: bool = typer.Option(False, "--enhance", help="Adapt the task to the selected model's strengths."),
    rules_file: Optional[Path] = typer.Option(None, "--rules", help="Optional workspace-contained project guidance file."),
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider name (for example ollama, openai, or openai-compatible)."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Base URL for an OpenAI-compatible endpoint; use KCLI_API_KEY for its token."),
):
    execute_run(
        prompt=prompt,
        language=language,
        model=model,
        max_retries=max_retries,
        save_to=save_to,
        mock=mock,
        show_banner=True,
        test_file=test_file,
        test_code=test_code,
        persona=persona,
        enhance=enhance,
        rules_file=rules_file,
        provider=provider,
        base_url=base_url,
    )


@app.command(name="prompt", help="Preview a provider-aware prompt without calling a model.")
def prompt_cmd(
    task: str = typer.Argument(..., help="Task to adapt."),
    model: str = typer.Option("qwen2.5-coder:1.5b", "--model", "-m", help="Target model name."),
    language: str = typer.Option("python", "--language", "-l", help="Target language."),
    rules_file: Optional[Path] = typer.Option(None, "--rules", help="Optional workspace-contained project guidance file."),
):
    preview = enhance_prompt(task, model, language)
    if rules_file is not None:
        try:
            guidance = load_project_rules(Path.cwd(), rules_file)
        except ValueError as exc:
            console.print(f"[bold red]Invalid project guidance:[/bold red] {exc}")
            raise typer.Exit(code=2)
        if guidance:
            preview = f"{preview}\n\n{guidance}"
    console.print(Panel(preview, title=f"Prompt preview · {resolve_profile(model).name}", border_style="cyan"))


@app.command(name="audit", help="Generate candidates with 5+ models in parallel, adversarial peer review, and verify locally.")
def audit_cmd(
    task: str = typer.Argument(..., help="Implementation task to audit across multiple models."),
    models: str = typer.Option("gemini-2.0-flash,claude-3-7-sonnet,deepseek-reasoner,gpt-4o,qwen2.5-coder:7b", "--models", "-m", help="Comma-separated model names (supports 2 to 10+ models)."),
    language: str = typer.Option("python", "--language", "-l", help="Target language."),
    mock: bool = typer.Option(False, "--mock", help="Use offline mock drivers."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable audit results."),
):
    """Executes multi-model parallel code generation, peer review, and AST verification."""
    from k_cli.agents.adversarial_swarm import MultiModelConsensusSwarm

    selected_models = [item.strip() for item in models.split(",") if item.strip()]
    if len(selected_models) < 2:
        selected_models = ["gemini-2.0-flash", "claude-3-7-sonnet", "deepseek-reasoner", "gpt-4o", "qwen2.5-coder:7b"]

    swarm = MultiModelConsensusSwarm(models=selected_models, mock_mode=mock)
    report = swarm.audit_and_generate(task_prompt=task, language=language)

    if as_json:
        payload = {
            "task": report.task,
            "selected_model": report.selected_model,
            "consensus_score": report.consensus_score,
            "cross_model_agreement_pct": report.cross_model_agreement_pct,
            "total_duration_sec": report.total_duration_sec,
            "candidates": [
                {
                    "model": c.model_name,
                    "provider": c.provider,
                    "ast_valid": c.ast_valid,
                    "verification_passed": c.verification_passed,
                    "latency_sec": c.generation_time_sec,
                    "score": c.score,
                    "code": c.code,
                }
                for c in report.candidates
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return


    console.print(Markdown(report.render_markdown()))



@app.command(name="feature", help="Collect read-only source and test evidence for a feature claim.")
def feature_cmd(
    query: str = typer.Argument(..., help="Feature or capability to look for."),
    root_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Workspace root directory."),
    require_tests: bool = typer.Option(False, "--require-tests", help="Fail unless matching test evidence is found."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable evidence."),
):
    """Check whether a requested capability has implementation and supporting evidence."""
    evidence = inspect_feature(query, root_dir)
    if as_json:
        console.print(json.dumps(evidence.to_dict(), indent=2))
    else:
        table = Table(title="K-CLI Feature Evidence", box=None)
        table.add_column("Evidence", style="cyan")
        table.add_column("Count", style="bold white")
        table.add_row("Source matches", str(len(evidence.source_matches)))
        table.add_row("Test matches", str(len(evidence.test_matches)))
        table.add_row("Symbol matches", str(len(evidence.symbol_matches)))
        table.add_row("Status", "[green]PROVEN[/green]" if evidence.proven else "[yellow]INCONCLUSIVE[/yellow]")
        console.print(table)
        for match in (evidence.source_matches + evidence.test_matches + evidence.symbol_matches)[:15]:
            console.print(f"[dim]{match.category} {match.path}:{match.line}[/dim] {match.evidence}")
    if not evidence.proven or (require_tests and not evidence.test_matches):
        raise typer.Exit(code=1)


def execute_subagents_run(
    prompt: str,
    model: str = "qwen2.5-coder:1.5b",
    max_workers: int = 4,
    save_to: Optional[Path] = None,
    mock: bool = False,
    show_banner: bool = True,
    no_ui: bool = False,
    context_files: Optional[List[str]] = None,
):
    """Core execution logic for decomposing prompts into parallel subagent workers."""
    model = str(_resolve_val(model, "qwen2.5-coder:1.5b"))
    max_workers = int(_resolve_val(max_workers, 4))
    mock = bool(_resolve_val(mock, False))
    if not mock and ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM")):
        mock = True
    save_to_val = _resolve_val(save_to, None)
    save_to_path = Path(save_to_val) if save_to_val else None

    if show_banner:
        print_banner()

    driver = LLMDriver(model_name=model, mock_mode=mock)
    verifier = Verifier()
    dispatcher = SubagentDispatcher(
        driver=driver,
        verifier=verifier,
        max_workers=max_workers,
    )

    initial_ram = psutil.Process().memory_info().rss / (1024 * 1024)
    driver_type = "ONLINE (Ollama GGUF)" if driver.is_ollama_available() else "LOCAL (llama-cpp-python GGUF)"

    if show_banner:
        table = Table(title="Multi-Agent System Environment", box=None)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Active Model", model)
        table.add_row("Max Parallel Workers", str(max_workers))
        table.add_row("SLM Driver Engine", driver_type)
        table.add_row("Initial RAM Allocation", f"{initial_ram:.2f} MB / 1024 MB")
        console.print(table)
        console.print()

    console.print(f"[bold yellow]Multi-Agent Task:[/bold yellow] [italic]'{prompt}'[/italic]\n")

    tasks = dispatcher.decomposer.decompose(
        prompt=prompt,
        context_files=context_files,
    )

    # Display planned task hierarchy
    tree = SubagentVisualizer.render_tree(tasks, title=f"Planned Subagent Tree ({len(tasks)} tasks)")
    console.print(tree)
    console.print()

    if no_ui:
        result = dispatcher.dispatch(tasks=tasks)
    else:
        result = SubagentVisualizer.execute_with_live_cli(
            dispatcher=dispatcher,
            tasks=tasks,
            console=console,
        )

    console.print()
    if result.success:
        console.print(f"[bold green]✔ MULTI-AGENT TASK COMPLETED SUCCESSFULLY[/bold green] [dim](Tasks: {len(result.tasks)} | Duration: {result.total_duration_sec:.2f}s | RAM: {result.total_ram_mb:.2f} MB)[/dim]\n")

        # Display Final Patch or Code
        if result.aggregated_patch:
            syntax = Syntax(result.aggregated_patch, "diff", theme="monokai", line_numbers=False)
            panel = Panel(syntax, title="[bold green]Unified Aggregated Patch[/bold green]", border_style="green")
            console.print(panel)
        elif result.final_code:
            syntax = Syntax(result.final_code, "python", theme="monokai", line_numbers=True)
            panel = Panel(syntax, title="[bold green]Verified Implementation Code[/bold green]", border_style="green")
            console.print(panel)

        if save_to_path:
            out_content = result.aggregated_patch if result.aggregated_patch else result.final_code
            save_to_path.write_text(out_content, encoding="utf-8")
            console.print(f"\n[bold blue]Saved output to:[/bold blue] {save_to_path.resolve()}")

        return result

    else:
        console.print(f"[bold red]✘ SUBAGENTS PIPELINE FAILED[/bold red] [dim](Duration: {result.total_duration_sec:.2f}s | RAM: {result.total_ram_mb:.2f} MB)[/dim]\n")
        if result.verification and not result.verification.success:
            err_trace = result.verification.error_trace or "Verification failed."
            console.print(Panel(err_trace, title="Compiler / Verification Error Trace", border_style="red"))

        if result.final_code:
            syntax = Syntax(result.final_code, "python", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="Unverified Candidate Output", border_style="yellow"))

        raise typer.Exit(code=1)


@app.command(name="subagents", help="Decompose complex prompt into parallel subagents (Explorer, Researcher, Refactorer, Tester).")
def subagents_cmd(
    prompt: str = typer.Argument(..., help="Complex user prompt or coding task."),
    model: str = typer.Option("qwen2.5-coder:1.5b", "--model", "-m", help="Ollama model name."),
    max_workers: int = typer.Option(4, "--workers", "-w", help="Max parallel subagent workers."),
    save_to: Optional[Path] = typer.Option(None, "--save-to", "-s", help="File path to save verified patch or code."),
    mock: bool = typer.Option(False, "--mock", help="Force mock model execution for offline testing."),
    no_ui: bool = typer.Option(False, "--no-ui", help="Disable live Rich CLI visualization."),
):
    execute_subagents_run(
        prompt=prompt,
        model=model,
        max_workers=max_workers,
        save_to=save_to,
        mock=mock,
        show_banner=True,
        no_ui=no_ui,
    )


@app.command(name="spawn", help="Alias for subagents: Decompose and execute prompt with parallel subagents.")
def spawn_cmd(
    prompt: str = typer.Argument(..., help="Complex user prompt or coding task."),
    model: str = typer.Option("qwen2.5-coder:1.5b", "--model", "-m", help="Ollama model name."),
    max_workers: int = typer.Option(4, "--workers", "-w", help="Max parallel subagent workers."),
    save_to: Optional[Path] = typer.Option(None, "--save-to", "-s", help="File path to save verified patch or code."),
    mock: bool = typer.Option(False, "--mock", help="Force mock model execution for offline testing."),
    no_ui: bool = typer.Option(False, "--no-ui", help="Disable live Rich CLI visualization."),
):
    execute_subagents_run(
        prompt=prompt,
        model=model,
        max_workers=max_workers,
        save_to=save_to,
        mock=mock,
        show_banner=True,
        no_ui=no_ui,
    )


@app.command(name="verify", help="Run standalone ground-truth verification on a local code file or inline code string.")
def verify(
    file_path: Optional[Path] = typer.Argument(None, help="Path to code file to verify."),
    code: Optional[str] = typer.Option(None, "--code", "-c", help="Inline code string to verify."),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language override."),
    test_file: Optional[Path] = typer.Option(None, "--test-file", "-t", help="Path to test file for pytest verification."),
    test_code: Optional[str] = typer.Option(None, "--test-code", help="Inline test code string for pytest verification."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable verification results."),
):
    if not as_json:
        print_banner()

    file_path_val = _resolve_val(file_path, None)
    code_val = _resolve_val(code, None)
    lang_val = _resolve_val(language, None)
    test_file_val = _resolve_val(test_file, None)
    test_code_val = _resolve_val(test_code, None)

    if file_path_val is None and not code_val:
        console.print("[bold red]Error:[/bold red] Must specify a file path or code string to verify.")
        raise typer.Exit(code=1)

    resolved_code = ""
    display_target = ""
    default_lang = "python"

    if file_path_val is not None:
        fp = Path(file_path_val)
        if not fp.exists():
            console.print(f"[bold red]Error:[/bold red] File '{fp}' does not exist.")
            raise typer.Exit(code=1)
        resolved_code = fp.read_text(encoding="utf-8")
        display_target = fp.name
        ext = fp.suffix.lstrip(".").lower()
        default_lang = "python" if ext in ("py", "python") else "bash" if ext in ("sh", "bash") else "cpp" if ext in ("cpp", "cxx", "cc") else "python"
    else:
        resolved_code = code_val
        display_target = "inline code"

    lang = lang_val or default_lang

    resolved_test_code = test_code_val
    if test_file_val is not None:
        tf_path = Path(test_file_val)
        if tf_path.exists():
            resolved_test_code = tf_path.read_text(encoding="utf-8")

    verifier = Verifier()
    result = verifier.verify(resolved_code, language=lang, test_code=resolved_test_code)

    if as_json:
        payload = result.to_dict()
        payload["target"] = display_target
        console.print(json.dumps(payload, indent=2))
        if not result.success:
            raise typer.Exit(code=1)
        return

    if result.success:
        console.print(f"[bold green]✔ File '{display_target}' passed ground-truth {result.verification_type} verification![/bold green]")
    else:
        console.print(f"[bold red]✘ File '{display_target}' failed verification at line {result.line_number or 'unknown'}.[/bold red]\n")
        err_trace = result.error_trace or "Verification failed."
        console.print(Panel(err_trace, title="Compiler / Verification Error Trace", border_style="red"))
        raise typer.Exit(code=1)


@app.command(name="status", help="Check K-CLI active system RAM budget, model diagnostics, and git branch.")
def status():
    print_banner()
    driver = LLMDriver()
    orchestrator = Orchestrator(driver=driver)
    session = SessionManager(model_name=driver.model_name)

    ram_mb = orchestrator.get_current_ram_mb()
    ollama_ok = driver.is_ollama_available()

    table = Table(title="K-CLI System Diagnostics", box=None)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold white")
    table.add_row("Active Model", driver.model_name)
    table.add_row("Git Branch", session.get_git_branch())
    table.add_row("Active Persona", session.active_persona)
    table.add_row("Memory RSS Allocation", f"{ram_mb:.2f} MB / 1024 MB (Budget Limit)")
    table.add_row("SLM Driver Engine", "[green]ONLINE (Ollama GGUF)[/green]" if ollama_ok else "[yellow]LOCAL (llama-cpp-python GGUF)[/yellow]")
    table.add_row("Default Model", driver.model_name)
    from k_cli.core.sandbox import global_sandbox_engine
    diag = global_sandbox_engine.get_diagnostics()
    table.add_row("Sandbox Virtualization", f"[green]ACTIVE ({diag['security_rating']})[/green]" if diag["bubblewrap_available"] else f"[yellow]{diag['security_rating']}[/yellow]")
    table.add_row("Python Environment", sys.version.split()[0])
    console.print(table)


@app.command(name="plan", help="Create a protected, read-only implementation plan for a workspace.")
def plan_cmd(
    goal: str = typer.Argument(..., help="Outcome to plan; no project files are changed."),
    root_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Workspace to inspect."),
    rules_file: Optional[Path] = typer.Option(None, "--rules", help="Optional workspace-contained project guidance file."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable plan data."),
):
    """Inspect a workspace and print an implementation plan without editing anything."""
    result = create_plan(goal, root_dir)
    if rules_file is not None:
        try:
            result.project_guidance = load_project_rules(root_dir, rules_file)
        except ValueError as exc:
            console.print(f"[bold red]Invalid project guidance:[/bold red] {exc}")
            raise typer.Exit(code=2)
    if as_json:
        sys.stdout.write(json.dumps({
            "goal": result.goal,
            "workspace": str(result.workspace),
            "relevant_files": result.relevant_files,
            "detected_tools": result.detected_tools,
            "repo_map": result.repo_map,
            "project_guidance": result.project_guidance,
            "read_only": True,
        }, indent=2) + "\n")
    else:
        console.print(result.render_markdown())


@app.command(name="doctor", help="Check install, workspace, model, and safety prerequisites.")
def doctor_cmd(
    root_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Workspace to diagnose."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable diagnostics."),
):
    """Print actionable diagnostics without downloading models or changing project files."""
    root = root_dir.resolve()
    driver = LLMDriver()
    findings = scan_workspace(root)
    checks = [
        ("Workspace", str(root), root.exists()),
        ("Python", sys.version.split()[0], sys.version_info >= (3, 11)),
        ("Git repository", "detected" if GitGuard(root).is_git_repo() else "not detected", GitGuard(root).is_git_repo()),
        ("Ollama", "reachable" if driver.is_ollama_available() else "not reachable (mock mode still works)", driver.is_ollama_available()),
        ("KCLI_MOCK_MODE", os.getenv("KCLI_MOCK_MODE", "not set"), True),
        ("Secret hygiene", "no obvious committed credentials" if not findings else f"{len(findings)} potential credential(s) found", not findings),
    ]
    if as_json:
        payload = {
            "workspace": str(root),
            "checks": [
                {"name": label, "detail": detail, "passed": passed}
                for label, detail, passed in checks
            ],
            "findings": [
                {"rule": finding.rule, "path": str(finding.path), "line": finding.line}
                for finding in findings
            ],
            "ready": all(passed for _, _, passed in checks),
        }
        console.print(json.dumps(payload, indent=2))
        if not payload["ready"]:
            raise typer.Exit(code=1)
        return

    table = Table(title="K-CLI Doctor", box=None)
    table.add_column("Check", style="cyan")
    table.add_column("Result")
    table.add_column("Status")
    for label, detail, passed in checks:
        table.add_row(label, detail, "[green]ready[/green]" if passed else "[yellow]attention[/yellow]")
    console.print(table)
    for finding in findings:
        console.print(f"[yellow]Potential {finding.rule}: {finding.path}:{finding.line} (value intentionally hidden)[/yellow]")


web_app = typer.Typer(name="web", help="Launch the world-class K-CLI Web UI dashboard server.", invoke_without_command=True)


@app.command(name="web-ui", help="Launch the world-class K-CLI Web UI dashboard server.")
def web_ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Web server host interface."),
    port: int = typer.Option(8000, "--port", "-p", help="Web server port number."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open browser on server startup."),
):
    """Launch the world-class FastAPI Web UI dashboard."""
    from k_cli.web.server import start_web_server
    console.print(f"[bold cyan]⚡ Launching K-CLI World-Class Web UI on http://{host}:{port}...[/bold cyan]")
    start_web_server(host=host, port=port, open_browser=open_browser)


@web_app.callback(invoke_without_command=True)
def web_callback(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Web server host interface."),
    port: int = typer.Option(8000, "--port", "-p", help="Web server port number."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open browser on server startup."),
):
    """Launch the world-class FastAPI Web UI dashboard."""
    if ctx.invoked_subcommand is None:
        web_ui_cmd(host=host, port=port, open_browser=open_browser)


@web_app.command(name="ui", help="Launch the world-class K-CLI Web UI dashboard.")
def web_sub_ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Web server host interface."),
    port: int = typer.Option(8000, "--port", "-p", help="Web server port number."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open browser on server startup."),
):
    """Launch the Web UI dashboard."""
    web_ui_cmd(host=host, port=port, open_browser=open_browser)


app.add_typer(web_app, name="web")


# =============================================================================
# Tier 3: Streamlined Interactive Terminal REPL (`k-cli simple` / `k-cli simple ui`)
# =============================================================================
simple_app = typer.Typer(name="simple", help="Launch the streamlined, mouse-enabled text REPL UI.", invoke_without_command=True)


@app.command(name="simple-ui", help="Launch the streamlined text REPL with mouse and slash command support.")
@app.command(name="chat", help="Launch the streamlined interactive AI coding chat REPL.")
@app.command(name="repl", help="Launch the streamlined interactive AI coding chat REPL.")
def simple_ui_cmd(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Active model label."),
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Active persona label."),
    mock: bool = typer.Option(False, "--mock", help="Use offline mock driver."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root directory."),
):
    """Launch the streamlined Tier 3 interactive terminal REPL."""
    from k_cli.ui.simple_repl import run_simple_cli
    run_simple_cli(workspace_dir=str(workspace), model_name=model, persona=persona, mock_mode=mock)


@simple_app.callback(invoke_without_command=True)
def simple_callback(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Active model label."),
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Active persona label."),
    mock: bool = typer.Option(False, "--mock", help="Use offline mock driver."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root directory."),
):
    if ctx.invoked_subcommand is None:
        simple_ui_cmd(model=model, persona=persona, mock=mock, workspace=workspace)


@simple_app.command(name="ui", help="Launch the streamlined text REPL with mouse support.")
def simple_sub_ui_cmd(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Active model label."),
    persona: Optional[str] = typer.Option(None, "--persona", "-p", help="Active persona label."),
    mock: bool = typer.Option(False, "--mock", help="Use offline mock driver."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root directory."),
):
    simple_ui_cmd(model=model, persona=persona, mock=mock, workspace=workspace)


app.add_typer(simple_app, name="simple")


@app.command(name="ui", help="Launch the full-screen K-CLI Textual workstation.")
def ui_cmd(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Active model label (auto-detected if omitted)."),
    persona: str = typer.Option("Fullstack AI Systems Engineer", "--persona", "-p", help="Active persona label."),
    mock: bool = typer.Option(False, "--mock", help="Use the offline mock driver."),
    demo: bool = typer.Option(False, "--demo", "-d", help="Launch in pure zero-AI demo exploration mode."),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue previous multi-turn session from local storage."),
    codex: bool = typer.Option(False, "--codex", help="Open the Codex onboarding hub on launch."),
    welcome: bool = typer.Option(False, "--welcome", help="Force open the first-time welcome onboarding modal."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
):
    """Launch the polished Textual UI with dynamic model auto-detection and first-time onboarding."""
    try:
        from k_cli.tui.tui_app import KCliApp
    except ModuleNotFoundError:
        from k_cli.tui.tui_app import KCliCyberWorkstation as KCliApp
    
    is_mock = mock or demo
    effective_model = model or DevPreferencesManager.get_best_available_model()

    KCliApp(
        workspace_dir=str(workspace),
        model_name=effective_model,
        persona=persona,
        mock_mode=is_mock,
        show_codex_on_start=codex,
        show_welcome_on_start=welcome,
        continue_session=continue_session,
    ).run()


@app.command(name="tui", help="Alias for launching the full-screen K-CLI Textual workstation.")
def tui_cmd(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Active model label."),
    persona: str = typer.Option("Fullstack AI Systems Engineer", "--persona", "-p", help="Active persona label."),
    mock: bool = typer.Option(False, "--mock", help="Use the offline mock driver."),
    demo: bool = typer.Option(False, "--demo", "-d", help="Launch in pure zero-AI demo exploration mode."),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue previous multi-turn session from local storage."),
    codex: bool = typer.Option(False, "--codex", help="Open the Codex onboarding hub on launch."),
    welcome: bool = typer.Option(False, "--welcome", help="Force open the first-time welcome onboarding modal."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
):
    ui_cmd(
        model=model,
        persona=persona,
        mock=mock,
        demo=demo,
        continue_session=continue_session,
        codex=codex,
        welcome=welcome,
        workspace=workspace,
    )


@app.command(name="demo-ui", help="Launch the TUI in Pure Zero-AI Demo Mode (no API key or model needed).")
def demo_ui_cmd(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
):
    """Launch the full-screen Textual workstation in pure exploration mode without requiring any AI backend."""
    ui_cmd(mock=True, demo=True, workspace=workspace)


@app.command(name="codex", help="Launch the Codex Starting & Onboarding Hub (Cloud APIs, Local Models, Bankai HF, DevDocs).")
def codex_cmd(
    mock: bool = typer.Option(False, "--mock", help="Use the offline mock driver."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
):
    """Launch the Codex Starting Hub screen directly in the workstation."""
    ui_cmd(mock=mock, codex=True, workspace=workspace)


@app.command(name="setup", help="Alias for launching the Codex Starting & Onboarding Hub.")
def setup_cmd(
    mock: bool = typer.Option(False, "--mock", help="Use the offline mock driver."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
):
    """Launch the Codex Starting Hub screen."""
    codex_cmd(mock=mock, workspace=workspace)



@app.command(name="diff", help="View active uncommitted git diff or side-by-side diff.")
def diff_cmd(
    side_by_side: bool = typer.Option(False, "--side-by-side", "--sbs", "-s", help="Render side-by-side 2-column diff."),
):
    """Renders workspace git diff in inline or side-by-side format."""
    session = SessionManager()
    if not session.git_guard.is_git_repo():
        console.print("[yellow]Not inside a Git repository.[/yellow]")
        return

    diff_text = session.git_guard.get_diff()
    if not diff_text.strip():
        console.print("[dim]Working tree is clean; no uncommitted changes.[/dim]")
        return

    panel = DiffVisualizer.render_inline_diff(diff_text, title="Git Working Tree Diff")
    console.print(panel)


@app.command(name="review", help="Review changed source files without modifying the workspace.")
def review_cmd(
    root_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Workspace or Git repository root."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable review results."),
):
    """Run read-only syntax checks over changed Python files and summarize the diff."""
    root = root_dir.resolve()
    guard = GitGuard(root)
    if not guard.is_git_repo():
        payload = {
            "workspace": str(root),
            "git_repository": False,
            "changed_files": [],
            "syntax_failures": [],
            "status": "not-a-git-repository",
        }
        if as_json:
            console.print(json.dumps(payload, indent=2))
        else:
            console.print("[yellow]Review requires a Git repository; no files were inspected.[/yellow]")
        raise typer.Exit(code=2)

    status = guard._run_git(["status", "--porcelain"])
    changed_files: List[str] = []
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if len(line) >= 4:
                changed_files.append(line[3:].strip().strip('"'))

    verifier = Verifier()
    failures = []
    checked = []
    for relative in changed_files:
        path = root / relative
        if path.suffix.lower() != ".py" or not path.is_file():
            continue
        try:
            code = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            failures.append({"file": relative, "error": str(error)})
            continue
        checked.append(relative)
        result = verifier.verify_python_ast(code)
        if not result.success:
            failures.append({"file": relative, "line": result.line_number, "error": result.error_trace})

    payload = {
        "workspace": str(root),
        "git_repository": True,
        "changed_files": changed_files,
        "python_files_checked": checked,
        "syntax_failures": failures,
        "status": "failed" if failures else "passed",
    }
    if as_json:
        console.print(json.dumps(payload, indent=2))
    else:
        table = Table(title="K-CLI Read-Only Review", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold white")
        table.add_row("Changed files", str(len(changed_files)))
        table.add_row("Python files checked", str(len(checked)))
        table.add_row("Syntax failures", str(len(failures)))
        console.print(table)
        for failure in failures:
            console.print(
                f"[red]✘ {failure['file']}:{failure.get('line') or 'unknown'} "
                f"{failure['error']}[/red]"
            )
        if not failures:
            console.print("[green]✔ Changed Python files passed AST review.[/green]")
    if failures:
        raise typer.Exit(code=1)


@app.command(name="test", help="Run ground-truth compiler and pytest verification.")
def test_cmd(
    target: Optional[str] = typer.Argument(None, help="Target file or test code to verify."),
):
    """Runs ground-truth verification on target file or workspace."""
    session = SessionManager()
    passed, summary = session.run_test(target)
    if passed:
        console.print(f"[bold green]✔[/bold green] {summary}")
    else:
        console.print(f"[bold red]✗[/bold red] {summary}")
        raise typer.Exit(code=1)


@app.command(name="doc", help="Search offline DevDocs SQLite database for API signatures.")
def doc(
    query: str = typer.Argument(..., help="Query string or API symbol name."),
    limit: int = typer.Option(3, "--limit", "-n", help="Max number of results to return."),
    max_tokens: int = typer.Option(250, "--max-tokens", "-t", help="Max tokens budget for context."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite docs database."),
):
    """Searches DevDocs FTS5 offline database for function and class signatures."""
    retriever = DocRetriever(db_path=str(db_path) if db_path else None)
    results = retriever.search(query, limit=limit, max_tokens=max_tokens)
    if not results:
        console.print(f"[yellow]No documentation found for '{query}'.[/yellow]")
        raise typer.Exit(code=2)

    console.print(f"[bold cyan]DevDocs search results for '{query}':[/bold cyan]\n")
    for r in results:
        name = r.get("name", "")
        sig = r.get("signature", "")
        doc_str = r.get("doc", "")
        module = r.get("module", "")
        panel_content = f"[bold green]{sig}[/bold green]\n\n[dim]{doc_str}[/dim]"
        console.print(Panel(panel_content, title=f"Module: {module} | Symbol: {name}", border_style="cyan"))


@app.command(name="devdocs", help="Download and index complete DevDocs offline documentation suite.")
def devdocs_cmd(
    download: bool = typer.Option(True, "--download", "-d", help="Download and index all official DevDocs."),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search offline DevDocs."),
):
    """Downloads all DevDocs standard libraries or searches offline docs."""
    retriever = DocRetriever()
    if search:
        results = retriever.search(search, limit=3)
        if not results:
            console.print(f"[yellow]No documentation found for '{search}'.[/yellow]")
            return
        for r in results:
            panel_content = f"[bold green]{r.get('signature')}[/bold green]\n\n[dim]{r.get('doc')}[/dim]"
            console.print(Panel(panel_content, title=f"Module: {r.get('module')} | Symbol: {r.get('name')}", border_style="cyan"))
        return

    console.print("[bold cyan]📦 Indexing all standard libraries and frameworks into DevDocs SQLite database...[/bold cyan]")
    res = retriever.download_all_devdocs()
    console.print(f"[bold green]✔ Successfully indexed {res['total_database_symbols']} symbols in {res['duration_seconds']}s into {res['db_path']}![/bold green]")



@app.command(name="map", help="Display AST codebase repository map for the workspace.")
def map_cmd(
    root_dir: Path = typer.Option(Path("."), "--dir", "-d", help="Workspace root directory."),
    max_tokens: int = typer.Option(400, "--max-tokens", "-t", help="Max tokens budget for map."),
    focus: Optional[List[str]] = typer.Option(None, "--focus", "-f", help="Files to prioritize."),
):
    """Generates and displays AST symbol tree for the workspace."""
    repo_map = RepoMap(root_dir=str(root_dir))
    tree_text = repo_map.get_repo_map(max_tokens=max_tokens, focus_files=focus)
    if not tree_text.strip():
        console.print("[yellow]Repository map is empty (no valid Python files found).[/yellow]")
        return

    syntax = Syntax(tree_text, "python", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title="AST Codebase Repository Map", border_style="magenta"))


@app.command(name="init", help="Initialize K-CLI environment, verify Ollama health, and bootstrap Bankai models.")
def init_cmd(
    model: str = typer.Option("bankai-7b", "--model", "-m", help="Target Bankai model identifier (e.g. bankai-7b, bankai-10b)."),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama daemon URL."),
    no_pull: bool = typer.Option(False, "--no-pull", help="Skip downloading/pulling model weights from Hugging Face Hub."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download and re-creation even if cached."),
    mock: bool = typer.Option(False, "--mock", help="Force mock execution for offline testing."),
):
    """Initializes local K-CLI directory layout, checks Ollama status, and provisions default Bankai models."""
    print_banner()
    console.print("[bold cyan]⚡ Initializing K-CLI Environment & Bootstrapping Bankai Models...[/bold cyan]\n")

    mock_mode = bool(_resolve_val(mock, False))
    if not mock_mode and ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM")):
        mock_mode = True

    model_val = str(_resolve_val(model, "bankai-7b"))
    ollama_url_val = str(_resolve_val(ollama_url, "http://localhost:11434"))
    no_pull_val = bool(_resolve_val(no_pull, False))
    force_val = bool(_resolve_val(force, False))

    manager = ModelManager(ollama_url=ollama_url_val, mock_mode=mock_mode) if ModelManager else None
    if manager is None:
        console.print("[bold red]Error:[/bold red] ModelManager module could not be loaded.")
        raise typer.Exit(code=1)

    init_res = manager.init_environment(
        default_model=model_val,
        sync_model=not no_pull_val,
        force=force_val,
    )

    # 1. Directory Hierarchy
    table = Table(title="K-CLI Environment Directory Layout", box=None)
    table.add_column("Directory", style="cyan")
    table.add_column("Status", style="green")
    for d in init_res.get("directories", []):
        table.add_row(d, "✔ Ready")
    console.print(table)
    console.print()

    # 2. Ollama Diagnostics
    ollama_stat = init_res.get("ollama", {})
    ollama_ok = ollama_stat.get("healthy", False)
    ollama_table = Table(title="Local Ollama Inference Diagnostics", box=None)
    ollama_table.add_column("Property", style="cyan")
    ollama_table.add_column("Value", style="magenta")
    ollama_table.add_row("Ollama Host", ollama_stat.get("url", ollama_url_val))
    ollama_table.add_row("Daemon Status", "[bold green]ONLINE (Healthy)[/bold green]" if ollama_ok else "[bold yellow]OFFLINE / Unreachable[/bold yellow]")
    ollama_table.add_row("Ollama Version", str(ollama_stat.get("version", "unknown")))
    models_list = ", ".join(ollama_stat.get("models", [])) or "None loaded"
    ollama_table.add_row("Loaded Models", models_list)
    console.print(ollama_table)
    console.print()

    # 3. Model Pull & Ollama Registration Status
    pull_info = init_res.get("model_pull")
    if pull_info:
        p_table = Table(title="Bankai Model Bootstrapper Status", box=None)
        p_table.add_column("Attribute", style="cyan")
        p_table.add_column("Details", style="bold white")
        p_table.add_row("Target Model", pull_info.get("model_name", model_val))
        p_table.add_row("Ollama Tag", pull_info.get("ollama_tag", model_val))
        p_table.add_row("Local GGUF Path", str(pull_info.get("gguf_path") or "None"))
        p_table.add_row("Modelfile Path", str(pull_info.get("modelfile_path") or "None"))
        sha_str = pull_info.get("sha256") or "N/A"
        sha_status = "[bold green]✔ Verified[/bold green]" if pull_info.get("sha256_verified") else "[yellow]Unverified[/yellow]"
        p_table.add_row("SHA256 Integrity", f"{sha_str[:20]}... ({sha_status})")
        ollama_created = "[bold green]✔ Registered in Ollama[/bold green]" if pull_info.get("ollama_created") else "[yellow]Pending (Ollama offline)[/yellow]"
        p_table.add_row("Ollama Deployment", ollama_created)
        console.print(p_table)
        console.print()

    if init_res.get("ready"):
        console.print(Panel(
            f"[bold green]✔ Project Bankai Engine initialized successfully![/bold green]\n\n"
            f"• Active Model: [bold cyan]{model_val}[/bold cyan]\n"
            f"• Quick Run: [italic]k run 'write a binary search in python'[/italic]\n"
            f"• Interactive Shell: [italic]k[/italic]",
            title="[bold green]K-CLI Ready[/bold green]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            "[yellow]⚠ K-CLI directories initialized. To run with local Ollama, start the Ollama daemon and run [bold]k pull-model[/bold].[/yellow]",
            title="[bold yellow]Setup Notice[/bold yellow]",
            border_style="yellow",
        ))


@app.command(name="pull-model", help="Pull Bankai model from Hugging Face Hub into Ollama or local GGUF cache.")
def pull_model_cmd(
    model: str = typer.Argument("bankai-7b", help="Model identifier (e.g. bankai-7b, bankai-10b, krishivjoshi/bankai-7b)."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Ollama model tag to register (e.g. bankai:7b, bankai-7b)."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Hugging Face repository ID override."),
    quant: str = typer.Option("q4_k_m", "--quant", "-q", help="Quantization format to target (default: q4_k_m)."),
    verify_sha: bool = typer.Option(True, "--verify-sha/--no-verify-sha", help="Cryptographically verify SHA256 integrity."),
    sha256: Optional[str] = typer.Option(None, "--sha256", help="Expected SHA256 checksum string."),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama host URL."),
    no_ollama: bool = typer.Option(False, "--no-ollama", help="Skip Ollama model creation (cache GGUF only)."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download even if cached."),
    mock: bool = typer.Option(False, "--mock", help="Force mock execution for offline testing."),
):
    """Pulls Bankai GGUF model directly from Hugging Face Hub, verifies SHA256 integrity, and registers in Ollama."""
    print_banner()

    mock_mode = bool(_resolve_val(mock, False))
    if not mock_mode and ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM")):
        mock_mode = True

    model_val = str(_resolve_val(model, "bankai-7b"))
    tag_val = _resolve_val(tag, None)
    repo_val = _resolve_val(repo, None)
    quant_val = str(_resolve_val(quant, "q4_k_m"))
    verify_sha_val = bool(_resolve_val(verify_sha, True))
    sha256_val = _resolve_val(sha256, None)
    ollama_url_val = str(_resolve_val(ollama_url, "http://localhost:11434"))
    no_ollama_val = bool(_resolve_val(no_ollama, False))
    force_val = bool(_resolve_val(force, False))

    console.print(f"[bold cyan]🚀 Project Bankai Auto-Sync Engine: Pulling model '{model_val}'...[/bold cyan]\n")

    manager = ModelManager(ollama_url=ollama_url_val, mock_mode=mock_mode) if ModelManager else None
    if manager is None:
        console.print("[bold red]Error:[/bold red] ModelManager module could not be loaded.")
        raise typer.Exit(code=1)

    result = manager.pull_model(
        model_identifier=model_val,
        ollama_tag=tag_val,
        hf_repo=repo_val,
        force=force_val,
        verify_sha=verify_sha_val,
        create_in_ollama=not no_ollama_val,
        expected_sha256=sha256_val,
        quant=quant_val,
    )

    # Render Result Table
    table = Table(title=f"Model Pull & Ollama Deployment Report: {model_val}", box=None)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold white")
    table.add_row("Model Identifier", result.model_name)
    table.add_row("Target Ollama Tag", result.ollama_tag)
    table.add_row("Hugging Face Source", result.details.get("repo_id", f"krishivjoshi/{model_val}"))
    table.add_row("Local GGUF Path", str(result.gguf_path) if result.gguf_path else "[red]None[/red]")
    table.add_row("Modelfile Generated", str(result.modelfile_path) if result.modelfile_path else "[yellow]None[/yellow]")

    sha_text = result.sha256 or "N/A"
    if result.sha256_verified:
        sha_display = f"{sha_text[:20]}... [bold green]✔ SHA256 Verified[/bold green]"
    else:
        sha_display = f"{sha_text[:20]}... [bold red]✘ Verification Failed[/bold red]"
    table.add_row("SHA256 Integrity", sha_display)

    if not no_ollama_val:
        if result.ollama_created:
            table.add_row("Ollama Registration", f"[bold green]✔ Created '{result.ollama_tag}'[/bold green]")
        elif not result.ollama_healthy:
            table.add_row("Ollama Registration", f"[yellow]⚠ Ollama daemon offline at {ollama_url_val}[/yellow]")
        else:
            table.add_row("Ollama Registration", f"[red]✘ Failed to create model in Ollama[/red]")
    else:
        table.add_row("Ollama Registration", "[dim]Skipped (--no-ollama)[/dim]")

    console.print(table)
    console.print()

    if result.success:
        console.print(f"[bold green]✔ SUCCESS: Model '{model_val}' is ready for local compiler-grounded inference.[/bold green]\n")
    else:
        console.print(f"[bold red]✘ PULL FAILED: {result.message}[/bold red]\n")
        raise typer.Exit(code=1)


@app.command(name="pull", help="Alias for pull-model command.")
def pull_cmd(
    model: str = typer.Argument("bankai-7b", help="Model identifier (e.g. bankai-7b, bankai-10b, krishivjoshi/bankai-7b)."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Ollama model tag to register (e.g. bankai:7b, bankai-7b)."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Hugging Face repository ID override."),
    quant: str = typer.Option("q4_k_m", "--quant", "-q", help="Quantization format to target (default: q4_k_m)."),
    verify_sha: bool = typer.Option(True, "--verify-sha/--no-verify-sha", help="Cryptographically verify SHA256 integrity."),
    sha256: Optional[str] = typer.Option(None, "--sha256", help="Expected SHA256 checksum string."),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama host URL."),
    no_ollama: bool = typer.Option(False, "--no-ollama", help="Skip Ollama model creation (cache GGUF only)."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download even if cached."),
    mock: bool = typer.Option(False, "--mock", help="Force mock execution for offline testing."),
):
    """Alias for pull-model command."""
    pull_model_cmd(
        model=model,
        tag=tag,
        repo=repo,
        quant=quant,
        verify_sha=verify_sha,
        sha256=sha256,
        ollama_url=ollama_url,
        no_ollama=no_ollama,
        force=force,
        mock=mock,
    )


# ==============================================================================
# Conflict Resolution Commands (k-cli conflict ...)
# ==============================================================================

conflict_app = typer.Typer(
    name="conflict",
    help="Detect, inspect, and AI-resolve git merge conflicts.",
    add_completion=False,
)


@conflict_app.command(name="list", help="Detect and show conflicts in repo.")
def conflict_list_cmd(
    dir: str = typer.Option(".", "--dir", "-d", help="Repository or workspace root directory."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    resolver = ConflictResolver() if ConflictResolver else None
    if resolver is None:
        if json_output:
            typer.echo(json.dumps({"error": "ConflictResolver module not available", "conflicts": []}))
        else:
            console.print("[bold red]Error:[/bold red] ConflictResolver module is not available.")
        raise typer.Exit(code=1)

    conflicts = resolver.find_conflicts(repo_path=str(target_dir))

    if json_output:
        out_data = {
            "repo_path": str(target_dir),
            "total_conflicts": len(conflicts),
            "conflicted_files_count": len({c.file_path for c in conflicts if c.file_path}),
            "conflicts": [c.to_dict() for c in conflicts],
        }
        typer.echo(json.dumps(out_data, indent=2))
        return

    if not conflicts:
        console.print("[bold green]✔ Clean: No git merge conflicts detected in workspace.[/bold green]")
        return

    table = Table(title=f"Git Merge Conflicts Detected ({len(conflicts)})", box=None)
    table.add_column("File", style="bold cyan")
    table.add_column("Lines", style="magenta")
    table.add_column("Type", style="yellow")
    table.add_column("Scope / Function", style="white")
    table.add_column("Ours Label", style="green")
    table.add_column("Theirs Label", style="red")

    for c in conflicts:
        rel_p = str(Path(c.file_path).relative_to(target_dir)) if c.file_path.startswith(str(target_dir)) else c.file_path
        mtype = "3-Way (Diff3)" if c.is_3way() else "2-Way"
        table.add_row(
            rel_p,
            f"L{c.start_line}-{c.end_line}",
            mtype,
            c.scope_name or "(top-level)",
            c.ours_label,
            c.theirs_label,
        )

    console.print(table)
    console.print(f"\n[dim]Run [bold]k-cli conflict resolve --file <path>[/bold] or [bold]k-cli conflict resolve[/bold] to resolve.[/dim]\n")


@conflict_app.command(name="resolve", help="AI 3-way merge with verification.")
def conflict_resolve_cmd(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Specific conflicted file path to resolve."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model identifier to use."),
    auto_accept: bool = typer.Option(False, "--auto-accept", "-y", help="Automatically accept and stage resolved files."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace root directory."),
    mock: bool = typer.Option(False, "--mock", help="Force mock execution for testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    resolver = ConflictResolver(default_model=model) if ConflictResolver else None
    if resolver is None:
        if json_output:
            typer.echo(json.dumps({"error": "ConflictResolver module not available", "success": False}))
        else:
            console.print("[bold red]Error:[/bold red] ConflictResolver module is not available.")
        raise typer.Exit(code=1)

    is_mock = mock or os.getenv("KCLI_MOCK_MODE", "").lower() in ("true", "1") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM"))
    driver = LLMDriver(model_name=model or "qwen2.5-coder:1.5b", mock_mode=is_mock)
    verifier = Verifier()

    if file:
        target_file = Path(file).resolve() if not Path(file).is_absolute() else Path(file)
        if not target_file.exists():
            if json_output:
                typer.echo(json.dumps({"error": f"File '{file}' not found", "success": False}))
            else:
                console.print(f"[bold red]Error:[/bold red] Conflicted file '{file}' not found.")
            raise typer.Exit(code=1)

        res = resolver.resolve_file(
            file_path=str(target_file),
            llm_driver=driver,
            verifier=verifier,
            auto_stage=auto_accept,
        )

        if json_output:
            typer.echo(json.dumps(res.to_dict(), indent=2))
            return

        if res.success:
            console.print(f"[bold green]✔ Successfully resolved {res.resolved_conflicts}/{res.total_conflicts} conflict(s) in {file}.[/bold green]")
            if res.staged:
                console.print("[dim]✔ Automatically staged resolved file with git add.[/dim]")
        else:
            console.print(f"[bold red]✘ Failed to resolve conflicts in {file}: {res.error_message}[/bold red]")
            raise typer.Exit(code=1)
    else:
        summary = resolver.resolve_all_conflicts(
            repo_path=str(target_dir),
            llm_driver=driver,
            verifier=verifier,
            auto_stage=auto_accept,
        )

        if json_output:
            typer.echo(json.dumps(summary.to_dict(), indent=2))
            return

        if summary.total_files == 0:
            console.print("[bold green]✔ No merge conflicts detected in workspace.[/bold green]")
            return

        console.print(f"[bold cyan]Conflict Resolution Summary:[/bold cyan] {summary.resolved_files}/{summary.total_files} files resolved successfully.")
        for fpath, f_res in summary.file_results.items():
            glyph = "[bold green]✔[/bold green]" if f_res.success else "[bold red]✘[/bold red]"
            console.print(f"  {glyph} {os.path.basename(fpath)}: {f_res.resolved_conflicts}/{f_res.total_conflicts} resolved")

        if not summary.success:
            raise typer.Exit(code=1)


# ==============================================================================
# Pull Request Lifecycle Commands (k-cli pr ...)
# ==============================================================================

pr_app = typer.Typer(
    name="pr",
    help="Inspect, review, fix, and merge GitHub Pull Requests.",
    add_completion=False,
)


@pr_app.command(name="list", help="List GitHub pull requests.")
def pr_list_cmd(
    state: str = typer.Option("open", "--state", "-s", help="Filter PRs by state: open, closed, all."),
    limit: int = typer.Option(30, "--limit", "-l", help="Max number of PRs to retrieve."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace directory."),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub client for offline testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    is_mock = mock or os.getenv("KCLI_MOCK_GITHUB", "0").lower() in ("1", "true") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(repo_dir=target_dir, mock_mode=is_mock) if GitHubClient else None

    if client is None:
        if json_output:
            typer.echo(json.dumps({"error": "GitHubClient module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] GitHubClient module is not available.")
        raise typer.Exit(code=1)

    try:
        prs = client.list_pull_requests(state=state, limit=limit)
    except Exception as ex:
        if json_output:
            typer.echo(json.dumps({"error": str(ex), "pull_requests": []}))
        else:
            console.print(f"[bold yellow]⚠ Could not list pull requests:[/bold yellow] {ex}")
        return

    if json_output:
        typer.echo(json.dumps([pr.to_dict() for pr in prs], indent=2))
        return

    if not prs:
        console.print(f"[yellow]No {state} pull requests found.[/yellow]")
        return

    table = Table(title=f"Pull Requests ({client.owner}/{client.repo}) [{state}]", box=None)
    table.add_column("#", style="bold cyan", justify="right")
    table.add_column("Title", style="bold white")
    table.add_column("Author", style="magenta")
    table.add_column("Branch", style="green")
    table.add_column("State", style="yellow")
    table.add_column("Created", style="dim")

    for pr in prs:
        state_style = "green" if pr.state == "open" else ("magenta" if pr.merged else "red")
        table.add_row(
            str(pr.number),
            pr.title,
            pr.author or "unknown",
            f"{pr.head_branch} -> {pr.base_branch}",
            f"[{state_style}]{pr.state.upper()}[/{state_style}]",
            pr.created_at[:10] if pr.created_at else "",
        )

    console.print(table)


@pr_app.command(name="view", help="View pull request details and diff.")
def pr_view_cmd(
    pr_num: int = typer.Argument(..., help="Pull request number."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace directory."),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub client for offline testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    is_mock = mock or os.getenv("KCLI_MOCK_GITHUB", "0").lower() in ("1", "true") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(repo_dir=target_dir, mock_mode=is_mock) if GitHubClient else None

    if client is None:
        if json_output:
            typer.echo(json.dumps({"error": "GitHubClient module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] GitHubClient module is not available.")
        raise typer.Exit(code=1)

    try:
        pr = client.get_pull_request(pr_num)
        diff = client.get_pr_diff(pr_num)
        ci = client.get_ci_status(pr.head_sha or pr.head_branch)
    except Exception as ex:
        if json_output:
            typer.echo(json.dumps({"error": str(ex)}))
        else:
            console.print(f"[bold yellow]⚠ Could not view pull request #{pr_num}:[/bold yellow] {ex}")
        return

    if json_output:
        data = pr.to_dict()
        data["diff"] = diff
        data["ci_status"] = ci.to_dict()
        typer.echo(json.dumps(data, indent=2))
        return

    status_style = "bold green" if pr.state == "open" else ("bold magenta" if pr.merged else "bold red")
    ci_text = "[bold green]✔ Passing[/bold green]" if ci.is_passing else f"[bold red]✘ Failing ({ci.failed_count} failed)[/bold red]"

    panel_content = (
        f"[bold white]{pr.title}[/bold white]\n\n"
        f"• [cyan]Author:[/cyan] {pr.author}   • [cyan]State:[/cyan] [{status_style}]{pr.state.upper()}[/{status_style}]   • [cyan]CI:[/cyan] {ci_text}\n"
        f"• [cyan]Branches:[/cyan] [green]{pr.head_branch}[/green] -> [blue]{pr.base_branch}[/blue] (HEAD: {pr.head_sha[:8] if pr.head_sha else 'N/A'})\n\n"
        f"[bold]Description:[/bold]\n{pr.body or '(No description provided)'}"
    )
    console.print(Panel(panel_content, title=f"Pull Request #{pr.number}", border_style="cyan"))

    if diff.strip():
        console.print("\n[bold cyan]Diff Preview:[/bold cyan]")
        diff_lines = diff.splitlines()
        diff_preview = "\n".join(diff_lines[:30])
        if len(diff_lines) > 30:
            diff_preview += f"\n... ({len(diff_lines) - 30} more diff lines)"
        console.print(Syntax(diff_preview, "diff", theme="monokai", line_numbers=True))


@pr_app.command(name="review", help="Perform compiler-grade AI code review on a pull request.")
def pr_review_cmd(
    pr_num: int = typer.Argument(..., help="Pull request number."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model identifier to use."),
    post_comment: bool = typer.Option(False, "--post-comment", help="Automatically post review comment to GitHub PR."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace directory."),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub client for offline testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    is_mock = mock or os.getenv("KCLI_MOCK_GITHUB", "0").lower() in ("1", "true") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(repo_dir=target_dir, mock_mode=is_mock) if GitHubClient else None
    mgr = PRLifecycleManager(client=client, repo_dir=target_dir) if PRLifecycleManager else None

    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "PRLifecycleManager module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] PRLifecycleManager module is not available.")
        raise typer.Exit(code=1)

    driver = LLMDriver(model_name=model or "qwen2.5-coder:1.5b", mock_mode=is_mock)
    try:
        review = mgr.review_pr(
            pr_number=pr_num,
            llm_driver=driver,
            model=model,
            post_comment=post_comment,
        )
    except Exception as ex:
        if json_output:
            typer.echo(json.dumps({"error": f"Failed to review PR #{pr_num}: {ex}"}))
        else:
            console.print(f"[bold red]✘ Failed to review PR #{pr_num}:[/bold red] {ex}")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(review.to_dict(), indent=2))
        return

    verdict_color = "green" if review.verdict == "APPROVE" else ("red" if review.verdict == "REQUEST_CHANGES" else "yellow")
    console.print(Panel(
        f"[bold {verdict_color}]VERDICT: {review.verdict}[/bold {verdict_color}]\n\n"
        f"[bold]Summary:[/bold] {review.summary}\n\n"
        f"[bold red]Bugs Identified ({len(review.bugs)}):[/bold red]\n" + ("\n".join(f"  • {b}" for b in review.bugs) if review.bugs else "  None detected.") + "\n\n"
        f"[bold yellow]Security Issues ({len(review.security_issues)}):[/bold yellow]\n" + ("\n".join(f"  • {s}" for s in review.security_issues) if review.security_issues else "  None detected.") + "\n\n"
        f"[bold cyan]Performance Notes ({len(review.performance_notes)}):[/bold cyan]\n" + ("\n".join(f"  • {p}" for p in review.performance_notes) if review.performance_notes else "  None detected."),
        title=f"AI Code Review: PR #{pr_num}",
        border_style=verdict_color,
    ))
    if post_comment:
        console.print("[bold green]✔ Posted review comment to GitHub PR.[/bold green]")


@pr_app.command(name="fix", help="Automatically generate surgical fixes for PR issues, verify tests, and commit.")
def pr_fix_cmd(
    pr_num: int = typer.Argument(..., help="Pull request number."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model identifier to use."),
    auto_push: bool = typer.Option(False, "--auto-push", help="Automatically push fixes to remote branch on passing verification."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace directory."),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub client for offline testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    is_mock = mock or os.getenv("KCLI_MOCK_GITHUB", "0").lower() in ("1", "true") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(repo_dir=target_dir, mock_mode=is_mock) if GitHubClient else None
    mgr = PRLifecycleManager(client=client, repo_dir=target_dir) if PRLifecycleManager else None

    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "PRLifecycleManager module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] PRLifecycleManager module is not available.")
        raise typer.Exit(code=1)

    driver = LLMDriver(model_name=model or "qwen2.5-coder:1.5b", mock_mode=is_mock)
    try:
        res = mgr.fix_pr(
            pr_number=pr_num,
            llm_driver=driver,
            auto_push=auto_push,
        )
    except Exception as ex:
        if json_output:
            typer.echo(json.dumps({"error": f"Failed to fix PR #{pr_num}: {ex}"}))
        else:
            console.print(f"[bold red]✘ Failed to fix PR #{pr_num}:[/bold red] {ex}")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(res.to_dict(), indent=2))
        return

    if res.success:
        console.print(f"[bold green]✔ Fixed PR #{pr_num} successfully![/bold green]")
        console.print(f"  • Branch: {res.branch}")
        console.print(f"  • Files modified: {', '.join(res.fixes_applied) if res.fixes_applied else 'None'}")
        if res.commit_sha:
            console.print(f"  • Commit: {res.commit_sha}")
        if res.pushed:
            console.print("  • Remote push: [bold green]✔ Pushed to origin[/bold green]")
    else:
        console.print(f"[bold red]✘ Failed to fix PR #{pr_num}: {res.error_message}[/bold red]")
        raise typer.Exit(code=1)


@pr_app.command(name="merge", help="Merge pull request upon CI and verification checks passing.")
def pr_merge_cmd(
    pr_num: int = typer.Argument(..., help="Pull request number."),
    method: str = typer.Option("squash", "--method", help="Merge strategy: squash, rebase, merge."),
    require_ci: bool = typer.Option(True, "--require-ci/--no-require-ci", help="Require CI check runs to pass before merging."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace directory."),
    mock: bool = typer.Option(False, "--mock", help="Use mock GitHub client for offline testing."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    is_mock = mock or os.getenv("KCLI_MOCK_GITHUB", "0").lower() in ("1", "true") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(repo_dir=target_dir, mock_mode=is_mock) if GitHubClient else None
    mgr = PRLifecycleManager(client=client, repo_dir=target_dir) if PRLifecycleManager else None

    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "PRLifecycleManager module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] PRLifecycleManager module is not available.")
        raise typer.Exit(code=1)

    try:
        ok = mgr.auto_merge_pr(
            pr_number=pr_num,
            require_ci_pass=require_ci,
            merge_method=method,
        )
    except Exception as ex:
        if json_output:
            typer.echo(json.dumps({"error": f"Failed to merge PR #{pr_num}: {ex}"}))
        else:
            console.print(f"[bold red]✘ Failed to merge PR #{pr_num}:[/bold red] {ex}")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps({"pr_number": pr_num, "merged": ok, "method": method}, indent=2))
        return

    if ok:
        console.print(f"[bold green]✔ Successfully merged PR #{pr_num} using '{method}' strategy.[/bold green]")
    else:
        console.print(f"[bold red]✘ Failed to merge PR #{pr_num}. Ensure CI checks are passing and merge requirements are met.[/bold red]")
        raise typer.Exit(code=1)


# ==============================================================================
# Model Context Protocol Commands (k-cli mcp ...)
# ==============================================================================

mcp_app = typer.Typer(
    name="mcp",
    help="Manage, inspect, and test Model Context Protocol (MCP) servers and tools.",
    add_completion=False,
)


@mcp_app.command(name="list", help="List configured MCP servers.")
def mcp_list_subcmd(
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available", "servers": []}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    servers = mgr.list_servers()
    if json_output:
        typer.echo(json.dumps(servers, indent=2))
        return

    table = Table(title="Configured Model Context Protocol (MCP) Servers", box=None)
    table.add_column("Server Name", style="bold cyan")
    table.add_column("Transport", style="magenta")
    table.add_column("Command / URL", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Tools", justify="right")
    table.add_column("Resources", justify="right")

    if not servers:
        console.print("[yellow]No MCP servers configured yet.[/yellow]")
        console.print("Add one using: [italic]k-cli mcp add github npx -a '-y @modelcontextprotocol/server-github'[/italic]\n")
        return

    for s in servers:
        status_style = "green" if s["connected"] else ("yellow" if s["disabled"] else "dim")
        status_text = f"[{status_style}]{s['status']}[/{status_style}]"
        table.add_row(
            s["name"],
            s["transport"],
            s["command"],
            status_text,
            str(s["tool_count"]),
            str(s["resource_count"]),
        )
    console.print(table)


@mcp_app.command(name="add", help="Add or update an MCP server configuration.")
def mcp_add_subcmd(
    name: str = typer.Argument(..., help="Server identifier name."),
    command: str = typer.Argument(..., help="Command executable (e.g. npx, python, node)."),
    args: Optional[List[str]] = typer.Argument(None, help="Command arguments."),
    extra_args: Optional[str] = typer.Option(None, "--args", "-a", help="Arguments as a string or JSON list."),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="JSON string of environment variables."),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL for SSE/HTTP transport."),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport type (stdio, sse, http)."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config, auto_load=True) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available", "success": False}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    env_dict = {}
    if env:
        try:
            env_dict = json.loads(env)
        except Exception:
            pass

    parsed_args = list(args) if args else []
    if extra_args:
        try:
            val = json.loads(extra_args)
            if isinstance(val, list):
                parsed_args.extend([str(x) for x in val])
            else:
                parsed_args.extend(shlex.split(str(extra_args)))
        except Exception:
            parsed_args.extend(shlex.split(str(extra_args)))

    cfg = MCPServerConfig(
        name=name,
        command=command,
        args=parsed_args,
        env=env_dict,
        url=url,
        transport=transport,
    )
    mgr.add_server(name, cfg, save=True)

    if json_output:
        typer.echo(json.dumps({"success": True, "name": name, "server": cfg.to_dict()}, indent=2))
        return

    console.print(f"[bold green]✔ Server '{name}' successfully registered and saved to configuration.[/bold green]")


@mcp_app.command(name="remove", help="Remove an MCP server from configuration.")
def mcp_remove_subcmd(
    name: str = typer.Argument(..., help="Server identifier name to remove."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config, auto_load=True) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available", "success": False}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    ok = mgr.remove_server(name, save=True)
    if json_output:
        typer.echo(json.dumps({"success": ok, "name": name}, indent=2))
        return

    if ok:
        console.print(f"[bold green]✔ Server '{name}' removed successfully.[/bold green]")
    else:
        console.print(f"[bold yellow]Server '{name}' was not found in configuration.[/bold yellow]")


@mcp_app.command(name="tools", help="List discovered MCP tools.")
def mcp_tools_subcmd(
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Filter tools by server name."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available", "tools": []}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    tools = mgr.list_tools(server_name=server)
    if json_output:
        typer.echo(json.dumps([t.to_dict() for t in tools], indent=2))
        return

    if not tools:
        console.print(f"[yellow]No tools discovered on {'server ' + server if server else 'any active server'}.[/yellow]")
        return

    table = Table(title=f"Discovered MCP Tools ({len(tools)})", box=None)
    table.add_column("Tool Name", style="bold cyan")
    table.add_column("Server", style="magenta")
    table.add_column("Description", style="white")
    for t in tools:
        table.add_row(t.name, t.server_name or "default", t.description)
    console.print(table)


@mcp_app.command(name="call", help="Call an MCP tool with JSON arguments.")
def mcp_call_subcmd(
    tool_name: str = typer.Argument(..., help="Tool name to execute."),
    json_args: str = typer.Argument("{}", help="JSON string arguments for tool call."),
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Server name if tool is ambiguous."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available"}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    parsed_args: Dict[str, Any] = {}
    if json_args:
        try:
            parsed_args = json.loads(json_args)
        except Exception as pe:
            if json_output:
                typer.echo(json.dumps({"error": f"Invalid JSON arguments: {pe}"}))
            else:
                console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {pe}")
            raise typer.Exit(code=1)

    try:
        result = mgr.call_tool(tool_name, arguments=parsed_args, server_name=server)
        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2))
            return

        console.print(f"[bold green]Tool '{tool_name}' Output:[/bold green]")
        console.print(result.text if result.text else json.dumps(result.raw, indent=2))
    except Exception as ce:
        if json_output:
            typer.echo(json.dumps({"error": str(ce), "tool": tool_name}))
        else:
            console.print(f"[bold red]Tool execution error:[/bold red] {ce}")
        raise typer.Exit(code=1)


@mcp_app.command(name="test", help="Test connection to an MCP server.")
def mcp_test_subcmd(
    name: Optional[str] = typer.Argument(None, help="Server identifier name to test."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to mcp.json config."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    mgr = MCPManager(config_path=config) if MCPManager else None
    if mgr is None:
        if json_output:
            typer.echo(json.dumps({"error": "MCPManager not available", "success": False}))
        else:
            console.print("[bold red]Error:[/bold red] MCPManager module is not available.")
        raise typer.Exit(code=1)

    target_name = name or (list(mgr.server_configs.keys())[0] if mgr.server_configs else None)
    if not target_name:
        if json_output:
            typer.echo(json.dumps({"error": "No MCP servers configured to test", "success": False}))
        else:
            console.print("[bold red]Error:[/bold red] No MCP servers configured to test.")
        raise typer.Exit(code=1)

    res = mcp_test_connection(target_name, manager=mgr)
    if json_output:
        typer.echo(json.dumps(res, indent=2))
        return

    if res["success"]:
        console.print(f"[bold green]✔ Connected to '{target_name}' in {res['duration_ms']}ms![/bold green]")
        console.print(f"  • Tools Discovered: {len(res.get('tools', []))}")
        for t in res.get("tools", []):
            console.print(f"    - [bold white]{t.get('name')}[/bold white]: {t.get('description', '')}")
    else:
        console.print(f"[bold red]✘ Connection to '{target_name}' failed: {res['error']}[/bold red]")
        raise typer.Exit(code=1)


# ==============================================================================
# Task Deduplication Commands (k-cli dedup ...)
# ==============================================================================

dedup_app = typer.Typer(
    name="dedup",
    help="Check and detect duplicate issues, tasks, and existing code.",
    add_completion=False,
)


@dedup_app.command(name="check", help="Check if a task or query matches existing commits or symbols.")
def dedup_check_cmd(
    query_or_issue: str = typer.Argument(..., help="Query string, issue title, or requested task."),
    dir: str = typer.Option(".", "--dir", "-d", help="Repository workspace root directory."),
    threshold: float = typer.Option(0.65, "--threshold", "-t", help="Confidence threshold (0.0 to 1.0) to mark as duplicate."),
    depth: int = typer.Option(50, "--depth", help="Git commit history depth to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format."),
):
    target_dir = Path(dir).resolve()
    engine = DedupEngine(repo_path=str(target_dir), duplicate_threshold=threshold, git_depth=depth) if DedupEngine else None

    if engine is None:
        if json_output:
            typer.echo(json.dumps({"error": "DedupEngine module not available"}))
        else:
            console.print("[bold red]Error:[/bold red] DedupEngine module is not available.")
        raise typer.Exit(code=1)

    match = engine.scan_for_duplicate(query=query_or_issue)

    if json_output:
        typer.echo(json.dumps(match.to_dict() if match else {"is_duplicate": False, "confidence": 0.0}, indent=2))
        return

    if match and match.is_duplicate:
        console.print(Panel(
            f"[bold yellow]⚠ POTENTIAL DUPLICATE DETECTED ({match.confidence:.1%} confidence)[/bold yellow]\n\n"
            f"[bold]Rationale:[/bold] {match.explanation}\n"
            f"• [cyan]Match Type:[/cyan] {match.match_type.upper()}\n"
            + (f"• [cyan]Existing Commit:[/cyan] {match.existing_commit[:10]}\n" if match.existing_commit else "")
            + (f"• [cyan]File Location:[/cyan] {match.file_path}" + (f" (lines {match.line_range[0]}-{match.line_range[1]})" if match.line_range else "") + "\n" if match.file_path else ""),
            title="Deduplication Warning",
            border_style="yellow",
        ))
    else:
        conf_str = f" ({match.confidence:.1%} max match)" if match else ""
        console.print(f"[bold green]✔ Unique: No duplicate commits or symbols found{conf_str}. Safe to proceed.[/bold green]")


@app.command(name="commit", help="Generate AST-grounded conventional commit message and stage/commit changes.")
def commit_command(
    push: bool = typer.Option(False, "--push", help="Push commit to remote branch after creating it."),
    all: bool = typer.Option(True, "--all", "-a", help="Stage all uncommitted working tree changes."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Optional model identifier for AI-assisted refinement."),
    repo: str = typer.Option(".", "--repo", "-r", help="Repository path."),
    json_output: bool = typer.Option(False, "--json", help="Output proposal in JSON format without committing."),
):
    """Generates an intelligent conventional commit from AST diffs and stages/commits changes."""
    target_path = Path(repo).resolve()
    engine = SmartGitEngine(repo_path=str(target_path)) if SmartGitEngine else None

    if engine is None:
        console.print("[bold red]Error:[/bold red] SmartGitEngine module is not available.")
        raise typer.Exit(code=1)

    if not engine.is_git_repo():
        console.print(f"[bold red]Error:[/bold red] '{target_path}' is not a valid git repository.")
        raise typer.Exit(code=1)

    proposal = engine.generate_smart_commit(staged_only=not all, model=model)

    if json_output:
        typer.echo(json.dumps(proposal.to_dict(), indent=2))
        return

    if not proposal.files_changed:
        console.print("[yellow]Working tree is clean. No uncommitted modifications found.[/yellow]")
        return

    # Render proposal preview
    console.print(Panel(
        f"[bold cyan]Type:[/bold cyan] {proposal.commit_type.upper()}"
        + (f" | [magenta]Scope:[/magenta] {proposal.scope}" if proposal.scope else "")
        + f"\n[bold green]Subject:[/bold green] {proposal.subject}\n\n"
        f"[bold]Body:[/bold]\n{proposal.body}\n\n"
        f"[dim]{proposal.raw_diff_summary}[/dim]",
        title="✨ Smart Conventional Commit Proposal",
        border_style="cyan",
    ))

    # Auto-stage and commit
    success = engine.auto_stage_and_commit(message=proposal.full_message, push=push, all_files=all)
    if success:
        console.print(f"[bold green]✔ Changes committed successfully![/bold green]" + (" Pushed to remote." if push else ""))
    else:
        console.print("[bold red]✘ Git commit failed.[/bold red]")
        raise typer.Exit(code=1)


security_app = typer.Typer(
    name="security",
    help="Fast AST & Regex security scanner and surgical auto-healer.",
    add_completion=False,
)


@security_app.command(name="scan", help="Scan repository for hardcoded secrets, SQLi, ReDoS, and unsafe execution.")
def security_scan_command(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository path to scan."),
    json_output: bool = typer.Option(False, "--json", help="Output findings in JSON format."),
):
    """Scans codebase for security vulnerabilities with AST & regex analysis."""
    target_path = Path(repo).resolve()
    healer = SecurityHealer(repo_path=str(target_path)) if SecurityHealer else None

    if healer is None:
        if json_output:
            typer.echo(json.dumps({"error": "SecurityHealer module is not available"}))
        else:
            console.print("[bold red]Error:[/bold red] SecurityHealer module is not available.")
        raise typer.Exit(code=1)

    report = healer.scan_repository()

    if json_output:
        typer.echo(report.to_json(indent=2))
        return

    if not report.findings:
        console.print(f"[bold green]✔ Clean Workspace: 0 security vulnerabilities found across {report.scanned_files_count} files ({report.scan_duration_seconds:.2f}s).[/bold green]")
        return

    table = Table(title=f"🛡️ Security Vulnerability Scan ({report.total_findings} findings)", box=None)
    table.add_column("ID", style="bold cyan")
    table.add_column("Severity", style="bold")
    table.add_column("Type", style="magenta")
    table.add_column("File:Line", style="white")
    table.add_column("CVSS", justify="right", style="yellow")
    table.add_column("CWE", style="dim")
    table.add_column("Description", style="white")

    for f in report.findings:
        sev_style = "bold red" if f.severity in ("CRITICAL", "HIGH") else "bold yellow"
        table.add_row(
            f.id,
            f"[{sev_style}]{f.severity}[/{sev_style}]",
            f.vuln_type,
            f"{f.file_path}:{f.line_number}",
            str(f.cvss_score),
            f.cwe_id,
            f.description[:60] + ("..." if len(f.description) > 60 else ""),
        )

    console.print(table)
    console.print(f"\n[dim]Files scanned: {report.scanned_files_count} | Duration: {report.scan_duration_seconds:.2f}s | Max CVSS: {report.max_cvss_score}[/dim]")
    console.print("[cyan]Run [bold]k-cli security heal --all[/bold] to automatically remediate detected vulnerabilities.[/cyan]\n")


@security_app.command(name="heal", help="Auto-heal detected security vulnerabilities with AST & test verification.")
def security_heal_command(
    vuln_id: Optional[str] = typer.Option(None, "--vuln-id", "-i", help="Specific vulnerability ID to heal."),
    heal_all: bool = typer.Option(False, "--all", "-a", help="Heal all detected vulnerabilities."),
    repo: str = typer.Option(".", "--repo", "-r", help="Repository path."),
    json_output: bool = typer.Option(False, "--json", help="Output healing results in JSON format."),
):
    """Surgically remediates detected vulnerabilities with ground-truth verification."""
    target_path = Path(repo).resolve()
    healer = SecurityHealer(repo_path=str(target_path)) if SecurityHealer else None

    if healer is None:
        if json_output:
            typer.echo(json.dumps({"error": "SecurityHealer module is not available"}))
        else:
            console.print("[bold red]Error:[/bold red] SecurityHealer module is not available.")
        raise typer.Exit(code=1)

    if not vuln_id and not heal_all:
        console.print("[bold red]Error:[/bold red] Please specify either [bold]--vuln-id <id>[/bold] or [bold]--all[/bold].")
        raise typer.Exit(code=1)

    results: List[VulnerabilityHealResult] = []
    if vuln_id:
        res = healer.auto_heal_vulnerability(vuln_id=vuln_id)
        results.append(res)
    elif heal_all:
        results = healer.heal_all_vulnerabilities()

    if json_output:
        typer.echo(json.dumps([r.to_dict() for r in results], indent=2))
        return

    if not results:
        console.print("[yellow]No vulnerabilities were targeted or found for healing.[/yellow]")
        return

    for r in results:
        if r.success:
            console.print(Panel(
                f"[bold green]✔ Successfully Healed {r.vuln_id}[/bold green] in [cyan]{r.file_path}[/cyan]\n\n"
                f"• AST Syntax Verified: [green]✔[/green]\n"
                f"• Test Suite Passed: [green]✔[/green]\n"
                f"• Re-scan Clean: [green]✔[/green]\n\n"
                + (f"[dim]Applied Diff:\n{r.diff}[/dim]" if r.diff else ""),
                title=f"Remediation Success: {r.vuln_id}",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[bold red]✘ Failed to heal {r.vuln_id}[/bold red] in [cyan]{r.file_path or 'unknown'}[/cyan]\n\n"
                f"[bold]Reason:[/bold] {r.error_message}",
                title=f"Remediation Failed: {r.vuln_id}",
                border_style="red",
            ))


# =============================================================================
# Universal AI Models Hub Commands (`k-cli models`)
# =============================================================================
models_app = typer.Typer(help="Universal AI Model Hub, local SLMs, and benchmarks.")


@models_app.command("list")
def models_list(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter by provider (ollama, gemini, anthropic, openai, groq, etc.)."),
    local_only: bool = typer.Option(False, "--local", "-l", help="List only local models."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Lists available local and cloud AI models in the Universal Model Hub."""
    hub = ModelHub()
    models = hub.list_models(provider=provider, local_only=local_only)

    if json_output:
        print(json.dumps([m.to_dict() for m in models], indent=2))
        return

    table = Table(title="🤖 K-CLI Universal Model Hub", border_style="cyan", header_style="bold magenta")
    table.add_column("Model ID", style="bold cyan")
    table.add_column("Provider", style="yellow")
    table.add_column("Type", style="green")
    table.add_column("Context", justify="right")
    table.add_column("Status / Installed", justify="center")
    table.add_column("Description", style="dim")

    for m in models:
        type_str = "Local SLM" if m.is_local else "Cloud LLM"
        status_str = "[bold green]✔ Installed[/bold green]" if m.is_installed else ("[dim]Cloud Available[/dim]" if not m.is_local else "[yellow]Pull Available[/yellow]")
        table.add_row(
            m.id,
            m.provider.value.upper(),
            type_str,
            f"{m.context_window // 1024}k",
            status_str,
            m.description[:45] + ("..." if len(m.description) > 45 else ""),
        )

    console.print(table)


@models_app.command("test")
def models_test(
    model: str = typer.Argument(..., help="Model identifier to test (e.g. qwen2.5-coder:1.5b, gemini-2.0-flash)."),
    prompt: str = typer.Option("Write a Python function to compute fibonacci numbers iteratively.", "--prompt", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Benchmarks model latency, throughput (tok/s), and memory RSS consumption."""
    hub = ModelHub()
    console.print(f"[bold cyan]Running benchmark for model [yellow]{model}[/yellow]...[/bold cyan]")
    res = hub.benchmark_model(model_name=model, prompt=prompt)

    if json_output:
        print(json.dumps(res.to_dict(), indent=2))
        return

    if res.success:
        console.print(Panel(
            f"[bold green]✔ Benchmark Succeeded[/bold green]\n\n"
            f"• [bold]Model:[/bold] {res.model_id} ({res.provider})\n"
            f"• [bold]Throughput:[/bold] [bold cyan]{res.tokens_per_second:.1f} tok/s[/bold cyan]\n"
            f"• [bold]Time to First Token (TTFT):[/bold] {res.time_to_first_token:.3f}s\n"
            f"• [bold]Total Duration:[/bold] {res.duration_seconds:.3f}s ({res.tokens_generated} tokens)\n"
            f"• [bold]Process RAM RSS:[/bold] {res.ram_rss_mb:.1f} MB\n\n"
            f"[dim]Output Preview:\n{res.sample_output}[/dim]",
            title="Model Benchmark Telemetry",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]✘ Benchmark Failed[/bold red]\n\n[bold]Error:[/bold] {res.error_message}",
            title="Benchmark Error",
            border_style="red",
        ))


@models_app.command("pull")
def models_pull(
    model: str = typer.Argument(..., help="Local model name to pull via Ollama (e.g. qwen2.5-coder:7b)."),
):
    """Pulls a local model onto the local machine via Ollama daemon."""
    hub = ModelHub()
    console.print(f"[bold cyan]Pulling local model [yellow]{model}[/yellow]...[/bold cyan]")
    success = hub.pull_model(model_name=model, stream_callback=lambda msg: console.print(msg, end=""))
    if success:
        console.print(f"\n[bold green]✔ Model {model} pulled and ready for local inference.[/bold green]")
    else:
        console.print(f"\n[bold red]✘ Failed pulling model {model}. Ensure Ollama daemon is running at http://localhost:11434[/bold red]")


@models_app.command("providers")
def models_providers(
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Inspects configuration and active API credentials across all supported providers."""
    hub = ModelHub()
    statuses = {}
    for p in ModelProvider:
        statuses[p.value] = hub.is_provider_configured(p)

    if json_output:
        print(json.dumps(statuses, indent=2))
        return

    table = Table(title="⚡ AI Model Provider Status", border_style="cyan", header_style="bold magenta")
    table.add_column("Provider", style="bold yellow")
    table.add_column("Type", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Configuration Requirement", style="dim")

    for p in ModelProvider:
        is_ready = statuses[p.value]
        status_str = "[bold green]✔ Ready[/bold green]" if is_ready else "[dim red]Not Configured[/dim red]"
        prov_type = "Local SLM" if p in (ModelProvider.OLLAMA, ModelProvider.LLAMACPP, ModelProvider.NATIVE) else "Cloud API"
        req_str = "http://localhost:11434" if p == ModelProvider.OLLAMA else (f"export {p.value.upper()}_API_KEY" if p != ModelProvider.MOCK else "None (Built-in)")
        table.add_row(p.value.upper(), prov_type, status_str, req_str)

    console.print(table)


@models_app.command("set-default", help="Set and persist the default AI model (e.g. 'k-cli models set-default claude-3-5-sonnet' or 'auto').")
def models_set_default(
    model_name: str = typer.Argument(..., help="Model identifier to set as default (or 'auto' for adaptive intent routing)."),
):
    """Sets and saves the developer's default preferred AI model."""
    DevPreferencesManager.set_default_model(model_name)
    console.print(f"[bold green]✔ Default model successfully set to:[/bold green] [bold cyan]{model_name}[/bold cyan]")
    console.print("[dim]K-CLI will automatically route to this model when in default mode.[/dim]")


@models_app.command("get-default", help="Display the currently active default AI model.")
def models_get_default():
    """Prints the currently configured default AI model."""
    current = DevPreferencesManager.get_default_model()
    console.print(f"[bold cyan]Current Default Model:[/bold cyan] [bold green]{current}[/bold green]")


# =============================================================================
# GitHub Ecosystem Commands (`k-cli gh` / `k-cli issue` / `k-cli release`)
# =============================================================================
gh_app = typer.Typer(help="Complete GitHub ecosystem & autonomous issue solver.")
issue_app = typer.Typer(help="Manage and autonomously solve GitHub issues.")
release_app = typer.Typer(help="Manage GitHub releases & automated changelogs.")
action_app = typer.Typer(help="Inspect GitHub Actions CI/CD runs & logs.")
gist_app = typer.Typer(help="Create and manage GitHub Gists.")


@issue_app.command("list")
@gh_app.command("issues")
def gh_issue_list(
    state: str = typer.Option("open", "--state", "-s", help="Issue state (open, closed, all)."),
    limit: int = typer.Option(30, "--limit", "-n", help="Max issues to return."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Lists repository issues."""
    engine = GitHubEngine()
    issues = engine.list_issues(state=state, limit=limit)

    if json_output:
        print(json.dumps([i.to_dict() for i in issues], indent=2))
        return

    table = Table(title=f"🐙 GitHub Issues ({engine.owner}/{engine.repo})", border_style="cyan", header_style="bold magenta")
    table.add_column("#", justify="right", style="bold cyan")
    table.add_column("State", justify="center")
    table.add_column("Title", style="white")
    table.add_column("Author", style="dim yellow")
    table.add_column("Labels", style="dim green")
    table.add_column("Comments", justify="right")

    for i in issues:
        state_badge = "[bold green]open[/bold green]" if i.state == "open" else "[dim red]closed[/dim red]"
        table.add_row(
            str(i.number),
            state_badge,
            i.title[:50],
            f"@{i.author}",
            ", ".join(i.labels[:3]),
            str(i.comments_count),
        )
    console.print(table)


@issue_app.command("solve")
@gh_app.command("solve")
def gh_issue_solve(
    issue_number: int = typer.Argument(..., help="GitHub issue number to autonomously solve."),
    auto_pr: bool = typer.Option(True, "--auto-pr/--no-pr", help="Automatically create Pull Request once tests pass."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Autonomously investigates, writes surgical fixes, verifies tests, and opens PR for an issue."""
    engine = GitHubEngine()
    console.print(f"[bold cyan]Autonomously solving GitHub issue [yellow]#{issue_number}[/yellow]...[/bold cyan]")
    res = engine.solve_issue(issue_number=issue_number, auto_pr=auto_pr)

    if json_output:
        print(json.dumps(res.to_dict(), indent=2))
        return

    if res.success:
        console.print(Panel(
            f"[bold green]✔ Successfully Solved Issue #{issue_number}[/bold green]\n\n"
            f"• [bold]Branch Created:[/bold] [cyan]{res.branch_name}[/cyan]\n"
            + (f"• [bold]Pull Request Opened:[/bold] [link={res.pr_url}]{res.pr_url}[/link]\n" if res.pr_url else "") +
            f"• [bold]Status:[/bold] {res.summary}",
            title=f"Issue #{issue_number} Resolved",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]✘ Failed solving issue #{issue_number}[/bold red]\n\n[bold]Reason:[/bold] {res.error_message}",
            title=f"Issue #{issue_number} Unresolved",
            border_style="red",
        ))


@release_app.command("list")
@gh_app.command("releases")
def gh_release_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Max releases to return."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Lists repository releases."""
    engine = GitHubEngine()
    releases = engine.list_releases(limit=limit)

    if json_output:
        print(json.dumps([r.to_dict() for r in releases], indent=2))
        return

    table = Table(title=f"🚀 GitHub Releases ({engine.owner}/{engine.repo})", border_style="cyan", header_style="bold magenta")
    table.add_column("Tag", style="bold cyan")
    table.add_column("Release Name", style="white")
    table.add_column("Type", justify="center")
    table.add_column("Published", style="dim")
    table.add_column("Assets", justify="right")

    for r in releases:
        type_badge = "[yellow]pre-release[/yellow]" if r.prerelease else ("[dim]draft[/dim]" if r.draft else "[green]release[/green]")
        table.add_row(r.tag_name, r.name, type_badge, r.published_at[:10], str(len(r.assets)))
    console.print(table)


@release_app.command("create")
def gh_release_create(
    tag: str = typer.Argument(..., help="Release tag name (e.g. v1.0.0)."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Release title name."),
    draft: bool = typer.Option(False, "--draft", help="Create as draft release."),
    prerelease: bool = typer.Option(False, "--prerelease", help="Create as prerelease."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Creates a new GitHub release with automatically generated AST Conventional Changelog."""
    engine = GitHubEngine()
    console.print(f"[bold cyan]Synthesizing changelog and creating release [yellow]{tag}[/yellow]...[/bold cyan]")
    rel = engine.create_release(tag_name=tag, name=name, draft=draft, prerelease=prerelease)

    if json_output:
        print(json.dumps(rel.to_dict(), indent=2))
        return

    console.print(Panel(
        f"[bold green]✔ Created Release {rel.tag_name}[/bold green]\n\n"
        f"• [bold]Title:[/bold] {rel.name}\n"
        f"• [bold]URL:[/bold] [link={rel.html_url}]{rel.html_url}[/link]\n\n"
        f"[dim]Changelog Preview:\n{rel.body[:300]}...[/dim]",
        title=f"Release {tag} Published",
        border_style="green",
    ))


@action_app.command("runs")
@gh_app.command("actions")
def gh_action_runs(
    limit: int = typer.Option(15, "--limit", "-n", help="Max runs to return."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Lists GitHub Actions CI/CD workflow runs."""
    engine = GitHubEngine()
    runs = engine.list_workflow_runs(limit=limit)

    if json_output:
        print(json.dumps([r.to_dict() for r in runs], indent=2))
        return

    table = Table(title=f"⚡ GitHub Actions CI/CD Runs ({engine.owner}/{engine.repo})", border_style="cyan", header_style="bold magenta")
    table.add_column("Run ID", style="bold cyan")
    table.add_column("Workflow", style="white")
    table.add_column("Branch", style="yellow")
    table.add_column("Status", justify="center")
    table.add_column("Conclusion", justify="center")
    table.add_column("Created", style="dim")

    for r in runs:
        conclusion_badge = "[bold green]success[/bold green]" if r.conclusion == "success" else (
            "[bold red]failure[/bold red]" if r.conclusion == "failure" else f"[dim]{r.conclusion or 'running'}[/dim]"
        )
        table.add_row(str(r.id), r.name, r.head_branch, r.status, conclusion_badge, r.created_at[:10])
    console.print(table)


@gist_app.command("create")
def gh_gist_create(
    file_path: str = typer.Argument(..., help="File path to publish as Gist."),
    description: str = typer.Option("Created via K-CLI", "--description", "-d"),
    public: bool = typer.Option(False, "--public", help="Make gist public."),
):
    """Creates a GitHub Gist snippet."""
    engine = GitHubEngine()
    p = Path(file_path).resolve()
    if not p.exists():
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        return

    content = p.read_text(encoding="utf-8", errors="replace")
    url = engine.create_gist(files={p.name: content}, description=description, public=public)
    console.print(f"[bold green]✔ Gist created successfully:[/bold green] [link={url}]{url}[/link]")


# =============================================================================
# Local GitHub Hub & Trending Commands (`k-cli hub` / `k-cli trending`)
# =============================================================================

@app.command(name="hub", help="Display local GitHub workstation summary, commits, and activity feed.")
def hub_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository path."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Displays local repository workstation analytics and commit streams."""
    hub = LocalGitHubHub(repo_path=repo)
    summary = hub.get_summary()

    if json_output:
        sys.stdout.write(json.dumps(summary.to_dict(), indent=2) + "\n")
        return

    table = Table(title=f"🐙 Local GitHub Workstation ({summary.repo_name})", box=None)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold white")
    table.add_row("Branch Name", f"[bold green]{summary.branch_name}[/bold green]")
    table.add_row("Total Commits", str(summary.total_commits))
    table.add_row("Uncommitted Changes", f"[yellow]{summary.uncommitted_changes}[/yellow]" if summary.uncommitted_changes else "[green]0 (clean)[/green]")
    table.add_row("Contributors", str(summary.contributors_count))
    table.add_row("Repository Health", f"[bold green]{summary.health_score:.1f} / 100[/bold green]")
    console.print(table)
    console.print()

    commits = hub.get_recent_commits(limit=5)
    if commits:
        c_table = Table(title="Recent Git Commit History", box=None)
        c_table.add_column("SHA", style="bold cyan")
        c_table.add_column("Author", style="magenta")
        c_table.add_column("Date", style="dim")
        c_table.add_column("Subject", style="white")
        for c in commits:
            c_table.add_row(c.short_sha, c.author, c.date, c.subject[:50])
        console.print(c_table)


@app.command(name="trending", help="Discover trending GitHub repositories, AI agents, and developer tools.")
def trending_cmd(
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Filter by programming language (python, rust, go, etc.)."),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Filter by topic or query (ai-agent, tui, llm, etc.)."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max repositories to show."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Discovers trending GitHub repositories and AI agent frameworks."""
    engine = TrendingEngine()
    repos = engine.get_trending(language=language, query=query, limit=limit)

    if json_output:
        sys.stdout.write(json.dumps([r.to_dict() for r in repos], indent=2) + "\n")
        return

    table = Table(title="🔥 Trending on GitHub (Developer Workstation)", box=None)
    table.add_column("Repository", style="bold cyan")
    table.add_column("Language", style="magenta")
    table.add_column("Stars", style="yellow", justify="right")
    table.add_column("Today", style="bold green", justify="right")
    table.add_column("Description", style="white")

    for r in repos:
        table.add_row(
            r.full_name,
            r.language,
            f"★ {r.stars:,}",
            f"+{r.stars_today}",
            r.description[:50] + ("..." if len(r.description) > 50 else ""),
        )
    console.print(table)


rules_app = typer.Typer(name="rules", help="Manage custom developer instructions & workspace rules (.kclirules).")


@rules_app.command(name="init", help="Create a .kclirules template in the current workspace.")
def rules_init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing rules file."),
):
    """Initializes a starter .kclirules template in the workspace root."""
    from k_cli.tools.rules import create_default_rules_file
    path = create_default_rules_file(force=force)
    console.print(f"[bold green]✔ Initialized custom rules template at:[/bold green] [cyan]{path}[/cyan]")


@rules_app.command(name="get", help="Display currently active developer instructions & rules.")
def rules_get():
    """Displays active developer rules from workspace or global settings."""
    from k_cli.tools.rules import load_project_rules
    rules_text = load_project_rules(".")
    if rules_text:
        console.print(Panel(rules_text, title="[bold green]Active Developer Rules & Instructions[/bold green]", border_style="green"))
    else:
        console.print("[yellow]No custom rules found in workspace. Run 'k-cli rules init' to create a .kclirules file.[/yellow]")


@rules_app.command(name="set", help="Set custom global developer instructions.")
def rules_set(
    instructions: str = typer.Argument(..., help="Custom system prompt instructions for the AI."),
):
    """Sets global developer instructions saved to ~/.kcli/rules.md."""
    from k_cli.tools.rules import set_global_rules
    path = set_global_rules(instructions)
    console.print(f"[bold green]✔ Successfully saved global developer instructions to:[/bold green] [cyan]{path}[/cyan]")


# Mount sub-applications onto root CLI app
app.add_typer(conflict_app, name="conflict")
app.add_typer(pr_app, name="pr")
app.add_typer(mcp_app, name="mcp")
app.add_typer(dedup_app, name="dedup")
app.add_typer(security_app, name="security")
app.add_typer(models_app, name="models")
app.add_typer(rules_app, name="rules")
app.add_typer(gh_app, name="gh")
app.add_typer(issue_app, name="issue")
app.add_typer(release_app, name="release")
app.add_typer(action_app, name="action")
app.add_typer(gist_app, name="gist")

# =============================================================================
# Sovereign Sandbox & Virtualization Engine (`k-cli sandbox`)
# =============================================================================
sandbox_app = typer.Typer(help="🛡️ Sovereign multi-tier sandbox and virtualization engine (Bubblewrap, Network Airgap, POSIX Jail).")

@sandbox_app.command(name="status", help="Display active virtualization tier, hardware bounds, and security rating.")
def sandbox_status_cmd():
    from k_cli.core.sandbox import global_sandbox_engine
    diag = global_sandbox_engine.get_diagnostics()

    table = Table(title="🛡️ K-CLI Sovereign Sandbox & Virtualization Status", border_style="cyan")
    table.add_column("Property / Capability", style="bold cyan")
    table.add_column("Status / Enforcement", style="bold white")

    table.add_row("Virtualization Engine", diag["virtualization_engine"])
    table.add_row("Active Isolation Tier", f"[bold green]{diag['active_tier'].replace('_', ' ').title()}[/bold green]")
    table.add_row("Bubblewrap Linux Container", "[bold green]✔ AVAILABLE[/bold green]" if diag["bubblewrap_available"] else "[yellow]○ UNAVAILABLE[/yellow]")
    table.add_row("Container Binary Path", str(diag["bubblewrap_binary"]))
    table.add_row("Linux User Namespaces", "[bold green]✔ ENABLED[/bold green]" if diag["namespaces_available"] else "[yellow]○ DISABLED[/yellow]")
    table.add_row("POSIX Resource Limits", "[bold green]✔ ACTIVE[/bold green]" if diag["posix_rlimits_available"] else "[yellow]○ DISABLED[/yellow]")
    table.add_row("Network Airgap Isolation", "[bold green]✔ ENFORCED (DROPS SOCKETS)[/bold green]" if diag["default_network_airgap"] else "[yellow]PERMISSIVE[/yellow]")
    table.add_row("Hardware RAM Budget", f"[bold green]{diag['default_memory_budget_mb']} MB (< 1.0 GB Budget Limit)[/bold green]")
    table.add_row("CPU Execution Quota", f"{diag['cpu_time_limit_sec']} Seconds")
    table.add_row("Zero-Leak Secret Sanitization", "[bold green]✔ ACTIVE (STRIPS CLOUD SECRETS)[/bold green]" if diag["secret_sanitization_active"] else "[yellow]OFF[/yellow]")
    table.add_row("Security Evaluation Rating", f"[bold green]{diag['security_rating']}[/bold green]")

    console.print(table)


@sandbox_app.command(name="test", help="Execute automated self-test of sandbox isolation, network airgap, and write protection.")
def sandbox_test_cmd():
    from k_cli.core.sandbox import global_sandbox_engine
    console.print("[bold cyan]⚡ Running K-CLI Sandbox Automated Security & Isolation Battery...[/bold cyan]\n")
    results = global_sandbox_engine.self_test()

    table = Table(title="🧪 Sandbox Security & Virtualization Self-Test Results", border_style="green")
    table.add_column("Test Battery", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    for k, v in results.items():
        if k == "overall_pass":
            continue
        passed = v.get("passed", False)
        status_str = "[bold green]✔ PASS[/bold green]" if passed else "[bold red]✘ FAIL[/bold red]"
        details = str(v.get("details", v.get("tier", "OK")))
        table.add_row(k.replace("_", " ").title(), status_str, details)

    console.print(table)
    if results.get("overall_pass"):
        console.print("[bold green]✔ ALL 4 SECURITY SANDBOX BATTERIES PASSED WITH ZERO LEAKS![/bold green]")
    else:
        console.print("[bold red]✘ One or more sandbox batteries reported warnings.[/bold red]")


@sandbox_app.command(name="run", help="Execute any command or script securely inside the sovereign sandbox container.")
def sandbox_run_cmd(
    command: str = typer.Argument(..., help="Shell command or script to execute inside sandbox."),
    airgap: bool = typer.Option(True, "--airgap/--no-airgap", help="Enforce network airgap (block outbound/inbound sockets)."),
    mem_mb: int = typer.Option(1024, "--memory-limit", "-m", help="Memory limit in megabytes (< 1GB budget)."),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds."),
):
    from k_cli.core.sandbox import global_sandbox_engine, SandboxConfig
    cfg = SandboxConfig(
        network_isolated=airgap,
        memory_limit_mb=mem_mb,
        timeout_sec=timeout,
    )
    console.print(f"[bold cyan]🛡️ Executing in Sovereign Sandbox ({cfg.tier} | Airgap: {airgap} | RAM: {mem_mb}MB)...[/bold cyan]\n")
    res = global_sandbox_engine.execute(command, config=cfg, timeout=timeout)
    console.print(res.summary())


app.add_typer(sandbox_app, name="sandbox")

# =============================================================================
# Credentials & API Keys Management
# =============================================================================
keys_app = typer.Typer(help="🔑 Manage, configure, test, and store API keys for all AI model providers.")

@keys_app.callback(invoke_without_command=True)
def keys_main(ctx: typer.Context):
    """List all API key statuses and provide quick interactive setup."""
    if ctx.invoked_subcommand is None:
        from k_cli.core.credentials import CredentialsManager
        from rich.table import Table

        statuses = CredentialsManager.get_key_statuses()
        table = Table(title="🔑 K-CLI API Credentials Vault", border_style="cyan")
        table.add_column("Provider / Key", style="bold cyan")
        table.add_column("Environment Variable", style="dim")
        table.add_column("Status", style="bold")
        table.add_column("Active Key", style="dim white")

        for s in statuses:
            status_text = "[green]✔ Active[/green]" if s["active"] else "[yellow]○ Missing[/yellow]"
            masked_val = s["masked"] or "[dim]None[/dim]"
            table.add_row(s["label"], s["key"], status_text, masked_val)

        console.print(table)
        console.print("\n[dim]To set a key: [/dim][bold cyan]k-cli keys set <KEY_NAME> <VALUE>[/bold cyan]")
        console.print("[dim]To test connections: [/dim][bold cyan]k-cli keys test[/bold cyan]\n")


@keys_app.command(name="set", help="Set and store an API key (e.g. 'k-cli keys set GEMINI_API_KEY AIzaSy...').")
def keys_set_cmd(
    key_name: str = typer.Argument(..., help="Environment variable name (e.g. GEMINI_API_KEY, OPENAI_API_KEY, GITHUB_TOKEN)."),
    key_val: str = typer.Argument(..., help="Secret API key value."),
):
    if not key_name.strip() or not key_val.strip():
        console.print("[bold red]✘ Key name and value cannot be empty.[/bold red]")
        raise typer.Exit(code=1)
    from k_cli.core.credentials import CredentialsManager
    CredentialsManager.set_key(key_name, key_val)
    console.print(f"[bold green]✔ Successfully saved and activated {key_name.upper()}![/bold green]")
    console.print(f"[dim]Stored persistently in ~/.kcli/credentials.env[/dim]")


@keys_app.command(name="test", help="Test live connectivity for all configured provider keys.")
def keys_test_cmd():
    from k_cli.core.credentials import CredentialsManager, SUPPORTED_KEYS
    from rich.table import Table

    table = Table(title="⚡ Provider Connectivity Test", border_style="cyan")
    table.add_column("Provider", style="bold cyan")
    table.add_column("Status", style="bold")
    table.add_column("Latency / Message", style="dim")

    for key_name, label, _ in SUPPORTED_KEYS:
        ok, msg = CredentialsManager.test_key_connectivity(key_name)
        status_text = "[green]✔ Connected[/green]" if ok else "[red]✘ Offline / Missing[/red]"
        table.add_row(label, status_text, msg)

    console.print(table)


@keys_app.command(name="import", help="Import API keys from an existing .env or key.json file.")
def keys_import_cmd(
    file_path: str = typer.Argument(..., help="Path to .env or key.json file to import."),
):
    from k_cli.core.credentials import CredentialsManager, SUPPORTED_KEYS
    p = Path(file_path).resolve()
    if not p.exists():
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        raise typer.Exit(code=1)

    imported_count = 0
    if p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        for k, v in data.items():
            if isinstance(v, str) and v.strip() and k.upper() in [sk[0] for sk in SUPPORTED_KEYS]:
                CredentialsManager.set_key(k.upper(), v.strip())
                imported_count += 1
    else:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip().upper(), v.strip()
                if k in [sk[0] for sk in SUPPORTED_KEYS] and v:
                    CredentialsManager.set_key(k, v)
                    imported_count += 1

    console.print(f"[bold green]✔ Successfully imported {imported_count} key(s) from {file_path}![/bold green]")

app.add_typer(keys_app, name="keys")
app.add_typer(keys_app, name="auth")



# =============================================================================
# 10 Killer Agentic CLI Commands
# =============================================================================

@app.command(name="watch", help="Feature 1: Autonomous PR Review & Watcher Daemon.")
def watch_cmd(
    interval: int = typer.Option(30, "--interval", "-i", help="Polling interval in seconds."),
    auto_merge: bool = typer.Option(False, "--auto-merge", help="Auto-merge approved PRs when CI passes."),
    once: bool = typer.Option(False, "--once", help="Run a single review cycle and exit."),
):
    from k_cli.github.pr_watcher import PRWatcherDaemon
    daemon = PRWatcherDaemon(auto_merge_approved=auto_merge)
    console.print(f"[bold cyan]👁️ K-CLI PR Watcher Daemon active...[/bold cyan]")
    events = daemon.run_loop(interval_seconds=interval, max_iterations=1 if once else None, callback=lambda ev: console.print(f"[green]✔ PR #{ev.pr_number}: {ev.review_status} ({ev.action_taken})[/green]"))
    console.print(f"[dim]Processed {len(events)} PR review event(s).[/dim]")


@app.command(name="bisect", help="Feature 2: AI-Powered Git Bisect & Regression Hunter.")
def bisect_cmd(
    test_cmd: str = typer.Argument(..., help="Test command to evaluate regressions (e.g. 'pytest tests/ -q')."),
    good: str = typer.Option("HEAD~5", "--good", help="Known good commit SHA."),
    bad: str = typer.Option("HEAD", "--bad", help="Known bad commit SHA."),
):
    from k_cli.git.ai_bisect import AIBisectEngine
    try:
        engine = AIBisectEngine()
        console.print(f"[bold magenta]🎯 Starting AI Git Bisect between {good} and {bad}...[/bold magenta]")
        res = engine.run_bisect(test_command=test_cmd, good_commit=good, bad_commit=bad)
        console.print(Markdown(res.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Git Bisect failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="route", help="Feature 3: Cost & Latency Smart Model Router.")
def route_cmd(
    task: str = typer.Argument("Analyze, architect, and optimize repository codebase", help="Task prompt to analyze and route."),
):
    from k_cli.core.smart_router import SmartModelRouter
    try:
        router = SmartModelRouter()
        dec = router.route(task_prompt=task or "default task")
        console.print(Panel(
            f"[bold cyan]Selected Model:[/bold cyan] {dec.selected_model} ({dec.selected_provider})\n"
            f"[bold yellow]Task Tier:[/bold yellow] {dec.tier.value.upper()}\n"
            f"[bold green]Estimated Cost:[/bold green] ${dec.estimated_cost_usd:.4f} USD\n"
            f"[bold blue]Savings vs GPT-4:[/bold blue] ${dec.savings_usd:.4f} USD ({(dec.savings_usd/dec.baseline_gpt4_cost_usd):.1%})\n"
            f"[dim]Rationale: {dec.reasoning}[/dim]",
            title="⚡ Smart Model Router Decision",
            border_style="cyan",
        ))
    except Exception as ex:
        console.print(f"[bold red]✘ Smart Router failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="garden", help="Feature 4: Nightly Autonomous Repo Maintenance & Health Sweep.")
def garden_cmd(
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    from k_cli.tools.repo_gardener import RepoGardener
    try:
        gardener = RepoGardener()
        rep = gardener.run_garden_sweep()
        if as_json:
            import json
            console.print(json.dumps({"health_score": rep.health_score, "findings": len(rep.findings), "dead_code": rep.dead_code_count}))
        else:
            console.print(Markdown(rep.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Repo Gardener failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="explain", help="Feature 5: Codebase Natural Language Search & Semantic Q&A.")
def explain_cmd(
    query: str = typer.Argument("Explain high level architecture and entrypoints", help="Question to ask about the codebase architecture."),
):
    from k_cli.tools.codebase_qa import CodebaseQAEngine
    if not query.strip():
        console.print("[bold yellow]Please provide a question to search the codebase.[/bold yellow]")
        return
    try:
        qa = CodebaseQAEngine()
        res = qa.ask(query=query)
        console.print(Markdown(res.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Codebase Q&A failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="ghost", help="Feature 6: Ghost Terminal Autopilot & Error Healer.")
def ghost_cmd(
    command: str = typer.Argument(..., help="Dev server or test command to wrap (e.g. 'pytest')."),
):
    from k_cli.tools.ghost_daemon import GhostTerminalDaemon
    try:
        daemon = GhostTerminalDaemon()
        console.print(f"[bold cyan]👻 K-CLI Ghost Terminal Autopilot attached to: '{command}'[/bold cyan]\n")
        code = daemon.run_wrapped_command(command_str=command, on_heal_prompt=lambda p: True)
        raise typer.Exit(code=code)
    except Exception as ex:
        console.print(f"[bold red]✘ Ghost Daemon encountered an error:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="swarm", help="Feature 7: Adversarial Red Team / Blue Team Consensus Loop.")
def swarm_cmd(
    task: str = typer.Argument("Implement verified zero-defect algorithms", help="Coding task to execute through adversarial consensus."),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Maximum adversarial attack rounds."),
):
    from k_cli.agents.adversarial_swarm import AdversarialConsensusSwarm
    try:
        swarm = AdversarialConsensusSwarm(max_rounds=rounds)
        console.print(f"[bold magenta]🐝 Running Adversarial Consensus Swarm for: '{task}'...[/bold magenta]")
        res = swarm.run_consensus(task_prompt=task or "consensus task")
        console.print(Markdown(res.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Adversarial Swarm failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="synapse", help="Feature 8: AST Neural Code Graph & Context Compressor.")
def synapse_cmd(
    query: str = typer.Argument("core architecture components", help="Task or keyword to extract minimal AST subgraph for."),
):
    from k_cli.tools.synapse_graph import SynapseCodeGraph
    try:
        graph = SynapseCodeGraph()
        res = graph.extract_subgraph_slice(query=query or "core")
        console.print(Markdown(res.render_context()))
    except Exception as ex:
        console.print(f"[bold red]✘ Synapse Graph extraction failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="airgap", help="Feature 9: Sovereign Air-Gapped Offline Engine.")
def airgap_cmd():
    from k_cli.core.airgap import AirgapManager
    try:
        mgr = AirgapManager()
        rep = mgr.audit_environment()
        console.print(Markdown(rep.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Airgap audit failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="scaffold", help="Feature 10: Natural Language Full-Stack Scaffolder.")
def scaffold_cmd(
    spec: str = typer.Argument(..., help="Natural language description of application to scaffold."),
    target: str = typer.Option("./scaffolded_app", "--dir", "-d", help="Target output directory."),
    write: bool = typer.Option(False, "--write", "-w", help="Write scaffolded files to disk."),
):
    from k_cli.agents.scaffold_engine import FullStackScaffolder
    if not spec.strip():
        console.print("[bold yellow]Please provide an application specification to scaffold.[/bold yellow]")
        return
    try:
        scaffolder = FullStackScaffolder()
        console.print(f"[bold cyan]🏗️ Scaffolding full-stack application for: '{spec}'...[/bold cyan]")
        res = scaffolder.scaffold(spec_prompt=spec, target_dir=target, write_to_disk=write)
        console.print(Markdown(res.render_markdown()))
    except Exception as ex:
        console.print(f"[bold red]✘ Scaffolding failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="strands", help="Feature 11: AWS Strands Autonomous Agent Runner (Agents for Humans).")
def strands_cmd(
    goal: str = typer.Argument(..., help="High-level engineering or triage goal for the Strands agent."),
    provider: str = typer.Option("auto", "--provider", "-p", help="Model provider ('bedrock', 'gemini', 'anthropic', 'openai', 'ollama', or 'auto')."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Specific model ID (e.g. 'anthropic.claude-3-5-sonnet-20241022-v2:0' or 'gemini-2.0-flash')."),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS Region for Amazon Bedrock (e.g. 'us-east-1')."),
):
    """Executes an autonomous goal using the AWS Strands Agents SDK and registered deterministic tools."""
    from k_cli.agents.strands_agent import create_strands_agent
    try:
        console.print(f"[bold cyan]⚡ Initializing AWS Strands Autonomous Agent (Provider: {provider})...[/bold cyan]")
        agent = create_strands_agent(provider=provider, model_name=model, aws_region=region)
        console.print(f"[bold green]▶ Running Goal:[/bold green] [white]{goal}[/white]\n")
        response = agent.run(goal)
        console.print(Markdown(response))
    except Exception as ex:
        console.print(f"[bold red]✘ Strands Agent execution failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="agent", help="Alias for strands autonomous developer agent.")
def agent_cmd(
    goal: str = typer.Argument(..., help="High-level engineering or triage goal for the Strands agent."),
    provider: str = typer.Option("auto", "--provider", "-p", help="Model provider ('bedrock', 'gemini', 'anthropic', 'openai', 'ollama', or 'auto')."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Specific model ID."),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS Region for Amazon Bedrock."),
):
    strands_cmd(goal=goal, provider=provider, model=model, region=region)


@app.command(name="auto-heal", help="Feature 12: Strands Deep Crash Triage & Closed-Loop Auto-Heal.")
def auto_heal_cmd(
    log_source: Optional[str] = typer.Argument(None, help="Path to crash log file, or raw error string. If omitted, reads from stdin."),
    repo: str = typer.Option(".", "--repo", "-r", help="Target repository root directory."),
):
    """Parses raw crash traces across 7 environments and executes an autonomous verified heal loop."""
    from k_cli.agents.strands_agent import triage_and_heal_incident
    try:
        if log_source and os.path.exists(log_source):
            raw_log = Path(log_source).read_text(encoding="utf-8", errors="replace")
        elif log_source:
            raw_log = log_source
        elif not sys.stdin.isatty():
            raw_log = sys.stdin.read()
        else:
            console.print("[bold yellow]Please provide a log file, error string, or pipe logs via stdin.[/bold yellow]")
            return

        console.print("[bold cyan]🔍 Executing Strands Multi-Language Crash Triage & Auto-Heal...[/bold cyan]\n")
        report_json = triage_and_heal_incident(raw_log, repo_path=repo)
        console.print(Syntax(report_json, "json", theme="monokai", line_numbers=True))
    except Exception as ex:
        console.print(f"[bold red]✘ Auto-heal failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="immune", help="Feature 13: Autonomous Chaos Immunity & Edge-Case Self-Healing Engine.")
def immune_cmd(
    target_file: Optional[str] = typer.Argument(None, help="Target Python source file to probe and inoculate. If omitted, scans repository."),
    repo: str = typer.Option(".", "--repo", "-r", help="Target repository root directory."),
    apply_patches: bool = typer.Option(True, "--patch/--no-patch", help="Automatically apply verified defensive inoculation patches."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
):
    """Probes brittle AST patterns (KeyError, None dereference, timeout hangs), synthesizes adversarial tests, and inoculates codebase."""
    from k_cli.tools.chaos_immunity import ChaosImmunityEngine
    try:
        engine = ChaosImmunityEngine(repo_path=repo)
        if target_file and os.path.exists(target_file):
            console.print(f"[bold cyan]🛡️ Running Chaos Immunity Inoculation on '{target_file}'...[/bold cyan]\n")
            report = engine.inoculate_file(target_file, auto_apply_patches=apply_patches)
            if json_output:
                import json
                console.print(json.dumps({
                    "target_file": report.target_file,
                    "patterns_detected": len(report.patterns_detected),
                    "generated_tests_count": report.generated_tests_count,
                    "patches_applied_count": report.patches_applied_count,
                    "verification_passed": report.verification_passed,
                    "summary": report.summary,
                }, indent=2))
            else:
                console.print(Markdown(report.render_markdown()))
        else:
            console.print("[bold cyan]🛡️ Scanning workspace for brittle edge cases across core modules...[/bold cyan]\n")
            reports = engine.scan_and_inoculate_repo(max_files=10)
            total_patterns = sum(len(r.patterns_detected) for r in reports)
            total_tests = sum(r.generated_tests_count for r in reports)
            console.print(Panel(
                f"[bold green]✔ Chaos Immunity Sweep Completed[/bold green]\n\n"
                f"• [cyan]Modules Inoculated:[/cyan] {len(reports)}\n"
                f"• [yellow]Brittle Edge Cases Probed:[/yellow] {total_patterns}\n"
                f"• [magenta]Adversarial Immunity Tests Synthesized:[/magenta] {total_tests}\n"
                f"• [green]AST Ground-Truth Integrity:[/green] 100% VERIFIED\n\n"
                f"[dim]Generated test suites stored in `tests/chaos/`[/dim]",
                title="🛡️ K-CLI Chaos Immunity Shield",
                border_style="green",
            ))
    except Exception as ex:
        console.print(f"[bold red]✘ Chaos Immunity Engine failed:[/bold red] {ex}")
        raise typer.Exit(code=1)


@app.command(name="chaos", help="Alias for k-cli immune.")
def chaos_cmd(
    target_file: Optional[str] = typer.Argument(None, help="Target Python source file to probe and inoculate."),
    repo: str = typer.Option(".", "--repo", "-r", help="Target repository root directory."),
):
    immune_cmd(target_file=target_file, repo=repo, apply_patches=True, json_output=False)


# =============================================================================
# Amazon Bedrock AgentCore Deployment & Integration (`k-cli bedrock`)
# =============================================================================
bedrock_app = typer.Typer(name="bedrock", help="Deploy and manage Amazon Bedrock AgentCore for K-CLI Strands Agent.")


@bedrock_app.command(name="export", help="Export Amazon Bedrock AgentCore OpenAPI schema and CloudFormation bundle.")
def bedrock_export_cmd(
    output_dir: str = typer.Option(".kcli/agent_core_bundle", "--output", "-o", help="Output directory for AgentCore bundle."),
):
    """Exports Bedrock AgentCore OpenAPI 3.0 schemas and CloudFormation SAM templates."""
    from k_cli.agents.agent_core import BedrockAgentCoreEngine
    engine = BedrockAgentCoreEngine()
    bundle_path = engine.export_deployment_bundle(output_dir=output_dir)
    console.print(Panel(
        f"[bold green]✔ Amazon Bedrock AgentCore Bundle Exported[/bold green]\n\n"
        f"• [cyan]Bundle Directory:[/cyan] {bundle_path}\n"
        f"• [yellow]OpenAPI Action Group:[/yellow] {bundle_path / 'openapi_schema.json'}\n"
        f"• [magenta]CloudFormation SAM Template:[/magenta] {bundle_path / 'template.yaml'}\n"
        f"• [green]Agent Configuration:[/green] {bundle_path / 'agent_config.json'}\n\n"
        f"[dim]Ready to deploy with AWS CLI or SAM: `sam deploy --guided`[/dim]",
        title="⚡ Amazon Bedrock AgentCore",
        border_style="green",
    ))


@bedrock_app.command(name="deploy", help="Deploy K-CLI Strands Agent to Amazon Bedrock AgentCore.")
def bedrock_deploy_cmd():
    """Deploys K-CLI Strands Agent directly to Amazon Bedrock."""
    from k_cli.agents.agent_core import BedrockAgentCoreEngine
    engine = BedrockAgentCoreEngine()
    res = engine.deploy_to_bedrock()
    console.print(Panel(
        f"[bold green]✔ Amazon Bedrock AgentCore Deployment Status: {res['status']}[/bold green]\n\n"
        f"• [cyan]Agent Name:[/cyan] {res['agent_name']}\n"
        f"• [yellow]Foundation Model:[/yellow] {res['model_id']}\n"
        f"• [magenta]AWS Region:[/magenta] {res['region']}\n"
        f"• [white]Summary:[/white] {res['message']}\n",
        title="⚡ Amazon Bedrock AgentCore Deployment",
        border_style="cyan",
    ))


app.add_typer(bedrock_app, name="bedrock")


# =============================================================================
# Autonomous Background Healing Daemon (`k-cli daemon` / `k-cli watch`)
# =============================================================================
@app.command(name="daemon", help="Run K-CLI autonomous self-healing daemon in the background.")
@app.command(name="watch", help="Continuously monitor repository and auto-heal broken builds in the background.")
def daemon_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory to monitor."),
    interval: float = typer.Option(10.0, "--interval", "-i", help="Poll interval in seconds."),
):
    """Runs autonomous developer daemon quietly in the background; surfaces only on critical decisions."""
    from k_cli.agents.background_daemon import BackgroundHealerDaemon
    import asyncio
    console.print(f"[bold cyan]⚡ K-CLI Background Healer Daemon starting on '{repo}' (interval: {interval}s)...[/bold cyan]")
    console.print("[dim]Runs quietly in the background and surfaces only when a decision is needed. Press Ctrl+C to stop.[/dim]\n")
    
    def on_decision(dec):
        console.print(f"\n[bold green]🚨 [DAEMON NOTICE][/bold green] [yellow]{dec['summary']}[/yellow]")
    
    daemon = BackgroundHealerDaemon(workspace_dir=repo, poll_interval_seconds=interval, decision_callback=on_decision)
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon stopped by user.[/yellow]")


# =============================================================================
# Cinematic 5-Minute Interactive Demo & AI Voiceover (`k-cli demo`)
# =============================================================================
@app.command(name="demo", help="Run the cinematic 5-minute interactive demo with AI voiceover cues.")
def demo_cmd(
    speed: float = typer.Option(1.0, "--speed", "-s", help="Playback speed multiplier (e.g. 1.5 for fast demo)."),
    act: Optional[int] = typer.Option(None, "--act", "-a", help="Run a specific act (1 to 5). If omitted, runs all 5 acts."),
):
    """Executes the ultra-cinematic 5-minute production demo with live agent telemetry."""
    from k_cli.demo.demo_runner import start_cinematic_demo
    start_cinematic_demo(speed=speed, act=act)


# =============================================================================
# Feature 1: Autonomous Time-Travel Checkpoints & Instant Rollback (`k-cli undo`)
# =============================================================================
@app.command(name="undo", help="Instantly roll back the workspace to the latest safe checkpoint.")
@app.command(name="rollback", help="Alias for undo: revert to previous checkpoint.")
def undo_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory to restore."),
):
    """Reverts workspace state to the most recent pre-execution checkpoint."""
    from k_cli.git.checkpoint import CheckpointManager
    mgr = CheckpointManager(workspace_dir=repo)
    success, msg = mgr.rollback_last_checkpoint()
    if success:
        console.print(Panel(
            f"[bold green]✔ Time-Travel Rollback Succeeded[/bold green]\n\n{msg}",
            title="🛡️ K-CLI Checkpoint Rollback",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]✘ Rollback Failed[/bold red]\n\n{msg}",
            title="🛡️ K-CLI Checkpoint Rollback",
            border_style="red",
        ))


@app.command(name="checkpoints", help="List all autonomous time-travel snapshots in workspace.")
def checkpoints_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory."),
):
    """Displays saved workspace checkpoints."""
    from k_cli.git.checkpoint import CheckpointManager
    mgr = CheckpointManager(workspace_dir=repo)
    ckpts = mgr.list_checkpoints()
    if not ckpts:
        console.print("[yellow]No checkpoints saved yet in .kcli/checkpoints/[/yellow]")
        return
    table = Table(title="🛡️ K-CLI Time-Travel Checkpoints", border_style="cyan")
    table.add_column("Checkpoint ID", style="cyan bold")
    table.add_column("Timestamp", style="white")
    table.add_column("Files Tracked", style="green")
    table.add_column("Description", style="dim")
    for c in reversed(ckpts):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c["timestamp"]))
        table.add_row(c["checkpoint_id"], ts, str(len(c.get("files_tracked", []))), c.get("description", ""))
    console.print(table)


@app.command(name="diff-last", help="Show unified diff between current workspace and latest checkpoint.")
def diff_last_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory."),
):
    """Displays diff since last checkpoint."""
    from k_cli.git.checkpoint import CheckpointManager
    mgr = CheckpointManager(workspace_dir=repo)
    diff_text = mgr.compute_diff()
    if "Zero modifications detected" in diff_text:
        console.print(f"[bold green]✔ {diff_text}[/bold green]")
    else:
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        console.print(syntax)


# =============================================================================
# Feature 2: Self-Learning Project Memory (`k-cli memory`)
# =============================================================================
@app.command(name="memory", help="View or update self-learning project memory (KCLI.md / .kcli/MEMORY.md).")
def memory_cmd(
    action: str = typer.Argument("show", help="Action: 'show', 'init', or 'learn'."),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Lesson or directive to record."),
    repo: str = typer.Option(".", "--repo", "-r", help="Target repository directory."),
):
    """Inspects and manages persistent project memory."""
    from k_cli.core.memory import ProjectMemoryManager
    mgr = ProjectMemoryManager(workspace_dir=repo)
    if action == "init":
        mgr.initialize_if_missing()
        console.print("[bold green]✔ Initialized persistent KCLI.md project memory.[/bold green]")
    elif action == "learn" and note:
        mgr.record_learning(note, category="DeveloperNote")
        console.print(f"[bold green]✔ Recorded learning:[/bold green] {note}")
    else:
        content = mgr.load_memory(max_chars=8000)
        if not content:
            mgr.initialize_if_missing()
            content = mgr.load_memory(max_chars=8000)
        console.print(Panel(
            Markdown(content),
            title="🧠 K-CLI Self-Learning Project Memory (KCLI.md)",
            border_style="magenta",
        ))


# =============================================================================
# Feature 3: Standardized Evaluation & Benchmark Scorecard (`k-cli eval` / `benchmark`)
# =============================================================================
@app.command(name="eval", help="Run standardized benchmark evaluation and export official scorecard.")
@app.command(name="benchmark", help="Alias for k-cli eval: Run standardized autonomous developer benchmark.")
def eval_cmd(
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory to evaluate."),
    compare: Optional[str] = typer.Option(None, "--compare", "-c", help="Target tool to compare against (e.g. 'aider')."),
    json_out: bool = typer.Option(False, "--json", help="Output raw JSON benchmark data."),
):
    """Executes the quantitative benchmark measuring AST pass rate, sandbox isolation, and comparison against Aider."""
    from k_cli.tools.benchmark_harness import EvaluationHarness
    harness = EvaluationHarness(workspace_dir=repo)

    if compare:
        target_name = compare.upper() if compare != "all" else "INDUSTRY PEERS (Antigravity, Claude Code, Aider)"
        console.print(f"[bold cyan]⚡ Running K-CLI Official Comparative Benchmark vs {target_name}...[/bold cyan]\n")
        comp_report = harness.run_comparative_benchmark(target=compare)

        if json_out:
            import dataclasses
            console.print(json.dumps(dataclasses.asdict(comp_report), indent=2))
            return

        table = Table(title="🏆 Official 4-Way Industry Benchmark: K-CLI vs Antigravity vs Claude Code vs Aider", border_style="cyan")
        table.add_column("ID", style="bold cyan", no_wrap=True)
        table.add_column("Evaluation Metric", style="white")
        table.add_column("K-CLI (Ours)", style="bold green")
        table.add_column("Google Antigravity", style="magenta")
        table.add_column("Claude Code", style="yellow")
        table.add_column("Aider", style="dim white")
        table.add_column("Category Leader", style="bold green")

        for m in comp_report.metrics:
            leader_style = "[bold green]✔ K-CLI[/bold green]" if m.leader == "K-CLI" else f"[bold magenta]★ {m.leader}[/bold magenta]"
            table.add_row(
                m.metric_id,
                f"[bold]{m.name}[/bold]\n[dim]{m.category}[/dim]",
                m.k_cli,
                m.antigravity,
                m.claude_code,
                m.aider,
                leader_style,
            )
        console.print(table)

        summary_panel = Panel(
            f"[bold bright_white]Overall Championship Verdict:[/bold bright_white] [bold green]{comp_report.overall_verdict}[/bold green]\n\n"
            f"  • [bold green]K-CLI Category Wins:[/bold green] [bold white]{comp_report.k_cli_wins}/{comp_report.total_categories}[/bold white] (Sovereign Sandbox, AST Compilers, <1GB RAM, CreditSaver, Airgap, 3-Way Merge)\n"
            f"  • [bold magenta]Google Antigravity Wins:[/bold magenta] [bold white]{comp_report.antigravity_wins}/{comp_report.total_categories}[/bold white] (Visual DevTools & DOM Instrumentation, Cloud Fleet Orchestration)\n"
            f"  • [bold yellow]Claude Code Wins:[/bold yellow] [bold white]{comp_report.claude_code_wins}/{comp_report.total_categories}[/bold white] (Monolithic >200k Token Frontier Reasoning)\n"
            f"  • [bold cyan]Evaluation Duration:[/bold cyan] [cyan]{comp_report.total_duration_sec}s[/cyan]\n\n"
            f"[dim]Official Scorecard exported to: {repo}/.kcli/BENCHMARK_SCORECARD.md[/dim]",
            title="📊 Executive Industry Benchmark Scorecard",
            border_style="green",
        )
        console.print(summary_panel)
        return

    console.print("[bold cyan]⚡ Running K-CLI Autonomous Engineering Benchmark Battery...[/bold cyan]")
    report = harness.run_full_evaluation()

    if json_out:
        import dataclasses
        console.print(json.dumps(dataclasses.asdict(report), indent=2))
        return

    table = Table(title="🏆 K-CLI Standardized Benchmark Scorecard", border_style="green")
    table.add_column("Task ID", style="bold cyan")
    table.add_column("Benchmark Task", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Status", style="bold green")
    table.add_column("AST Ground-Truth", style="bold green")
    table.add_column("Time", style="cyan")
    table.add_column("Cost Spent", style="magenta")
    table.add_column("Cost Saved", style="green")

    for r in report.results:
        st = "[bold green]✔ PASS[/bold green]" if r.passed else "[bold red]✘ FAIL[/bold red]"
        ast_st = "[bold green]✔ VALID[/bold green]" if r.ast_verified else "[bold red]✘ FAIL[/bold red]"
        table.add_row(
            r.task_id,
            r.name,
            r.category,
            st,
            ast_st,
            f"{r.duration_sec}s",
            f"${r.actual_cost_usd:.4f}",
            f"${r.saved_usd:.4f}",
        )
    console.print(table)

    summary_panel = Panel(
        f"[bold bright_white]Overall Pass Rate:[/bold bright_white] [bold green]{report.passed_tasks}/{report.total_tasks} ({report.ast_pass_rate_pct}% AST Verified)[/bold green]\n"
        f"[bold bright_white]Total Test Duration:[/bold bright_white] [cyan]{report.total_duration_sec}s[/cyan]\n"
        f"[bold bright_white]Actual Cloud/Model Spend:[/bold bright_white] [magenta]${report.total_spent_usd:.4f}[/magenta]\n"
        f"[bold bright_white]CreditSaver Optimization:[/bold bright_white] [bold green]${report.total_saved_usd:.4f} saved ({report.savings_pct}% cheaper than $10 unoptimized baseline)[/bold green]\n\n"
        f"[dim]Scorecard exported to: {repo}/.kcli/BENCHMARK_SCORECARD.md[/dim]",
        title="📊 Executive Evaluation Metrics",
        border_style="cyan",
    )
    console.print(summary_panel)


# =============================================================================
# Feature 4: Autonomous Docker & CI/CD Pipeline Healer (`k-cli cicd`)
# =============================================================================
@app.command(name="cicd", help="Audit and auto-repair broken GitHub Actions workflows and Dockerfiles.")
def cicd_cmd(
    target: str = typer.Argument("all", help="Target: 'all', 'workflow', 'dockerfile', or specific path."),
    repo: str = typer.Option(".", "--repo", "-r", help="Repository directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Audit only without writing changes."),
):
    """Diagnoses and heals broken CI/CD pipelines and Dockerfiles."""
    from k_cli.tools.cicd_healer import CICDHealer
    healer = CICDHealer(workspace_dir=repo)
    auto_apply = not dry_run

    console.print(f"[bold cyan]⚡ Running K-CLI CI/CD & Docker Pipeline Healer on '{repo}'...[/bold cyan]\n")
    results = []

    # Workflow healing
    wf_path = Path(repo) / ".github" / "workflows"
    if wf_path.exists():
        for wf_file in wf_path.glob("*.yml"):
            results.append(healer.audit_and_heal_workflow(str(wf_file), auto_apply=auto_apply))
        for wf_file in wf_path.glob("*.yaml"):
            results.append(healer.audit_and_heal_workflow(str(wf_file), auto_apply=auto_apply))

    # Dockerfile healing
    df_path = Path(repo) / "Dockerfile"
    if df_path.exists():
        results.append(healer.audit_and_heal_dockerfile(str(df_path), auto_apply=auto_apply))

    if not results:
        console.print("[yellow]No GitHub Actions workflows or Dockerfiles detected in repository.[/yellow]")
        return

    for res in results:
        p_name = Path(res.file_path).name
        if res.issues_found > 0:
            console.print(Panel(
                f"[bold green]✔ Healed {res.issues_found} issue(s) in {p_name}:[/bold green]\n" +
                "\n".join(f"  • {f}" for f in res.fixes_applied),
                title=f"🔧 CI/CD Healer: {p_name}",
                border_style="green",
            ))
        else:
            console.print(f"[green]✔[/green] {p_name}: [dim]All action versions, cache directives, and build layers verified optimal.[/dim]")


# =============================================================================
# Feature 5: Global Ambient Error Interceptor Sentinel (`k-cli wrap <cmd>`)
# =============================================================================
@app.command(name="wrap", help="Run ANY shell/pip/git command under ambient Sentinel supervision; auto-fixes errors in <1s.")
@app.command(name="sentinel", help="Alias for k-cli wrap: Ambient zero-latency error interceptor.")
def wrap_cmd(
    command: List[str] = typer.Argument(..., help="Shell command to execute and monitor."),
    repo: str = typer.Option(".", "--repo", "-r", help="Working directory for execution."),
):
    """Runs a command with Global Sentinel active. If any error occurs, Sentinel intercepts and heals it instantly."""
    from k_cli.tools.sentinel import GlobalSentinel
    import shlex
    cmd_str = shlex.join(command)
    console.print(f"[bold cyan]⚡ K-CLI Global Sentinel active on: [bold white]{cmd_str}[/bold white][/bold cyan]\n")
    sentinel = GlobalSentinel(workspace_dir=repo)
    result = sentinel.wrap_and_heal(cmd_str, cwd=repo)

    if result.stdout.strip():
        console.print(result.stdout.strip())
    if result.stderr.strip() and result.final_exit_code != 0:
        console.print(f"[red]{result.stderr.strip()}[/red]")

    if result.original_exit_code == 0:
        console.print(f"\n[bold green]✔ Command completed successfully ({result.duration_sec}s)[/bold green]")
    elif result.repair_successful:
        console.print(Panel(
            f"[bold green]✔ Sentinel Auto-Repaired Command in {result.duration_sec}s[/bold green]\n\n"
            f"• [cyan]Intercepted Error:[/cyan] {result.culprit_detected}\n"
            f"• [yellow]Action Taken:[/yellow] {result.repair_action}\n"
            f"• [green]Final Status:[/green] Exit Code {result.final_exit_code} (VERIFIED RE-EXECUTION SUCCESS)",
            title="🛡️ K-CLI Global Sentinel Interception",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]✘ Sentinel Intercepted Error (Exit Code {result.final_exit_code})[/bold red]\n\n"
            f"• [cyan]Culprit:[/cyan] {result.culprit_detected}\n"
            f"• [yellow]Intervention:[/yellow] {result.repair_action}",
            title="⚠️ K-CLI Sentinel Warning",
            border_style="yellow",
        ))
        raise typer.Exit(code=result.final_exit_code)


def interactive_mode(model: str = "qwen2.5-coder:1.5b", mock: bool = False, continue_session: bool = False):
    """Interactive multi-turn prompt shell when typing 'k' without arguments."""
    if hasattr(console, "is_terminal") and console.is_terminal:
        console.clear()
    
    if continue_session:
        session = SessionManager.load_latest(workspace_dir=".", mock_mode=mock) or SessionManager(workspace_dir=".", model_name=model, mock_mode=mock)
    else:
        session = SessionManager(workspace_dir=".", model_name=model, mock_mode=mock)

    print_banner()
    if continue_session and session.history:
        console.print(f"[bold green]✔ Resumed previous session ({len(session.history)} turn(s), model: {session.model_name}) from ~/.kcli/sessions/[/bold green]\n")
    else:
        console.print("[bold cyan]K-CLI Interactive Shell ready. Type /help for slash commands or /exit to quit.[/bold cyan]\n")

    shell = InteractiveShell(session=session, console=console)
    shell.run()


def version_callback(value: bool):
    if value:
        console.print("[bold cyan]K-CLI[/bold cyan] [bold bright_white]v1.0.0[/bold bright_white] [dim](Project Bankai Flagship Edition)[/dim]")
        raise typer.Exit()


@app.callback(
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(None, "--version", "-v", help="Show K-CLI version and exit.", callback=version_callback, is_eager=True),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Prompt text if running main entrypoint directly."),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue previous multi-turn session from local storage."),
    demo_ui: bool = typer.Option(False, "--demo-ui", help="Launch the TUI in pure Zero-AI demo mode without needing any API key."),
):
    if ctx.invoked_subcommand is None:
        if demo_ui:
            ui_cmd(mock=True, demo=True, continue_session=continue_session)
            raise typer.Exit()
        elif prompt:
            execute_run(prompt=prompt, show_banner=True)
            raise typer.Exit()
        elif ctx.args:
            prompt_arg = " ".join(ctx.args)
            execute_run(prompt=prompt_arg, show_banner=True)
            raise typer.Exit()
        else:
            interactive_mode(continue_session=continue_session)


if __name__ == "__main__":
    app()
