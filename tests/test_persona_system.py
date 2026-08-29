"""
test_persona_system.py - Unit and Integration Tests for K-CLI Dynamic Persona System

Tests all 6 specialized domain personas:
1. DevOps & SRE Specialist (Docker, Kubernetes, CI/CD, Terraform, Cloud Deployments)
2. Surgical Debugger (Root-cause analysis, minimal SEARCH/REPLACE diffs, zero regression)
3. Systems Architect (C++23, Rust, Linux Kernel, Lock-free concurrency, Big-O proofs)
4. Application Security Engineer (OWASP Top 10, HMAC, Auth middlewares, Constant-time crypto)
5. Frontend & Fullstack Engineer (React, Vite, Next.js, CSS layout, accessibility)
6. Database & Query Optimizer (PostgreSQL, Redis, Spanner, SQL query optimization)
+ Generalist / Fullstack AI Systems Engineer (Default)

Validates PersonaRegistry alias resolution, phase prompt modulation, Orchestrator pipeline integration,
SessionManager /persona command routing, and CLI interaction.
"""

import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from typer.testing import CliRunner

from k_cli.agents.persona import (
    DomainPersona,
    PersonaProfile,
    PersonaRegistry,
    PipelinePhase,
    DEVOPS_PERSONA,
    DEBUGGER_PERSONA,
    SYSTEMS_PERSONA,
    SECURITY_PERSONA,
    FRONTEND_PERSONA,
    DATABASE_PERSONA,
    DEFAULT_PERSONA,
)
from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult, Persona
from k_cli.core.llm_driver import LLMDriver
from k_cli.git.verifier import Verifier
from k_cli.core.session import SessionManager
from k_cli.cli import app, get_persona_color, execute_run


runner = CliRunner()


# ==============================================================================
# 1. Persona Profiles and Prompt Engineering Tests
# ==============================================================================

def test_all_six_required_personas_registered():
    """Verify that all 6 domain personas + default are registered in PersonaRegistry."""
    profiles = PersonaRegistry.list_personas()
    profile_ids = {p.id for p in profiles}

    assert DomainPersona.DEVOPS.value in profile_ids
    assert DomainPersona.DEBUGGER.value in profile_ids
    assert DomainPersona.SYSTEMS.value in profile_ids
    assert DomainPersona.SECURITY.value in profile_ids
    assert DomainPersona.FRONTEND.value in profile_ids
    assert DomainPersona.DATABASE.value in profile_ids
    assert DomainPersona.DEFAULT.value in profile_ids


def test_devops_persona_prompt_engineering():
    """Verify DevOps & SRE Specialist prompt engineering covers Docker, K8s, CI/CD, Terraform."""
    p = PersonaRegistry.get("devops")
    assert p is not None
    assert p.title == "DevOps & SRE Specialist"
    assert "Docker" in p.expertise
    assert "Kubernetes" in p.expertise
    assert "Terraform" in str(p.expertise)

    # Check stage-modulated system prompt
    research_prompt = p.get_phase_system_prompt(PipelinePhase.RESEARCHER)
    assert "DevOps & SRE Specialist" in research_prompt
    assert "RESEARCHER" in research_prompt
    assert "deployment platform" in research_prompt.lower() or "infrastructure" in research_prompt.lower()

    coder_prompt = p.get_phase_system_prompt(PipelinePhase.CODER)
    assert "Dockerfile" in coder_prompt or "Kubernetes" in coder_prompt or "Terraform" in coder_prompt
    assert "Output Constraints" in coder_prompt


def test_surgical_debugger_prompt_engineering():
    """Verify Surgical Debugger prompt engineering enforces minimal diffs and zero regressions."""
    p = PersonaRegistry.get("debugger")
    assert p is not None
    assert p.title == "Surgical Debugger"
    assert "Root-Cause Analysis" in p.expertise
    assert "Zero-Regression Guarantees" in p.expertise

    coder_prompt = p.get_phase_system_prompt(PipelinePhase.CODER)
    assert "SEARCH/REPLACE" in coder_prompt or "surgical" in coder_prompt.lower()
    assert "Minimal Mutation Principle" in p.system_prompt or "minimal" in p.system_prompt.lower()


def test_systems_architect_prompt_engineering():
    """Verify Systems Architect prompt engineering covers C++23, Rust, Lock-free concurrency, Big-O."""
    p = PersonaRegistry.get("systems")
    assert p is not None
    assert p.title == "Systems Architect"
    assert any("C++23" in exp for exp in p.expertise)
    assert any("Rust" in exp for exp in p.expertise)
    assert any("Big-O" in exp for exp in p.expertise)

    arch_prompt = p.get_phase_system_prompt(PipelinePhase.ARCHITECT)
    assert "Systems Architect" in arch_prompt
    assert "Big-O" in arch_prompt or "lock-free" in arch_prompt.lower() or "cache" in arch_prompt.lower()


def test_application_security_prompt_engineering():
    """Verify Application Security Engineer prompt engineering covers OWASP, HMAC, Auth, Constant-time crypto."""
    p = PersonaRegistry.get("security")
    assert p is not None
    assert p.title == "Application Security Engineer"
    assert any("OWASP" in exp for exp in p.expertise)
    assert any("HMAC" in exp for exp in p.expertise)
    assert any("Constant-Time" in exp for exp in p.expertise)

    critic_prompt = p.get_phase_system_prompt(PipelinePhase.CRITIC)
    assert "SAST" in critic_prompt or "OWASP" in critic_prompt or "security" in critic_prompt.lower()
    assert "hmac.compare_digest" in p.system_prompt or "constant-time" in p.system_prompt.lower()


def test_frontend_fullstack_prompt_engineering():
    """Verify Frontend & Fullstack Engineer prompt engineering covers React, Vite, Next.js, CSS, Accessibility."""
    p = PersonaRegistry.get("frontend")
    assert p is not None
    assert p.title == "Frontend & Fullstack Engineer"
    assert any("React" in exp for exp in p.expertise)
    assert any("Next.js" in exp for exp in p.expertise)
    assert any("Accessibility" in exp or "a11y" in exp.lower() for exp in p.expertise)

    coder_prompt = p.get_phase_system_prompt(PipelinePhase.CODER)
    assert "semantic" in coder_prompt.lower() or "react" in coder_prompt.lower() or "accessible" in coder_prompt.lower()


def test_database_optimizer_prompt_engineering():
    """Verify Database & Query Optimizer prompt engineering covers PostgreSQL, Redis, Spanner, SQL tuning."""
    p = PersonaRegistry.get("database")
    assert p is not None
    assert p.title == "Database & Query Optimizer"
    assert any("PostgreSQL" in exp for exp in p.expertise)
    assert any("Redis" in exp for exp in p.expertise)
    assert any("Spanner" in exp for exp in p.expertise)

    arch_prompt = p.get_phase_system_prompt(PipelinePhase.ARCHITECT)
    assert "schema" in arch_prompt.lower() or "indexing" in arch_prompt.lower() or "caching" in arch_prompt.lower()


# ==============================================================================
# 2. Persona Registry and Alias Matching Tests
# ==============================================================================

def test_registry_alias_resolutions():
    """Verify flexible alias matching for all domain personas."""
    # DevOps aliases
    assert PersonaRegistry.get("devops") == DEVOPS_PERSONA
    assert PersonaRegistry.get("sre") == DEVOPS_PERSONA
    assert PersonaRegistry.get("k8s") == DEVOPS_PERSONA
    assert PersonaRegistry.get("kubernetes") == DEVOPS_PERSONA
    assert PersonaRegistry.get("docker") == DEVOPS_PERSONA
    assert PersonaRegistry.get("terraform") == DEVOPS_PERSONA
    assert PersonaRegistry.get("DevOps & SRE Specialist") == DEVOPS_PERSONA

    # Debugger aliases
    assert PersonaRegistry.get("debugger") == DEBUGGER_PERSONA
    assert PersonaRegistry.get("surgical") == DEBUGGER_PERSONA
    assert PersonaRegistry.get("surgical debugger") == DEBUGGER_PERSONA
    assert PersonaRegistry.get("patch") == DEBUGGER_PERSONA
    assert PersonaRegistry.get("root_cause") == DEBUGGER_PERSONA

    # Systems Architect aliases
    assert PersonaRegistry.get("systems") == SYSTEMS_PERSONA
    assert PersonaRegistry.get("systems architect") == SYSTEMS_PERSONA
    assert PersonaRegistry.get("rust") == SYSTEMS_PERSONA
    assert PersonaRegistry.get("cpp") == SYSTEMS_PERSONA
    assert PersonaRegistry.get("c++") == SYSTEMS_PERSONA

    # Security aliases
    assert PersonaRegistry.get("security") == SECURITY_PERSONA
    assert PersonaRegistry.get("appsec") == SECURITY_PERSONA
    assert PersonaRegistry.get("application security engineer") == SECURITY_PERSONA
    assert PersonaRegistry.get("sec") == SECURITY_PERSONA
    assert PersonaRegistry.get("owasp") == SECURITY_PERSONA

    # Frontend aliases
    assert PersonaRegistry.get("frontend") == FRONTEND_PERSONA
    assert PersonaRegistry.get("fullstack") == FRONTEND_PERSONA or PersonaRegistry.get("fullstack") == DEFAULT_PERSONA
    assert PersonaRegistry.get("react") == FRONTEND_PERSONA
    assert PersonaRegistry.get("nextjs") == FRONTEND_PERSONA
    assert PersonaRegistry.get("a11y") == FRONTEND_PERSONA

    # Database aliases
    assert PersonaRegistry.get("database") == DATABASE_PERSONA
    assert PersonaRegistry.get("db") == DATABASE_PERSONA
    assert PersonaRegistry.get("sql") == DATABASE_PERSONA
    assert PersonaRegistry.get("postgres") == DATABASE_PERSONA
    assert PersonaRegistry.get("redis") == DATABASE_PERSONA

    # Default / Generalist
    assert PersonaRegistry.get("default") == DEFAULT_PERSONA
    assert PersonaRegistry.get("general") == DEFAULT_PERSONA
    assert PersonaRegistry.get("generalist") == DEFAULT_PERSONA
    assert PersonaRegistry.get("reset") == DEFAULT_PERSONA


def test_registry_fallback_and_formatting():
    """Verify get_or_default and table formatting."""
    assert PersonaRegistry.get_or_default("non_existent_persona_12345") == DEFAULT_PERSONA
    assert PersonaRegistry.get_or_default(None) == DEFAULT_PERSONA

    table_text = PersonaRegistry.format_persona_table("devops")
    assert "Available K-CLI Personas:" in table_text
    assert "DevOps & SRE Specialist" in table_text
    assert "Surgical Debugger" in table_text
    assert "Systems Architect" in table_text
    assert "Application Security Engineer" in table_text
    assert "Frontend & Fullstack Engineer" in table_text
    assert "Database & Query Optimizer" in table_text
    assert "▶ [ACTIVE]" in table_text


# ==============================================================================
# 3. Orchestrator Integration Tests
# ==============================================================================

class PersonaCapturingDriver(LLMDriver):
    """Driver that records system prompts sent to it during execution."""
    def __init__(self):
        super().__init__(mock_mode=True)
        self.captured_system_prompts: List[str] = []

    def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        if system_prompt:
            self.captured_system_prompts.append(system_prompt)
        return super().generate(prompt, system_prompt, temperature, stream_callback)


def test_orchestrator_with_domain_persona():
    """Verify Orchestrator modulates system prompts according to active persona."""
    driver = PersonaCapturingDriver()
    orchestrator = Orchestrator(driver=driver, persona="security")

    assert orchestrator.active_persona is not None
    assert orchestrator.active_persona.id == "security"

    res = orchestrator.execute_pipeline(
        user_prompt="Implement constant-time HMAC token validation",
        language="python"
    )

    assert res.success is True
    assert res.persona == "security"
    assert len(driver.captured_system_prompts) >= 4  # RESEARCHER, ARCHITECT, CODER, CRITIC

    # Verify that Application Security Engineer prompt was actually used
    assert any("Application Security Engineer" in sp for sp in driver.captured_system_prompts)
    assert any("RESEARCHER" in sp for sp in driver.captured_system_prompts)
    assert any("ARCHITECT" in sp for sp in driver.captured_system_prompts)
    assert any("CODER" in sp for sp in driver.captured_system_prompts)


def test_orchestrator_dynamic_persona_switching():
    """Verify Orchestrator set_persona method."""
    driver = LLMDriver(mock_mode=True)
    orchestrator = Orchestrator(driver=driver)

    orchestrator.set_persona("devops")
    assert orchestrator.get_active_persona() == DEVOPS_PERSONA

    orchestrator.set_persona("systems")
    assert orchestrator.get_active_persona() == SYSTEMS_PERSONA

    orchestrator.set_persona("database")
    assert orchestrator.get_active_persona() == DATABASE_PERSONA


# ==============================================================================
# 4. SessionManager Slash Command Tests (/persona)
# ==============================================================================

def test_session_manager_persona_slash_command_list(tmp_path: Path):
    """Verify /persona with no args displays available personas table."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    handled, out = session.handle_slash_command("/persona")
    assert handled is True
    assert "Available K-CLI Personas:" in out
    assert "DevOps & SRE Specialist" in out
    assert "Surgical Debugger" in out
    assert "Systems Architect" in out


def test_session_manager_persona_switching_commands(tmp_path: Path):
    """Verify seamless switching between all 6 personas via /persona <name>."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)

    # 1. DevOps
    handled, out = session.handle_slash_command("/persona devops")
    assert handled is True
    assert "DevOps & SRE Specialist" in out
    assert session.active_persona == "DevOps & SRE Specialist"
    assert session.orchestrator.active_persona == DEVOPS_PERSONA

    # 2. Surgical Debugger
    handled, out = session.handle_slash_command("/persona surgical debugger")
    assert handled is True
    assert "Surgical Debugger" in out
    assert session.active_persona == "Surgical Debugger"

    # 3. Systems Architect
    handled, out = session.handle_slash_command("/persona systems")
    assert handled is True
    assert "Systems Architect" in out
    assert session.active_persona == "Systems Architect"

    # 4. Application Security Engineer
    handled, out = session.handle_slash_command("/persona appsec")
    assert handled is True
    assert "Application Security Engineer" in out
    assert session.active_persona == "Application Security Engineer"

    # 5. Frontend & Fullstack Engineer
    handled, out = session.handle_slash_command("/persona frontend")
    assert handled is True
    assert "Frontend & Fullstack Engineer" in out
    assert session.active_persona == "Frontend & Fullstack Engineer"

    # 6. Database & Query Optimizer
    handled, out = session.handle_slash_command("/persona database")
    assert handled is True
    assert "Database & Query Optimizer" in out
    assert session.active_persona == "Database & Query Optimizer"

    # Reset to Default
    handled, out = session.handle_slash_command("/persona reset")
    assert handled is True
    assert "Fullstack AI Systems Engineer" in out or "default" in out.lower()

    # Invalid persona
    handled, out = session.handle_slash_command("/persona invalid_persona_name")
    assert handled is False or "Unknown" in out
    assert "Unknown persona" in out


def test_session_status_shows_active_persona(tmp_path: Path):
    """Verify /status output includes the active persona title."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    session.set_persona("database")

    handled, out = session.handle_slash_command("/status")
    assert handled is True
    assert "Database & Query Optimizer" in out


def test_session_process_turn_with_active_persona(tmp_path: Path):
    """Verify session process_turn passes active persona to pipeline execution."""
    session = SessionManager(workspace_dir=str(tmp_path), mock_mode=True)
    session.set_persona("systems")

    gen = session.process_turn("Write a lock-free ring buffer")
    tokens = list(gen)
    assert len(tokens) > 0
    assert session.last_result["success"] is True


# ==============================================================================
# 5. CLI & Color Mapping Tests
# ==============================================================================

def test_cli_get_persona_color():
    """Verify get_persona_color for all domain personas."""
    assert get_persona_color("DEVOPS") == "cyan"
    assert get_persona_color("DevOps & SRE Specialist") == "cyan"
    assert get_persona_color("SURGICAL DEBUGGER") == "red"
    assert get_persona_color("DEBUGGER") == "red"
    assert get_persona_color("SYSTEMS ARCHITECT") == "magenta"
    assert get_persona_color("APPLICATION SECURITY ENGINEER") == "red"
    assert get_persona_color("FRONTEND & FULLSTACK ENGINEER") == "green"
    assert get_persona_color("DATABASE & QUERY OPTIMIZER") == "yellow"
    assert get_persona_color("UNKNOWN_PERSONA") == "blue"


def test_cli_run_command_with_persona_flag():
    """Verify k run --persona <name> invokes execute_run with specialized persona."""
    result = runner.invoke(app, ["run", "Create a Kubernetes deployment manifest", "--persona", "devops", "--mock"])
    assert result.exit_code == 0
    assert "DevOps & SRE Specialist" in result.output or "GROUND-TRUTH VERIFIED" in result.output
