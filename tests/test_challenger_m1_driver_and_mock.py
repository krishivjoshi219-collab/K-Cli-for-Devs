"""
test_challenger_m1_driver_and_mock.py - Empirical Challenger 2 Test Suite for Milestone 1.

Tests:
1. LLMDriver initialization, parameter handling, and environment variable overrides.
2. is_ollama_available() mock behavior, URL parsing, and network exception resilience.
3. Multi-tier fallback hierarchy (Native llama -> Ollama -> Mock) and streaming preservation.
4. MockFailingDriver *args/**kwargs forwarding, mock_mode defaulting, and auto-debug integration.
5. Adversarial stress testing (high token volume, extreme temperatures, large prompts, rapid calls).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

_root_dir = Path(__file__).parent.parent
_tests_dir = _root_dir / "tests"
_parent_dir = _root_dir.parent

if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

import pytest

try:
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.orchestrator import Orchestrator, OrchestratorResult, Persona
    from k_cli.git.verifier import VerificationResult, Verifier
except ModuleNotFoundError:
    from llm_driver import LLMDriver
    from orchestrator import Orchestrator, OrchestratorResult, Persona
    from verifier import VerificationResult, Verifier

import test_cli
MockFailingDriver = test_cli.MockFailingDriver


class TestLLMDriverInitializationAndConfig:
    """Empirical verification of LLMDriver initialization, config, and env overrides."""

    def test_default_initialization(self):
        driver = LLMDriver()
        assert driver.model_name == "qwen2.5-coder:1.5b"
        assert driver.ollama_url == "http://localhost:11434"
        assert driver.timeout == 60.0
        assert driver.mock_mode is False
        assert driver._native_llm is None

    def test_custom_parameters_initialization(self):
        driver = LLMDriver(
            model_name="deepseek-coder:1.3b",
            ollama_url="http://192.168.1.50:11434/",
            timeout=15.0,
            mock_mode=True,
        )
        assert driver.model_name == "deepseek-coder:1.3b"
        assert driver.ollama_url == "http://192.168.1.50:11434"
        assert driver.timeout == 15.0
        assert driver.mock_mode is True

    def test_url_normalization_and_slash_stripping(self):
        d1 = LLMDriver(ollama_url="localhost:11434")
        assert d1.ollama_url == "http://localhost:11434"

        d2 = LLMDriver(ollama_url="https://remote.ollama.ai:443///")
        assert d2.ollama_url == "https://remote.ollama.ai:443"

        d3 = LLMDriver(ollama_url="http://10.0.0.1:8080/")
        assert d3.ollama_url == "http://10.0.0.1:8080"

    def test_env_var_kcli_model_override(self, monkeypatch):
        monkeypatch.setenv("KCLI_MODEL", "qwen2.5-coder:7b-instruct")
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b")
        assert driver.model_name == "qwen2.5-coder:7b-instruct"

    def test_env_var_ollama_host_override(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "remote-gpu:11434/")
        driver = LLMDriver(ollama_url="http://localhost:11434")
        assert driver.ollama_url == "http://remote-gpu:11434"

    def test_lazy_load_native_llama_graceful_failure(self):
        driver = LLMDriver()
        with patch.dict(sys.modules, {"llama_cpp": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'llama_cpp'")):
                assert driver.get_native_llama() is None


class TestIsOllamaAvailableMockAndNetwork:
    """Empirical verification of is_ollama_available() logic under all conditions."""

    def _make_mock_response(self, status: int, data: dict):
        resp = MagicMock()
        resp.status = status
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    def test_is_ollama_available_mock_mode_true_no_network(self):
        driver = LLMDriver(mock_mode=True)
        with patch("urllib.request.urlopen") as mock_urlopen:
            assert driver.is_ollama_available() is True
            assert not mock_urlopen.called

    def test_is_ollama_available_exact_model_match(self):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        mock_resp = self._make_mock_response(200, {
            "models": [{"name": "qwen2.5-coder:1.5b"}, {"name": "llama3:8b"}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is True

    def test_is_ollama_available_prefix_and_tagless_match(self):
        driver = LLMDriver(model_name="qwen2.5-coder", mock_mode=False)
        mock_resp = self._make_mock_response(200, {
            "models": [{"name": "qwen2.5-coder:1.5b"}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is True

    def test_is_ollama_available_tag_in_query_tagless_in_server(self):
        driver = LLMDriver(model_name="qwen2.5-coder:latest", mock_mode=False)
        mock_resp = self._make_mock_response(200, {
            "models": [{"name": "qwen2.5-coder"}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is True

    def test_is_ollama_available_missing_model_returns_false(self):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        mock_resp = self._make_mock_response(200, {
            "models": [{"name": "mistral:7b"}, {"name": "starcoder2:3b"}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is False

    def test_is_ollama_available_empty_model_list(self):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        mock_resp = self._make_mock_response(200, {"models": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is False

    def test_is_ollama_available_malformed_json_and_non_dict_elements(self):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        mock_resp = self._make_mock_response(200, {
            "models": [None, 12345, "string_item", {"name": ""}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is False

        mock_bad_resp = MagicMock()
        mock_bad_resp.status = 200
        mock_bad_resp.read.return_value = b"{MALFORMED_JSON"
        mock_bad_resp.__enter__.return_value = mock_bad_resp
        with patch("urllib.request.urlopen", return_value=mock_bad_resp):
            assert driver.is_ollama_available() is False

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500, 502, 503])
    def test_is_ollama_available_http_error_statuses(self, status_code):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        mock_resp = self._make_mock_response(status_code, {"models": [{"name": "qwen2.5-coder:1.5b"}]})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is False

    @pytest.mark.parametrize("exc", [
        urllib.error.URLError("Connection refused"),
        TimeoutError("Connection timed out"),
        ConnectionRefusedError("Port closed"),
        ConnectionResetError("Reset by peer"),
    ])
    def test_is_ollama_available_network_exceptions(self, exc):
        driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert driver.is_ollama_available() is False


class TestLLMDriverFallbackHierarchy:
    """Empirical verification of Native -> Ollama -> Mock multi-tier inference."""

    def test_priority_1_native_llama_dispatch(self):
        driver = LLMDriver(mock_mode=False)
        mock_llama = MagicMock()
        mock_llama.return_value = {"choices": [{"text": "def native_func(): pass"}]}

        with patch.object(driver, "get_native_llama", return_value=mock_llama):
            res = driver.generate("Implement func")
            assert res == "def native_func(): pass"
            mock_llama.assert_called_once()

    def test_priority_2_ollama_api_dispatch(self):
        driver = LLMDriver(mock_mode=False)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"response": "def ollama_func(): pass"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch.object(driver, "get_native_llama", return_value=None):
            with patch.object(driver, "is_ollama_available", return_value=True):
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    res = driver.generate("Implement func")
                    assert res == "def ollama_func(): pass"

    def test_priority_2_ollama_streaming_dispatch(self):
        driver = LLMDriver(mock_mode=False)
        stream_lines = [
            json.dumps({"response": "def "}).encode("utf-8"),
            json.dumps({"response": "add(a, b):\n"}).encode("utf-8"),
            json.dumps({"response": "    return a + b", "done": True}).encode("utf-8"),
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = iter(stream_lines)
        mock_resp.__enter__.return_value = mock_resp

        tokens: List[str] = []
        with patch.object(driver, "get_native_llama", return_value=None):
            with patch.object(driver, "is_ollama_available", return_value=True):
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    res = driver.generate("Implement add", stream_callback=lambda t: tokens.append(t))
                    assert res == "def add(a, b):\n    return a + b"
                    assert "".join(tokens) == res

    def test_priority_2_ollama_failure_falls_back_to_mock_preserving_streaming(self):
        driver = LLMDriver(mock_mode=False)
        tokens: List[str] = []

        with patch.object(driver, "get_native_llama", return_value=None):
            with patch.object(driver, "is_ollama_available", return_value=True):
                with patch("urllib.request.urlopen", side_effect=RuntimeError("Ollama crashed mid-request")):
                    res = driver.generate(
                        "Write code",
                        system_prompt="You are [DEBUGGER] persona",
                        stream_callback=lambda t: tokens.append(t),
                    )
                    assert "```python" in res
                    assert len(tokens) > 0
                    assert "".join(tokens) == res

    def test_priority_3_mock_fallback_all_personas(self):
        driver = LLMDriver(mock_mode=False)
        with patch.object(driver, "get_native_llama", return_value=None):
            with patch.object(driver, "is_ollama_available", return_value=False):
                res_r = driver.generate("task", system_prompt="You are [RESEARCHER] persona")
                assert "Task:" in res_r or "RAM" in res_r

                res_a = driver.generate("plan", system_prompt="You are [ARCHITECT] persona")
                assert "<think>" in res_a

                res_c = driver.generate("review", system_prompt="You are [CRITIC] persona")
                assert "VALIDATED" in res_c

                res_d = driver.generate("repair", system_prompt="You are [DEBUGGER] persona")
                assert "```python" in res_d

    def test_mock_generation_prompt_routing(self):
        driver = LLMDriver(mock_mode=True)

        res_ram = driver.generate("Show RAM and memory consumption")
        assert "psutil" in res_ram
        assert "get_ram_usage_mb" in res_ram

        res_std = driver.generate("Implement binary search")
        assert "K-CLI Ground-Truth Execution Verified" in res_std

    def test_mock_streaming_token_splitting_and_reconstitution(self):
        driver = LLMDriver(mock_mode=True)
        tokens: List[str] = []

        full_text = driver.generate(
            "Write a script",
            system_prompt="You are [RESEARCHER] persona",
            stream_callback=lambda t: tokens.append(t),
        )

        assert len(tokens) > 0
        assert "".join(tokens) == full_text


class TestMockFailingDriverKwargsAndIntegration:
    """Empirical verification of MockFailingDriver kwargs handling and repair flow."""

    def test_mock_failing_driver_default_args(self):
        mfd = MockFailingDriver()
        assert mfd.mock_mode is True
        assert mfd.model_name == "qwen2.5-coder:1.5b"
        assert mfd.ollama_url == "http://localhost:11434"
        assert mfd.timeout == 60.0

    def test_mock_failing_driver_with_model_name_and_custom_kwargs(self):
        mfd = MockFailingDriver(
            model_name="custom:3b",
            ollama_url="http://127.0.0.1:11434",
            timeout=42.0,
        )
        assert mfd.model_name == "custom:3b"
        assert mfd.ollama_url == "http://127.0.0.1:11434"
        assert mfd.timeout == 42.0
        assert mfd.mock_mode is True

    def test_mock_failing_driver_positional_args(self):
        mfd = MockFailingDriver("custom:7b", "http://remote:11434", 30.0)
        assert mfd.model_name == "custom:7b"
        assert mfd.ollama_url == "http://remote:11434"
        assert mfd.timeout == 30.0
        assert mfd.mock_mode is True

    def test_mock_failing_driver_explicit_mock_mode_false(self):
        mfd = MockFailingDriver(mock_mode=False)
        assert mfd.mock_mode is False

    def test_mock_failing_driver_persona_failure_and_repair_simulation(self):
        mfd = MockFailingDriver()
        coder_res = mfd.generate("write function", system_prompt="You are [CODER] persona")
        assert "broken_func(:" in coder_res

        debugger_res = mfd.generate("fix function", system_prompt="You are [DEBUGGER] persona")
        assert "broken_func():" in debugger_res

        other_res = mfd.generate("research", system_prompt="You are [RESEARCHER] persona")
        assert "Task" in other_res or "RAM" in other_res

    def test_mock_failing_driver_orchestrator_auto_debug_loop(self):
        driver = MockFailingDriver()
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier, max_retries=3)

        streamed_events = []
        res = orchestrator.execute_pipeline(
            user_prompt="Build broken function test",
            language="python",
            token_stream_callback=lambda p, t: streamed_events.append((p, t)),
        )

        assert res.success is True
        assert res.attempts == 2
        assert res.retry_count == 1
        assert "broken_func():" in res.final_code
        assert any(h["persona"] == "DEBUGGER_attempt_1" for h in res.history)
        assert len(streamed_events) > 0


class TestAdversarialStressAndBoundaryConditions:
    """Stress tests on concurrency, boundary values, extreme parameters, and RAM."""

    def test_rapid_consecutive_invocations_stress(self):
        driver = LLMDriver(mock_mode=True)
        for i in range(50):
            res = driver.generate(f"Stress test iteration {i}", system_prompt="You are [CODER] persona")
            assert len(res) > 0

    def test_huge_prompt_input_stability(self):
        driver = LLMDriver(mock_mode=True)
        large_code = "def f():\n    return 'x'\n" * 20000  # ~400 KB text
        res = driver.generate(large_code)
        assert len(res) > 0

    def test_empty_and_none_system_prompts(self):
        driver = LLMDriver(mock_mode=True)
        res_empty = driver.generate("", system_prompt="")
        assert len(res_empty) > 0

        res_none = driver.generate("test prompt", system_prompt=None)
        assert len(res_none) > 0

    def test_extreme_temperatures(self):
        driver = LLMDriver(mock_mode=True)
        res_zero = driver.generate("test", temperature=0.0)
        res_high = driver.generate("test", temperature=2.5)
        assert len(res_zero) > 0
        assert len(res_high) > 0

    def test_memory_rss_within_budget_during_heavy_load(self):
        driver = LLMDriver(mock_mode=True)
        verifier = Verifier()
        orchestrator = Orchestrator(driver=driver, verifier=verifier, ram_budget_mb=1024.0)

        ram_start = orchestrator.get_current_ram_mb()
        for _ in range(10):
            res = orchestrator.execute_pipeline("Test pipeline memory stability", language="python")
            assert res.success is True

        ram_end = orchestrator.get_current_ram_mb()
        assert ram_end < 1024.0, f"Memory exceeded budget: {ram_end} MB"
