"""
test_orchestrator.py - Comprehensive Unit tests for Orchestrator sequential persona state machine
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

_root_dir = Path(__file__).parent.parent
_parent_dir = _root_dir.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

import pytest

try:
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult, Persona
    from k_cli.git.verifier import VerificationResult, Verifier
except ModuleNotFoundError:
    from llm_driver import LLMDriver
    from orchestrator import Orchestrator, OrchestratorResult, Persona
    from verifier import VerificationResult, Verifier


def test_orchestrator_fluff_stripping():
    text = "Sure, here is your code:\n```python\nprint('hello')\n```\nHope this helps!"
    stripped = Orchestrator.strip_fluff(text)
    assert stripped == "print('hello')"


def test_orchestrator_ram_tracking_and_budget_enforcer():
    import gc
    gc.collect()
    orchestrator = Orchestrator(ram_budget_mb=2048.0)
    ram_mb = orchestrator.get_current_ram_mb()
    assert isinstance(ram_mb, float)
    assert ram_mb > 0.0

    checked_ram = orchestrator.check_ram_budget()
    assert isinstance(checked_ram, float)
    assert checked_ram > 0.0


def test_orchestrator_5_persona_pipeline():
    driver = LLMDriver(mock_mode=True)
    orchestrator = Orchestrator(driver=driver)

    res = orchestrator.execute_pipeline(
        user_prompt="Write a Python function to double an integer",
        language="python"
    )

    assert res.success is True
    assert res.attempts == 1
    assert res.retry_count == 0
    assert res.memory_rss_mb > 0.0
    assert res.memory_rss_mb < 1024.0
    assert "def " in res.final_code or "import " in res.final_code or "print" in res.final_code

    # Check persona_outputs contract attribute
    p_outputs = res.persona_outputs
    assert isinstance(p_outputs, dict)
    assert Persona.RESEARCHER.value in p_outputs
    assert Persona.ARCHITECT.value in p_outputs
    assert Persona.CODER.value in p_outputs
    assert Persona.CRITIC.value in p_outputs


def test_orchestrator_stream_cb_alias():
    driver = LLMDriver(mock_mode=True)
    orchestrator = Orchestrator(driver=driver)

    streamed_events = []

    def stream_callback(persona: Persona, token: str):
        streamed_events.append((persona, token))

    res = orchestrator.execute_pipeline(
        user_prompt="Calculate factorial",
        language="python",
        stream_cb=stream_callback
    )

    assert res.success is True
    assert len(streamed_events) > 0
    personas_seen = {p for p, t in streamed_events}
    assert Persona.RESEARCHER in personas_seen
    assert Persona.ARCHITECT in personas_seen
    assert Persona.CODER in personas_seen
    assert Persona.CRITIC in personas_seen


class MockFailingDriver(LLMDriver):
    """Driver that returns syntax error on attempt 1, and fixed code on attempt 2."""
    def __init__(self):
        super().__init__(mock_mode=True)
        self.debugger_prompts = []

    def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        sys_lower = (system_prompt or "").lower()
        if "coder" in sys_lower:
            return "```python\ndef broken_func(:\n    return 42\n```"
        elif "debugger" in sys_lower:
            self.debugger_prompts.append(prompt)
            return "```python\ndef broken_func():\n    return 42\n```"
        return super().generate(prompt, system_prompt, temperature=stream_callback)


def test_orchestrator_auto_debug_loop_repair_and_critic_notes():
    driver = MockFailingDriver()
    orchestrator = Orchestrator(driver=driver, max_retries=3)

    res = orchestrator.execute_pipeline(
        user_prompt="Fix broken function",
        language="python"
    )

    assert res.success is True
    assert res.attempts == 2  # 1 initial attempt + 1 retry
    assert res.retry_count == 1
    assert res.final_code == "def broken_func():\n    return 42"
    assert len(driver.debugger_prompts) == 1
    # Verify critic notes included in debugger prompt
    assert "Critic Notes:" in driver.debugger_prompts[0]


class AlwaysFailingDriver(LLMDriver):
    """Driver that continuously returns invalid Python syntax."""
    def __init__(self):
        super().__init__(mock_mode=True)

    def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
        sys_lower = (system_prompt or "").lower()
        if "coder" in sys_lower or "debugger" in sys_lower:
            return "```python\ndef invalid_syntax_func(:\n```"
        return super().generate(prompt, system_prompt, temperature=stream_callback)


def test_orchestrator_auto_debug_loop_max_retries_termination():
    driver = AlwaysFailingDriver()
    orchestrator = Orchestrator(driver=driver, max_retries=3)

    res = orchestrator.execute_pipeline(
        user_prompt="Attempt unsolvable syntax fix",
        language="python"
    )

    assert res.success is False
    assert res.attempts == 4  # 1 initial attempt + 3 retries
    assert res.retry_count == 3
