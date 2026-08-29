"""
test_llm_driver.py - Unit tests for LLMDriver multi-tier inference engine
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_root_dir = Path(__file__).parent.parent
_parent_dir = _root_dir.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

import pytest

try:
    from k_cli.core.llm_driver import LLMDriver
except ModuleNotFoundError:
    from llm_driver import LLMDriver


def test_llm_driver_mock_generation():
    driver = LLMDriver(mock_mode=True)
    res_researcher = driver.generate("test prompt", system_prompt="You are [RESEARCHER] persona")
    assert "Task" in res_researcher or "RAM" in res_researcher

    res_architect = driver.generate("test prompt", system_prompt="You are [ARCHITECT] persona")
    assert "<think>" in res_architect

    res_critic = driver.generate("test prompt", system_prompt="You are [CRITIC] persona")
    assert "VALIDATED" in res_critic

    res_debugger = driver.generate("test prompt", system_prompt="You are [DEBUGGER] persona")
    assert "```python" in res_debugger


def test_llm_driver_mock_streaming():
    driver = LLMDriver(mock_mode=True)
    tokens = []

    def callback(token: str):
        tokens.append(token)

    res = driver.generate("Write code", system_prompt="You are [CODER] persona", stream_callback=callback)
    assert len(tokens) > 0
    assert "".join(tokens) == res


def test_llm_driver_is_ollama_available_mock():
    driver = LLMDriver(mock_mode=True)
    assert driver.is_ollama_available() is True


def test_llm_driver_is_ollama_available_model_check():
    driver = LLMDriver(model_name="qwen2.5-coder:1.5b", mock_mode=False)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "models": [{"name": "qwen2.5-coder:1.5b"}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert driver.is_ollama_available() is True

    # When target model is missing from /api/tags JSON
    mock_resp_missing = MagicMock()
    mock_resp_missing.status = 200
    mock_resp_missing.read.return_value = json.dumps({
        "models": [{"name": "llama3:8b"}]
    }).encode("utf-8")
    mock_resp_missing.__enter__.return_value = mock_resp_missing

    with patch("urllib.request.urlopen", return_value=mock_resp_missing):
        assert driver.is_ollama_available() is False


def test_llm_driver_ollama_fallback_to_mock_preserves_streaming():
    driver = LLMDriver(mock_mode=False)
    tokens = []

    def callback(token: str):
        tokens.append(token)

    # Force urlopen error in _generate_ollama to trigger exception handler
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with patch.object(driver, "is_ollama_available", return_value=True):
            res = driver.generate("test prompt", system_prompt="You are [RESEARCHER] persona", stream_callback=callback)

    assert len(tokens) > 0
    assert "".join(tokens) == res
