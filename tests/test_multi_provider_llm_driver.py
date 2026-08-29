"""
test_multi_provider_llm_driver.py - Comprehensive Unit & Integration Tests for
Universal Plug-and-Play Multi-Provider LLM Driver.
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
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

import pytest

try:
    from k_cli.core.llm_driver import LLMDriver, ProviderType, _CallbackException
except ModuleNotFoundError:
    from llm_driver import LLMDriver, ProviderType, _CallbackException


# =====================================================================
# 1. Local Bankai-7B/14B GGUF via Ollama & llama.cpp HTTP Server
# =====================================================================

class TestLocalBackends:
    """Tests for local Ollama and llama.cpp HTTP server backends."""

    def test_ollama_bankai_models_detection(self):
        driver = LLMDriver(model_name="bankai-7b", mock_mode=False)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "models": [{"name": "bankai-7b:latest"}, {"name": "bankai-14b:latest"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_ollama_available() is True

        driver_14b = LLMDriver(model_name="bankai-14b", mock_mode=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver_14b.is_ollama_available() is True

    def test_ollama_bankai_streaming(self):
        driver = LLMDriver(model_name="bankai-7b", mock_mode=False)
        stream_chunks = [
            b'{"response": "def ", "done": false}\n',
            b'{"response": "bankai_solution():\\n", "done": false}\n',
            b'{"response": "    return 42", "done": true}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = stream_chunks
        mock_resp.__enter__.return_value = mock_resp

        tokens = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch.object(driver, "is_ollama_available", return_value=True):
                res = driver.generate("Implement bankai function", stream_callback=lambda t: tokens.append(t))

        assert res == "def bankai_solution():\n    return 42"
        assert "".join(tokens) == res

    def test_llamacpp_server_availability_check(self):
        driver = LLMDriver(llamacpp_url="http://localhost:8080", mock_mode=False)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert driver.is_llamacpp_available() is True

        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("Offline")):
            assert driver.is_llamacpp_available() is False

    def test_llamacpp_streaming_chat_completions(self):
        driver = LLMDriver(llamacpp_url="http://localhost:8080", mock_mode=False, provider="llamacpp")
        sse_lines = [
            b'data: {"choices": [{"delta": {"content": "import "}}]}\n',
            b'data: {"choices": [{"delta": {"content": "math"}}]}\n',
            b'data: [DONE]\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = sse_lines
        mock_resp.__enter__.return_value = mock_resp

        tokens = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = driver.generate("import math", stream_callback=lambda t: tokens.append(t))

        assert res == "import math"
        assert "".join(tokens) == "import math"

    def test_llamacpp_legacy_completion_fallback_on_404(self):
        driver = LLMDriver(llamacpp_url="http://localhost:8080", mock_mode=False, provider="llamacpp")

        http_404 = urllib.error.HTTPError(
            url="http://localhost:8080/v1/chat/completions",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        mock_legacy_resp = MagicMock()
        mock_legacy_resp.status = 200
        mock_legacy_resp.read.return_value = json.dumps({"content": "def legacy_func(): pass"}).encode("utf-8")
        mock_legacy_resp.__enter__.return_value = mock_legacy_resp

        def fake_urlopen(req, timeout=60.0):
            if "/v1/chat/completions" in req.full_url:
                raise http_404
            return mock_legacy_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = driver._generate_llamacpp("test prompt", system_prompt="system")
            assert res == "def legacy_func(): pass"


def test_openai_compatible_provider_uses_custom_endpoint():
    driver = LLMDriver(
        model_name="custom-coder",
        provider="openai-compatible",
        openai_api_key="test-token",
        openai_base_url="https://models.example/v1",
        mock_mode=False,
    )
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "custom endpoint response"}}]}
    ).encode("utf-8")
    response.__enter__.return_value = response

    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        assert driver.generate("write code") == "custom endpoint response"

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://models.example/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-token"


def test_custom_adapter_registration():
    from k_cli.core.llm_driver import register_adapter

    def fake_adapter(prompt, system_prompt="", temperature=0.2, stream_callback=None):
        if stream_callback:
            stream_callback("custom ")
            stream_callback("adapter")
        return "custom adapter generated code"

    register_adapter("genblaze_custom", fake_adapter)
    driver = LLMDriver(model_name="genblaze-model", provider="genblaze_custom", mock_mode=False)

    tokens = []
    result = driver.generate("test task", stream_callback=tokens.append)
    assert result == "custom adapter generated code"
    assert tokens == ["custom ", "adapter"]


# =====================================================================
# 2. Google Gemini Backend (Gemini 3.7 Flash, 1.5 Pro, Thinking Budgets)
# =====================================================================

class TestGeminiBackend:
    """Tests for Google Gemini integration."""

    def test_gemini_streaming_and_thinking_budget(self):
        driver = LLMDriver(
            model_name="gemini-3.7-flash",
            gemini_api_key="mock-gemini-key",
            thinking_budget=4096,
            mock_mode=False,
            provider="gemini",
        )
        assert driver.is_gemini_available() is True
        assert driver.thinking_budget == 4096

        sse_lines = [
            b'data: {"candidates": [{"content": {"parts": [{"text": "```python\\n"}]}}]}\n',
            b'data: {"candidates": [{"content": {"parts": [{"text": "print(\'gemini 3.7\')\\n"}]}}]}\n',
            b'data: {"candidates": [{"content": {"parts": [{"text": "```"}]}}]}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = sse_lines
        mock_resp.__enter__.return_value = mock_resp

        recorded_req = None

        def fake_urlopen(req, timeout=60.0):
            nonlocal recorded_req
            recorded_req = req
            return mock_resp

        tokens = []
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = driver.generate("Code prompt", stream_callback=lambda t: tokens.append(t))

        assert res == "```python\nprint('gemini 3.7')\n```"
        assert "".join(tokens) == res
        assert recorded_req is not None
        assert "models/gemini-3.7-flash:streamGenerateContent" in recorded_req.full_url
        assert "key=mock-gemini-key" in recorded_req.full_url

        # Verify thinking budget in json payload
        payload = json.loads(recorded_req.data.decode("utf-8"))
        assert payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 4096

    def test_gemini_non_streaming_generation(self):
        driver = LLMDriver(
            model_name="gemini-1.5-pro",
            gemini_api_key="mock-gemini-key",
            mock_mode=False,
            provider="gemini",
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "candidates": [
                {"content": {"parts": [{"text": "gemini 1.5 pro output"}]}}
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = driver.generate("Code prompt", stream_callback=None)

        assert res == "gemini 1.5 pro output"


# =====================================================================
# 3. Anthropic Claude Backend (Claude 3.7 Sonnet, Claude 3.5 Haiku)
# =====================================================================

class TestAnthropicBackend:
    """Tests for Anthropic Claude integration."""

    def test_claude_streaming_and_thinking(self):
        driver = LLMDriver(
            model_name="claude-3-7-sonnet-20250219",
            anthropic_api_key="mock-claude-key",
            thinking_budget=2048,
            mock_mode=False,
            provider="anthropic",
        )
        assert driver.is_anthropic_available() is True

        sse_lines = [
            b'event: content_block_delta\n',
            b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "def "}}\n',
            b'event: content_block_delta\n',
            b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "solve(): return True"}}\n',
            b'event: message_stop\n',
            b'data: {"type": "message_stop"}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = sse_lines
        mock_resp.__enter__.return_value = mock_resp

        recorded_req = None

        def fake_urlopen(req, timeout=60.0):
            nonlocal recorded_req
            recorded_req = req
            return mock_resp

        tokens = []
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = driver.generate("solve problem", stream_callback=lambda t: tokens.append(t))

        assert res == "def solve(): return True"
        assert "".join(tokens) == res
        assert recorded_req.headers["X-api-key"] == "mock-claude-key"

        payload = json.loads(recorded_req.data.decode("utf-8"))
        assert payload["thinking"]["budget_tokens"] == 2048
        assert payload["temperature"] == 1.0

    def test_claude_non_streaming(self):
        driver = LLMDriver(
            model_name="claude-3-5-haiku",
            anthropic_api_key="mock-claude-key",
            mock_mode=False,
            provider="anthropic",
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "content": [{"type": "text", "text": "haiku response"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = driver.generate("quick task")

        assert res == "haiku response"


# =====================================================================
# 4. OpenAI / DeepSeek / OpenRouter Compatible Endpoints
# =====================================================================

class TestOpenAICompatibleBackends:
    """Tests for OpenAI, DeepSeek, and OpenRouter endpoints."""

    def test_openai_chat_streaming(self):
        driver = LLMDriver(
            model_name="gpt-4o",
            openai_api_key="mock-openai-key",
            mock_mode=False,
            provider="openai",
        )
        assert driver.is_openai_available() is True

        sse_lines = [
            b'data: {"choices": [{"delta": {"content": "GPT-4o "}}]}\n',
            b'data: {"choices": [{"delta": {"content": "solution"}}]}\n',
            b'data: [DONE]\n',
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = sse_lines
        mock_resp.__enter__.return_value = mock_resp

        tokens = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = driver.generate("Solve", stream_callback=lambda t: tokens.append(t))

        assert res == "GPT-4o solution"
        assert "".join(tokens) == res

    def test_deepseek_reasoner_endpoint(self):
        driver = LLMDriver(
            model_name="deepseek-reasoner",
            deepseek_api_key="mock-deepseek-key",
            mock_mode=False,
            provider="deepseek",
        )
        assert driver.is_deepseek_available() is True

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "DeepSeek code output"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        recorded_req = None

        def fake_urlopen(req, timeout=60.0):
            nonlocal recorded_req
            recorded_req = req
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = driver.generate("Code query")

        assert res == "DeepSeek code output"
        assert "api.deepseek.com" in recorded_req.full_url
        assert recorded_req.headers["Authorization"] == "Bearer mock-deepseek-key"

    def test_openrouter_endpoint_with_headers(self):
        driver = LLMDriver(
            model_name="openrouter/anthropic/claude-3.7-sonnet",
            openrouter_api_key="mock-or-key",
            mock_mode=False,
            provider="openrouter",
        )
        assert driver.is_openrouter_available() is True

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "OpenRouter router response"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        recorded_req = None

        def fake_urlopen(req, timeout=60.0):
            nonlocal recorded_req
            recorded_req = req
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = driver.generate("OpenRouter query")

        assert res == "OpenRouter router response"
        assert recorded_req.headers["Http-referer"] == "https://github.com/k-cli"
        assert recorded_req.headers["X-title"] == "K-CLI Engine"


# =====================================================================
# 5. Auto-Fallback Routing & Resilience
# =====================================================================

class TestAutoFallbackHierarchy:
    """Tests for multi-tier auto fallback and failover resilience."""

    def test_primary_provider_detection(self, monkeypatch):
        # Gemini model
        d_gem = LLMDriver(model_name="gemini-3.7-flash", gemini_api_key="key", mock_mode=False)
        assert d_gem.detect_primary_provider() == "gemini"

        # Claude model
        d_claude = LLMDriver(model_name="claude-3-7-sonnet", anthropic_api_key="key", mock_mode=False)
        assert d_claude.detect_primary_provider() == "anthropic"

        # OpenAI model
        d_openai = LLMDriver(model_name="gpt-4o", openai_api_key="key", mock_mode=False)
        assert d_openai.detect_primary_provider() == "openai"

        # DeepSeek model
        d_ds = LLMDriver(model_name="deepseek-coder", deepseek_api_key="key", mock_mode=False)
        assert d_ds.detect_primary_provider() == "deepseek"

        # OpenRouter model
        d_or = LLMDriver(model_name="openrouter/qwen/qwen-2.5-coder", openrouter_api_key="key", mock_mode=False)
        assert d_or.detect_primary_provider() == "openrouter"

    def test_offline_ollama_falls_back_to_gemini_cloud(self):
        """When local Ollama is offline, driver seamlessly fails over to available Gemini cloud backend."""
        driver = LLMDriver(
            model_name="qwen2.5-coder:1.5b",
            gemini_api_key="mock-gemini-key",
            mock_mode=False,
        )

        mock_gemini_resp = MagicMock()
        mock_gemini_resp.status = 200
        mock_gemini_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "def cloud_gemini_fallback(): pass"}]}}]
        }).encode("utf-8")
        mock_gemini_resp.__enter__.return_value = mock_gemini_resp

        with patch.object(driver, "is_ollama_available", return_value=False):
            with patch.object(driver, "is_llamacpp_available", return_value=False):
                with patch.object(driver, "get_native_llama", return_value=None):
                    with patch("urllib.request.urlopen", return_value=mock_gemini_resp):
                        res = driver.generate("Write code")
                        assert res == "def cloud_gemini_fallback(): pass"
                        assert driver._last_used_provider == "gemini"

    def test_all_cloud_and_local_offline_falls_back_to_mock_safely(self):
        """When all external APIs are unreachable, driver falls back to deterministic mock without crashing."""
        driver = LLMDriver(
            model_name="bankai-7b",
            openai_api_key="failing-key",
            mock_mode=False,
        )

        with patch.object(driver, "is_ollama_available", return_value=False):
            with patch.object(driver, "is_llamacpp_available", return_value=False):
                with patch.object(driver, "get_native_llama", return_value=None):
                    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("All APIs down")):
                        tokens = []
                        res = driver.generate("Calculate RAM", stream_callback=lambda t: tokens.append(t))

                        assert "psutil" in res
                        assert len(tokens) > 0
                        assert "".join(tokens) == res
                        assert driver._last_used_provider == "mock"

    def test_callback_exception_does_not_mask_as_fallback(self):
        """Verify that an exception raised by the stream_callback bubbles immediately without triggering fallback."""
        driver = LLMDriver(
            model_name="bankai-7b",
            mock_mode=True,
        )

        class CustomAbort(Exception):
            pass

        def aborting_callback(token: str):
            raise CustomAbort("User aborted stream")

        with pytest.raises(CustomAbort, match="User aborted stream"):
            driver.generate("Generate script", stream_callback=aborting_callback)
