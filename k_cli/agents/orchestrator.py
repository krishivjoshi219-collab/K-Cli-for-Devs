"""
orchestrator.py - Sequential Persona State Machine for K-CLI (Project Bankai Engine v1.0.0)

Manages a single 1.5B GGUF model in RAM while switching system personas sequentially:
  [RESEARCHER] -> [ARCHITECT] -> [CODER] -> [CRITIC] -> [VERIFIER] -> (Auto-Debug Loop max 3 retries)

Enforces non-conversational code outputs, zero-fluff text, and < 1.0 GB system RAM budget.
"""

from __future__ import annotations

import gc
import json
import os
import psutil
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
    from k_cli.agents.persona import DomainPersona, PersonaProfile, PersonaRegistry
    from k_cli.github.dedup_engine import DedupEngine, DedupMatch
    from k_cli.tools.mcp_client import MCPManager
except (ModuleNotFoundError, ImportError):
    try:
        from k_cli.core.llm_driver import LLMDriver
        from verifier import CodeExtractor, VerificationResult, Verifier
        from persona import DomainPersona, PersonaProfile, PersonaRegistry
        from dedup_engine import DedupEngine, DedupMatch
        from mcp_client import MCPManager
    except (ModuleNotFoundError, ImportError):
        from k_cli.core.llm_driver import LLMDriver
        from verifier import CodeExtractor, VerificationResult, Verifier
        PersonaProfile = Any  # type: ignore
        PersonaRegistry = None  # type: ignore
        DomainPersona = None  # type: ignore
        DedupEngine = None  # type: ignore
        DedupMatch = None  # type: ignore
        MCPManager = None  # type: ignore


class Persona(str, Enum):
    RESEARCHER = "RESEARCHER"
    ARCHITECT = "ARCHITECT"
    CODER = "CODER"
    CRITIC = "CRITIC"
    DEBUGGER = "DEBUGGER"


PERSONA_PROMPTS: Dict[Persona, str] = {
    Persona.RESEARCHER: (
        "You are [RESEARCHER] persona for K-CLI AI Agent. "
        "Extract header signatures, dependencies, required imports, and problem specifications. "
        "Be concise and technical. Do NOT output conversational fluff."
    ),
    Persona.ARCHITECT: (
        "You are [ARCHITECT] persona for K-CLI AI Agent. "
        "Output a structured execution plan wrapped inside <think>...</think> tags, "
        "followed by a compact JSON architecture specification. "
        "Ensure computational and memory efficiency. Do NOT output conversational fluff."
    ),
    Persona.CODER: (
        "You are [CODER] persona for K-CLI AI Agent. "
        "Generate isolated, production-grade implementation code enclosed strictly inside markdown code blocks. "
        "Do NOT write any text, greetings, intros, or chatter outside the markdown code block. "
        "Only output pure executable code."
    ),
    Persona.CRITIC: (
        "You are [CRITIC] persona for K-CLI AI Agent. "
        "Evaluate the candidate code for syntax correctness, null pointer risks, boundary flaws, and memory bloat. "
        "Output 'VALIDATED' if approved, or 'CRITIQUE: <reasons>' if defects are found. "
        "Do NOT output conversational fluff."
    ),
    Persona.DEBUGGER: (
        "You are [DEBUGGER] persona for K-CLI AI Agent. "
        "The previous code failed compiler/execution verification. "
        "Analyze the provided line number, stack trace, and original code. "
        "Output ONLY the corrected code enclosed in markdown code blocks. "
        "Do NOT output any conversational text or explanation outside the code block."
    ),
}


@dataclass
class OrchestratorResult:
    """Dataclass returned at the end of persona pipeline execution."""
    success: bool
    final_code: str
    language: str
    verification: VerificationResult
    attempts: int
    architecture_plan: str
    critic_output: str
    ram_usage_mb: float
    history: List[Dict[str, Any]] = field(default_factory=list)
    persona: str = "default"
    dedup_warning: Optional[str] = None
    dedup_match: Optional[Dict[str, Any]] = None

    @property
    def memory_rss_mb(self) -> float:
        return self.ram_usage_mb

    @property
    def retry_count(self) -> int:
        return max(0, self.attempts - 1)

    @property
    def persona_outputs(self) -> Dict[str, str]:
        return {item["persona"]: item["output"] for item in self.history if isinstance(item, dict) and "persona" in item and "output" in item}


class Orchestrator:
    """Sequentially switches model personas to design, generate, critique, and verify code."""

    def __init__(
        self,
        driver: Optional[LLMDriver] = None,
        verifier: Optional[Verifier] = None,
        max_retries: int = 3,
        ram_budget_mb: float = 1024.0,
        persona: Optional[Union[str, PersonaProfile]] = None,
        dedup_engine: Optional[Any] = None,
        mcp_manager: Optional[Any] = None,
    ):
        self.driver = driver or LLMDriver()
        self.verifier = verifier or Verifier()
        self.max_retries = max_retries
        self.ram_budget_mb = ram_budget_mb
        self.active_persona: Optional[PersonaProfile] = (
            persona if isinstance(persona, PersonaProfile)
            else (PersonaRegistry.get_or_default(persona) if PersonaRegistry else None)
        )
        self.dedup_engine = dedup_engine
        self.mcp_manager = mcp_manager

    def set_persona(self, persona: Union[str, PersonaProfile]) -> Optional[PersonaProfile]:
        """Switches active domain persona profile."""
        if isinstance(persona, PersonaProfile):
            self.active_persona = persona
        elif PersonaRegistry:
            self.active_persona = PersonaRegistry.get_or_default(persona)
        return self.active_persona

    def get_active_persona(self) -> Optional[PersonaProfile]:
        """Returns currently active domain persona profile."""
        return self.active_persona

    @staticmethod
    def get_current_ram_mb() -> float:
        """Returns current process memory consumption in Megabytes (RSS)."""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)

    def check_ram_budget(self) -> float:
        """Enforces RAM budget < 1.0 GB limit, invoking gc if memory is high."""
        ram_mb = self.get_current_ram_mb()
        if ram_mb > self.ram_budget_mb * 0.85:
            gc.collect()
            ram_mb = self.get_current_ram_mb()
        return ram_mb

    @staticmethod
    def strip_fluff(text: str) -> str:
        """Strips conversational fluff and extracts pure code block if present."""
        # Find code blocks first
        blocks = CodeExtractor.extract_code_blocks(text)
        if blocks and blocks[0][1].strip():
            return blocks[0][1].strip()

        # If no code block, strip common fluff prefixes/suffixes
        cleaned = text.strip()
        fluff_patterns = [
            r"^(Sure|Certainly|Here is|Below is|Here's).*?:\n*",
            r"^(Hope this helps|Let me know if you need).*$",
        ]
        for pat in fluff_patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()
        return cleaned

    def execute_pipeline(
        self,
        user_prompt: str,
        language: str = "python",
        test_code: Optional[str] = None,
        token_stream_callback: Optional[Callable[[Persona, str], None]] = None,
        stream_cb: Optional[Callable[[Persona, str], None]] = None,
        persona: Optional[Union[str, PersonaProfile]] = None,
    ) -> OrchestratorResult:
        """
        Executes sequential persona state machine:
        RESEARCHER -> ARCHITECT -> CODER -> CRITIC -> VERIFIER -> (DEBUGGER loop up to max_retries)
        """
        cb = token_stream_callback or stream_cb
        history = []
        self.check_ram_budget()

        # Deduplication check before execution
        dedup_warning = None
        dedup_dict = None
        if self.dedup_engine is None and DedupEngine is not None:
            try:
                self.dedup_engine = DedupEngine()
            except Exception:
                self.dedup_engine = None

        if self.dedup_engine is not None:
            try:
                d_match = self.dedup_engine.scan_for_duplicate(user_prompt)
                if d_match and d_match.is_duplicate:
                    dedup_warning = f"Duplicate task detected ({d_match.confidence:.1%}): {d_match.explanation}"
                    dedup_dict = d_match.to_dict()
            except Exception:
                pass

        active_profile = None
        if persona is not None:
            active_profile = persona if isinstance(persona, PersonaProfile) else (PersonaRegistry.get_or_default(persona) if PersonaRegistry else None)
        else:
            active_profile = self.active_persona

        # Phase 1: RESEARCHER
        research_prompt = f"User Request: {user_prompt}\nTarget Language: {language}"
        research_out = self._call_persona(
            Persona.RESEARCHER, research_prompt, cb, active_persona=active_profile
        )
        history.append({"persona": Persona.RESEARCHER.value, "output": research_out})

        # Phase 2: ARCHITECT
        architect_prompt = (
            f"User Request: {user_prompt}\n"
            f"Research Context:\n{research_out}\n"
            f"Target Language: {language}"
        )
        architect_out = self._call_persona(
            Persona.ARCHITECT, architect_prompt, cb, active_persona=active_profile
        )
        history.append({"persona": Persona.ARCHITECT.value, "output": architect_out})

        # Phase 3: CODER
        coder_prompt = (
            f"User Request: {user_prompt}\n"
            f"Architecture Plan:\n{architect_out}\n"
            f"Generate isolated {language} implementation."
        )
        coder_raw = self._call_persona(
            Persona.CODER, coder_prompt, cb, active_persona=active_profile
        )
        candidate_code = self.strip_fluff(coder_raw)
        history.append({"persona": Persona.CODER.value, "output": candidate_code})

        # Phase 4: CRITIC
        critic_prompt = f"Target Language: {language}\nCandidate Code:\n```\n{candidate_code}\n```"
        critic_out = self._call_persona(
            Persona.CRITIC, critic_prompt, cb, active_persona=active_profile
        )
        history.append({"persona": Persona.CRITIC.value, "output": critic_out})

        # Phase 5: VERIFIER Guard & Auto-Debug Loop
        attempts = 0
        current_code = candidate_code
        v_result = self.verifier.verify(current_code, language=language, test_code=test_code)

        while not v_result.success and attempts < self.max_retries:
            attempts += 1
            self.check_ram_budget()

            # Construct debugger prompt with line number & error traceback
            debugger_prompt = (
                f"Attempt {attempts}/{self.max_retries}\n"
                f"Target Language: {language}\n"
                f"Failed Code:\n```\n{current_code}\n```\n"
                f"Error Line Number: {v_result.line_number or 'Unknown'}\n"
                f"Compiler/Execution Error Traceback:\n{v_result.error_trace}\n"
            )
            if critic_out:
                debugger_prompt += f"Critic Notes:\n{critic_out}\n"
            debugger_prompt += "\nFix the code and output ONLY the corrected code inside markdown code blocks."

            debug_raw = self._call_persona(
                Persona.DEBUGGER, debugger_prompt, cb, active_persona=active_profile
            )
            current_code = self.strip_fluff(debug_raw)
            history.append({
                "persona": f"{Persona.DEBUGGER.value}_attempt_{attempts}",
                "output": current_code,
                "error_trace": v_result.error_trace,
            })

            # Re-verify
            v_result = self.verifier.verify(current_code, language=language, test_code=test_code)

        final_ram = self.get_current_ram_mb()

        return OrchestratorResult(
            success=v_result.success,
            final_code=current_code,
            language=language,
            verification=v_result,
            attempts=attempts + 1,
            architecture_plan=architect_out,
            critic_output=critic_out,
            ram_usage_mb=final_ram,
            history=history,
            persona=active_profile.id if active_profile else "default",
            dedup_warning=dedup_warning,
            dedup_match=dedup_dict,
        )

    def execute_subagents(
        self,
        user_prompt: str,
        context_files: Optional[List[str]] = None,
        target_roles: Optional[List[Any]] = None,
        max_workers: int = 4,
        show_ui: bool = False,
        console: Optional[Any] = None,
    ):
        """
        Executes parallel multi-agent decomposition and synthesis using SubagentDispatcher.
        """
        try:
            from k_cli.agents.subagents import SubagentDispatcher, SubagentVisualizer
        except ModuleNotFoundError:
            from subagents import SubagentDispatcher, SubagentVisualizer

        dispatcher = SubagentDispatcher(
            driver=self.driver,
            verifier=self.verifier,
            max_workers=max_workers,
            ram_budget_mb=self.ram_budget_mb,
            mcp_manager=self.mcp_manager,
            dedup_engine=self.dedup_engine,
        )
        tasks = dispatcher.decomposer.decompose(
            prompt=user_prompt,
            context_files=context_files,
            target_roles=target_roles,
        )
        if show_ui:
            return SubagentVisualizer.execute_with_live_cli(
                dispatcher=dispatcher,
                tasks=tasks,
                console=console,
            )
        return dispatcher.dispatch(tasks=tasks)

    def _call_persona(
        self,
        persona: Persona,
        prompt: str,
        callback: Optional[Callable[[Persona, str], None]] = None,
        active_persona: Optional[PersonaProfile] = None,
    ) -> str:
        """Sends prompt to LLM driver with current persona system prompt."""
        self.check_ram_budget()
        target_profile = active_persona or self.active_persona
        if target_profile and hasattr(target_profile, "get_phase_system_prompt"):
            system_prompt = target_profile.get_phase_system_prompt(persona)
        else:
            system_prompt = PERSONA_PROMPTS.get(persona, "You are a K-CLI AI Agent.")

        def _inner_callback(token: str):
            if callback:
                callback(persona, token)

        return self.driver.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1 if persona in (Persona.CODER, Persona.DEBUGGER) else 0.3,
            stream_callback=_inner_callback if callback else None,
        )

