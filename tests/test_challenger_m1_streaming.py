"""
test_challenger_m1_streaming.py - Empirical challenger test suite for streaming callbacks
in llm_driver.py and orchestrator.py.
"""

import io
import json
import sys
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

_root_dir = Path(__file__).parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

import pytest

try:
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult, Persona
    from k_cli.git.verifier import VerificationResult, Verifier
except ModuleNotFoundError:
    from llm_driver import LLMDriver
    from orchestrator import Orchestrator, OrchestratorResult, Persona
    from verifier import VerificationResult, Verifier


class TestLLMDriverStreaming:
    """Empirical verification of LLMDriver streaming mechanics."""

    def test_mock_driver_chunk_fidelity_and_ordering(self):
        """Verify that all streamed chunks concatenated equal the exact return value."""
        driver = LLMDriver(mock_mode=True)
        chunks: List[str] = []

        def callback(chunk: str):
            chunks.append(chunk)

        prompts = [
            ("Write RAM monitor", "You are [RESEARCHER] persona"),
            ("Design architecture", "You are [ARCHITECT] persona"),
            ("Generate code", "You are [CODER] persona"),
            ("Review code", "You are [CRITIC] persona"),
            ("Fix code", "You are [DEBUGGER] persona"),
            ("Generic prompt", None),
        ]

        for prompt, sys_prompt in prompts:
            chunks.clear()
            result = driver.generate(prompt, system_prompt=sys_prompt, stream_callback=callback)
            assert len(chunks) > 0, f"Expected chunks for prompt: {prompt}"
            assert "".join(chunks) == result, f"Concatenated chunks mismatch for {sys_prompt}"

    def test_mock_driver_no_callback_returns_same_text(self):
        """Verify driver returns identical text whether callback is provided or not."""
        driver = LLMDriver(mock_mode=True)
        for sys_prompt in ["You are [RESEARCHER] persona", "You are [ARCHITECT] persona", "You are [CODER] persona"]:
            res_no_cb = driver.generate("test prompt", system_prompt=sys_prompt, stream_callback=None)
            chunks = []
            res_with_cb = driver.generate("test prompt", system_prompt=sys_prompt, stream_callback=lambda c: chunks.append(c))
            assert res_no_cb == res_with_cb
            assert "".join(chunks) == res_no_cb

    def test_ollama_streaming_chunk_ordering_and_done_flag(self):
        """Verify Ollama streaming preserves chunk ordering and stops on done: true."""
        driver = LLMDriver(mock_mode=False)

        stream_data = [
            b'{"response": "def ", "done": false}\n',
            b'{"response": "add(a, ", "done": false}\n',
            b'{"response": "b):\\n", "done": false}\n',
            b'{"response": "    return a + b", "done": true}\n',
            b'{"response": "TRAILING_SHOULD_BE_IGNORED", "done": false}\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = stream_data
        mock_resp.__enter__.return_value = mock_resp

        chunks = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(driver, "is_ollama_available", return_value=True):
                result = driver.generate(
                    "write add function",
                    system_prompt="You are [CODER] persona",
                    stream_callback=lambda c: chunks.append(c),
                )

        assert chunks == ["def ", "add(a, ", "b):\n", "    return a + b"]
        assert result == "def add(a, b):\n    return a + b"
        assert "TRAILING_SHOULD_BE_IGNORED" not in result
        assert "TRAILING_SHOULD_BE_IGNORED" not in chunks

    def test_ollama_streaming_empty_chunks_handling(self):
        """Verify that empty response tokens in Ollama stream do not corrupt output."""
        driver = LLMDriver(mock_mode=False)

        stream_data = [
            b'{"response": "part1", "done": false}\n',
            b'{"response": "", "done": false}\n',
            b'{"response": "part2", "done": true}\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = stream_data
        mock_resp.__enter__.return_value = mock_resp

        chunks = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(driver, "is_ollama_available", return_value=True):
                result = driver.generate(
                    "prompt",
                    stream_callback=lambda c: chunks.append(c),
                )

        assert result == "part1part2"
        assert "".join(chunks) == "part1part2"

    def test_native_llama_streaming(self):
        """Verify native llama streaming chunks are captured and concatenated correctly."""
        driver = LLMDriver(mock_mode=False)

        mock_chunks = [
            {"choices": [{"text": "import "}]},
            {"choices": [{"text": "math\n"}]},
            {"choices": [{"text": "print(math.pi)"}]},
        ]
        mock_llm = MagicMock(return_value=iter(mock_chunks))

        with patch.object(driver, "get_native_llama", return_value=mock_llm):
            chunks = []
            result = driver.generate(
                "import math",
                stream_callback=lambda c: chunks.append(c),
            )

        assert chunks == ["import ", "math\n", "print(math.pi)"]
        assert result == "import math\nprint(math.pi)"

    def test_callback_exception_propagation_mock_mode(self):
        """Verify that an exception raised by the callback in mock mode propagates immediately."""
        driver = LLMDriver(mock_mode=True)

        class CustomStreamError(Exception):
            pass

        def failing_callback(token: str):
            raise CustomStreamError("Abort streaming")

        with pytest.raises(CustomStreamError, match="Abort streaming"):
            driver.generate("test prompt", stream_callback=failing_callback)

    def test_callback_cancellation_during_ollama_stream(self):
        """Verify callback cancellation during Ollama stream raises cleanly."""
        driver = LLMDriver(mock_mode=False)

        stream_data = [
            b'{"response": "token1", "done": false}\n',
            b'{"response": "token2", "done": false}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = stream_data
        mock_resp.__enter__.return_value = mock_resp

        call_count = 0

        class CancelStream(Exception):
            pass

        def cancel_on_second(tok: str):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise CancelStream("User cancelled")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(driver, "is_ollama_available", return_value=True):
                with pytest.raises(CancelStream):
                    driver.generate("prompt", stream_callback=cancel_on_second)


class TestOrchestratorStreaming:
    """Empirical verification of Orchestrator streaming callback mechanics."""

    def test_orchestrator_persona_stream_sequence(self):
        """Verify that streaming callback receives events with correct personas in order."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        events: List[Tuple[Persona, str]] = []

        def callback(persona: Persona, chunk: str):
            events.append((persona, chunk))

        res = orchestrator.execute_pipeline(
            user_prompt="Write a Python function to compute fibonacci numbers",
            language="python",
            token_stream_callback=callback,
        )

        assert res.success is True
        assert len(events) > 0

        personas_in_order = []
        for p, _ in events:
            if not personas_in_order or personas_in_order[-1] != p:
                personas_in_order.append(p)

        assert personas_in_order == [
            Persona.RESEARCHER,
            Persona.ARCHITECT,
            Persona.CODER,
            Persona.CRITIC,
        ]

    def test_orchestrator_stream_content_per_persona(self):
        """Verify that concatenated tokens for each persona match persona output."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        tokens_by_persona: dict[Persona, List[str]] = {
            Persona.RESEARCHER: [],
            Persona.ARCHITECT: [],
            Persona.CODER: [],
            Persona.CRITIC: [],
        }

        def callback(persona: Persona, chunk: str):
            tokens_by_persona[persona].append(chunk)

        res = orchestrator.execute_pipeline(
            user_prompt="Write a Python function to compute factorial",
            language="python",
            token_stream_callback=callback,
        )

        assert res.success is True

        research_streamed = "".join(tokens_by_persona[Persona.RESEARCHER])
        assert res.persona_outputs[Persona.RESEARCHER.value] == research_streamed

        architect_streamed = "".join(tokens_by_persona[Persona.ARCHITECT])
        assert res.persona_outputs[Persona.ARCHITECT.value] == architect_streamed
        assert res.architecture_plan == architect_streamed

        coder_streamed = "".join(tokens_by_persona[Persona.CODER])
        assert Orchestrator.strip_fluff(coder_streamed) == res.final_code

        critic_streamed = "".join(tokens_by_persona[Persona.CRITIC])
        assert res.persona_outputs[Persona.CRITIC.value] == critic_streamed
        assert res.critic_output == critic_streamed

    def test_orchestrator_callback_aliasing_precedence(self):
        """Verify token_stream_callback takes precedence over stream_cb if both given."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        events_primary = []
        events_alias = []

        res = orchestrator.execute_pipeline(
            user_prompt="Double an integer",
            language="python",
            token_stream_callback=lambda p, c: events_primary.append((p, c)),
            stream_cb=lambda p, c: events_alias.append((p, c)),
        )

        assert res.success is True
        assert len(events_primary) > 0
        assert len(events_alias) == 0

    def test_orchestrator_stream_cb_only(self):
        """Verify stream_cb alias works when token_stream_callback is None."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        events_alias = []
        res = orchestrator.execute_pipeline(
            user_prompt="Double an integer",
            language="python",
            token_stream_callback=None,
            stream_cb=lambda p, c: events_alias.append((p, c)),
        )

        assert res.success is True
        assert len(events_alias) > 0

    def test_orchestrator_streaming_in_debugger_retry_loop(self):
        """Verify Persona.DEBUGGER is streamed during auto-debug retry attempts."""
        class FailingOnceDriver(LLMDriver):
            def __init__(self):
                super().__init__(mock_mode=True)
                self.debug_calls = 0

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                sys_lower = (system_prompt or "").lower()
                if "coder" in sys_lower:
                    text = "```python\ndef bad_syntax(:\n    pass\n```"
                elif "debugger" in sys_lower:
                    self.debug_calls += 1
                    text = "```python\ndef good_syntax():\n    return 42\n```"
                else:
                    return super().generate(prompt, system_prompt, stream_callback=stream_callback)

                if stream_callback:
                    for chunk in [text[:15], text[15:]]:
                        stream_callback(chunk)
                return text

        driver = FailingOnceDriver()
        orchestrator = Orchestrator(driver=driver, max_retries=2)

        events: List[Tuple[Persona, str]] = []
        res = orchestrator.execute_pipeline(
            user_prompt="Generate syntax repair test",
            language="python",
            token_stream_callback=lambda p, c: events.append((p, c)),
        )

        assert res.success is True
        assert res.attempts == 2
        assert driver.debug_calls == 1

        personas_in_order = []
        for p, _ in events:
            if not personas_in_order or personas_in_order[-1] != p:
                personas_in_order.append(p)

        assert personas_in_order == [
            Persona.RESEARCHER,
            Persona.ARCHITECT,
            Persona.CODER,
            Persona.CRITIC,
            Persona.DEBUGGER,
        ]

        debugger_chunks = [c for p, c in events if p == Persona.DEBUGGER]
        assert len(debugger_chunks) > 0
        assert "".join(debugger_chunks) == "```python\ndef good_syntax():\n    return 42\n```"

    def test_orchestrator_streaming_exception_propagation(self):
        """Verify exception raised in orchestrator stream callback propagates immediately."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        class PipelineAborted(Exception):
            pass

        def abort_on_coder(persona: Persona, chunk: str):
            if persona == Persona.CODER:
                raise PipelineAborted("Client disconnected during CODER phase")

        with pytest.raises(PipelineAborted, match="Client disconnected during CODER phase"):
            orchestrator.execute_pipeline(
                user_prompt="Write a test",
                language="python",
                token_stream_callback=abort_on_coder,
            )

    def test_orchestrator_streaming_with_none_callback(self):
        """Verify execute_pipeline runs cleanly when both callbacks are None."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        res = orchestrator.execute_pipeline(
            user_prompt="Write a simple script",
            language="python",
            token_stream_callback=None,
            stream_cb=None,
        )

        assert res.success is True
        assert res.final_code != ""


class TestStreamingBoundaryAndStress:
    """Stress tests on large token sequences, empty tokens, and special characters."""

    def test_high_volume_token_streaming(self):
        """Stress test streaming over 5,000 token chunks without loss or corruption."""
        class HighVolumeDriver(LLMDriver):
            def __init__(self):
                super().__init__(mock_mode=True)

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                tokens = [f"tok_{i} " for i in range(5000)]
                full_text = "```python\n" + "".join(tokens) + "\n```"
                if stream_callback:
                    for t in tokens:
                        stream_callback(t)
                return full_text

        driver = HighVolumeDriver()
        orchestrator = Orchestrator(driver=driver)

        collected_tokens = []
        res = orchestrator.execute_pipeline(
            user_prompt="High volume stream test",
            language="python",
            token_stream_callback=lambda p, c: collected_tokens.append((p, c)) if p == Persona.CODER else None,
        )

        assert len(collected_tokens) == 5000
        assert collected_tokens[0] == (Persona.CODER, "tok_0 ")
        assert collected_tokens[-1] == (Persona.CODER, "tok_4999 ")

    def test_streaming_special_characters_and_multibyte_utf8(self):
        """Verify stream callback handles emojis, unicode, newlines, and quotes faithfully."""
        class UnicodeDriver(LLMDriver):
            def __init__(self):
                super().__init__(mock_mode=True)

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                text = "```python\n# 🚀 漢字 € \t \r\nprint('hello world ✨')\n```"
                if stream_callback:
                    chunks = [text[:10], text[10:25], text[25:]]
                    for c in chunks:
                        stream_callback(c)
                return text

        driver = UnicodeDriver()
        orchestrator = Orchestrator(driver=driver)

        streamed = []
        res = orchestrator.execute_pipeline(
            user_prompt="Unicode stream test",
            language="python",
            token_stream_callback=lambda p, c: streamed.append(c) if p == Persona.CODER else None,
        )

        reconstructed = "".join(streamed)
        assert "🚀 漢字 €" in reconstructed
        assert "hello world ✨" in reconstructed
        assert Orchestrator.strip_fluff(reconstructed) == res.final_code

    def test_empty_string_stream_generation(self):
        """Verify handling when driver outputs an empty string."""
        class EmptyDriver(LLMDriver):
            def __init__(self):
                super().__init__(mock_mode=True)

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                if stream_callback:
                    stream_callback("")
                return ""

        driver = EmptyDriver()
        orchestrator = Orchestrator(driver=driver, max_retries=1)

        events = []
        # When no test_code is provided, empty code passes AST syntax verification (valid empty module)
        res_syntax_only = orchestrator.execute_pipeline(
            user_prompt="Generate empty",
            language="python",
            token_stream_callback=lambda p, c: events.append((p, c)),
        )
        assert res_syntax_only.success is True
        assert res_syntax_only.final_code == ""

        # When test_code is provided, empty code fails pytest verification
        res_with_tests = orchestrator.execute_pipeline(
            user_prompt="Generate empty",
            language="python",
            test_code="def test_something(): assert False",
            token_stream_callback=None,
        )
        assert res_with_tests.success is False

    def test_ollama_mid_stream_network_error_fallback(self):
        """Verify that mid-stream network drop triggers mock fallback without crashing."""
        driver = LLMDriver(mock_mode=False)

        class FaultyStream:
            def __init__(self):
                self.lines = [
                    b'{"response": "partial ", "done": false}\n',
                ]
                self.idx = 0

            def __iter__(self):
                return self

            def __next__(self):
                if self.idx < len(self.lines):
                    val = self.lines[self.idx]
                    self.idx += 1
                    return val
                raise ConnectionResetError("Connection lost mid-stream")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = FaultyStream()
        mock_resp.__enter__.return_value = mock_resp

        chunks = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(driver, "is_ollama_available", return_value=True):
                result = driver.generate(
                    "test prompt",
                    system_prompt="You are [RESEARCHER] persona",
                    stream_callback=lambda c: chunks.append(c),
                )

        assert len(chunks) > 0
        assert "Task" in result or "RAM" in result

    def test_orchestrator_multi_retry_debugger_stream_sequence(self):
        """Verify stream sequence when 3 debug retries occur."""
        class Fail3TimesDriver(LLMDriver):
            def __init__(self):
                super().__init__(mock_mode=True)
                self.debug_count = 0

            def generate(self, prompt, system_prompt=None, temperature=0.2, stream_callback=None):
                sys_lower = (system_prompt or "").lower()
                if "coder" in sys_lower:
                    text = "```python\ndef fail_code(:\n    pass\n```"
                elif "debugger" in sys_lower:
                    self.debug_count += 1
                    if self.debug_count < 3:
                        text = f"```python\ndef fail_code_{self.debug_count}(:\n    pass\n```"
                    else:
                        text = "```python\ndef fixed_code():\n    return 'success'\n```"
                else:
                    return super().generate(prompt, system_prompt, stream_callback=stream_callback)

                if stream_callback:
                    stream_callback(text)
                return text

        driver = Fail3TimesDriver()
        orchestrator = Orchestrator(driver=driver, max_retries=3)

        streamed_personas = []
        res = orchestrator.execute_pipeline(
            user_prompt="Repair test 3 times",
            language="python",
            token_stream_callback=lambda p, c: streamed_personas.append(p),
        )

        assert res.success is True
        assert res.attempts == 4  # Initial + 3 retries
        assert driver.debug_count == 3

        # Count occurrences of each persona streamed
        assert streamed_personas.count(Persona.RESEARCHER) >= 1
        assert streamed_personas.count(Persona.ARCHITECT) >= 1
        assert streamed_personas.count(Persona.CODER) >= 1
        assert streamed_personas.count(Persona.CRITIC) >= 1
        assert streamed_personas.count(Persona.DEBUGGER) == 3

    @pytest.mark.parametrize("target_persona", [
        Persona.RESEARCHER,
        Persona.ARCHITECT,
        Persona.CODER,
        Persona.CRITIC,
    ])
    def test_orchestrator_stream_exception_on_each_persona(self, target_persona):
        """Verify that raising an exception during any persona phase immediately stops pipeline."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        class StopPhaseException(Exception):
            pass

        def fail_on_persona(persona: Persona, chunk: str):
            if persona == target_persona:
                raise StopPhaseException(f"Stopped on {persona.value}")

        with pytest.raises(StopPhaseException, match=f"Stopped on {target_persona.value}"):
            orchestrator.execute_pipeline(
                user_prompt="Test early abort",
                language="python",
                token_stream_callback=fail_on_persona,
            )

    def test_orchestrator_state_isolation_between_runs(self):
        """Verify consecutive pipeline runs do not cross-contaminate streamed events."""
        driver = LLMDriver(mock_mode=True)
        orchestrator = Orchestrator(driver=driver)

        run1_events = []
        run2_events = []

        res1 = orchestrator.execute_pipeline(
            "Prompt 1",
            token_stream_callback=lambda p, c: run1_events.append((p, c)),
        )
        res2 = orchestrator.execute_pipeline(
            "Prompt 2",
            token_stream_callback=lambda p, c: run2_events.append((p, c)),
        )

        assert res1.success is True
        assert res2.success is True
        assert len(run1_events) > 0
        assert len(run2_events) > 0
        assert len(res1.history) == 4
        assert len(res2.history) == 4

