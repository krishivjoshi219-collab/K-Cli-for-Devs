"""
tests/test_adaptive_smart_router.py
Unit tests for AdaptiveIntentRouter, default model pinning, and intent-specialized model resolution.
"""

import os
import pytest
from unittest.mock import patch
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.core.credentials import DevPreferencesManager, CredentialsManager
from k_cli.core.intent_sensor import IntentSensor, UserIntent
from k_cli.core.smart_router import AdaptiveIntentRouter, SmartModelRouter, TaskTier


@pytest.fixture
def runner():
    return CliRunner()


def test_default_model_get_and_set(tmp_path):
    # Set and verify default model
    DevPreferencesManager.set_default_model("bankai-14b")
    assert DevPreferencesManager.get_default_model() == "bankai-14b"

    DevPreferencesManager.set_default_model("claude-3-5-sonnet")
    assert DevPreferencesManager.get_default_model() == "claude-3-5-sonnet"


def test_adaptive_intent_router_explicit_model():
    model, reason = AdaptiveIntentRouter.resolve_model_for_prompt(
        "Build me an auth system", requested_model="deepseek-coder"
    )
    assert model == "deepseek-coder"
    assert "User-selected model" in reason


def test_adaptive_intent_router_default_mode():
    DevPreferencesManager.set_default_model("krishivjoshi/bankai-10b")
    model, reason = AdaptiveIntentRouter.resolve_model_for_prompt(
        "Explain this snippet", requested_model="default"
    )
    assert model == "krishivjoshi/bankai-10b"
    assert "user-pinned default model" in reason


def test_adaptive_intent_router_chat_fast_path():
    DevPreferencesManager.set_default_model("auto")
    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyTestKey123456789"}, clear=False):
        model, reason = AdaptiveIntentRouter.resolve_model_for_prompt("hello how are you?")
        assert "gemini" in model.lower()
        assert "Fast Chat Path" in reason


def test_adaptive_intent_router_plan_reasoning_path():
    DevPreferencesManager.set_default_model("auto")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-testkey"}, clear=False):
        model, reason = AdaptiveIntentRouter.resolve_model_for_prompt(
            "Plan the high-level distributed database architecture and schema"
        )
        assert "claude-3-5-sonnet" in model.lower()
        assert "Architectural Planner" in reason


def test_adaptive_intent_router_coding_build_path():
    DevPreferencesManager.set_default_model("auto")
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-testdeepseek"}, clear=False):
        model, reason = AdaptiveIntentRouter.resolve_model_for_prompt(
            "def implement_binary_search_tree(): pass"
        )
        assert "coder" in model.lower() or "bankai" in model.lower() or "flash" in model.lower() or "qwen" in model.lower()
        assert "Autonomous Coding" in reason


def test_smart_model_router_cost_savings():
    router = SmartModelRouter()
    dec = router.route("Hello simple docstring update")
    assert dec.tier == TaskTier.TRIVIAL
    assert dec.savings_usd >= 0.0


def test_cli_models_set_and_get_default(runner):
    res_set = runner.invoke(app, ["models", "set-default", "bankai-14b"])
    assert res_set.exit_code == 0
    assert "Default model successfully set to" in res_set.output

    res_get = runner.invoke(app, ["models", "get-default"])
    assert res_get.exit_code == 0
    assert "bankai-14b" in res_get.output
