"""
test_models_hub.py - Comprehensive Unit & Integration Tests for Universal Model Hub
Project Bankai Engine v1.0.0
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from k_cli.core.models_hub import (
    ModelBenchmarkResult,
    ModelHub,
    ModelProvider,
    ModelSpec,
    MODEL_CATALOG_REGISTRY,
)
from k_cli.cli import app

runner = CliRunner()


def test_model_catalog_completeness():
    """Verifies that the catalog includes leading local SLMs and cloud LLMs."""
    assert "qwen2.5-coder:1.5b" in MODEL_CATALOG_REGISTRY
    assert "gemini-2.0-flash" in MODEL_CATALOG_REGISTRY
    assert "claude-3-7-sonnet" in MODEL_CATALOG_REGISTRY
    assert "gpt-4o" in MODEL_CATALOG_REGISTRY
    assert "deepseek-reasoner" in MODEL_CATALOG_REGISTRY
    assert "llama-3.3-70b-versatile" in MODEL_CATALOG_REGISTRY
    assert "codestral-latest" in MODEL_CATALOG_REGISTRY


def test_resolve_model_exact_and_prefixed():
    """Tests resolving exact, fuzzy, and provider-prefixed model names."""
    hub = ModelHub()

    # Exact
    m1 = hub.resolve_model("qwen2.5-coder:1.5b")
    assert m1 is not None
    assert m1.provider == ModelProvider.OLLAMA

    # Prefixed
    m2 = hub.resolve_model("gemini/gemini-2.0-flash")
    assert m2 is not None
    assert m2.provider == ModelProvider.GEMINI

    # Fuzzy
    m3 = hub.resolve_model("claude-3-7")
    assert m3 is not None
    assert m3.provider == ModelProvider.ANTHROPIC

    # Dynamic custom provider
    m4 = hub.resolve_model("deepseek/custom-model-99b")
    assert m4 is not None
    assert m4.provider == ModelProvider.DEEPSEEK


def test_custom_model_registration(tmp_path):
    """Tests registering and persisting custom local endpoints to JSON."""
    cfg_file = str(tmp_path / "custom_models.json")
    hub = ModelHub(config_file=cfg_file)

    custom_spec = ModelSpec(
        id="local-vllm-mistral",
        name="Local vLLM Mistral 7B",
        provider=ModelProvider.VLLM,
        base_url="http://localhost:8000/v1",
        context_window=32768,
        is_local=True,
    )
    hub.register_model(custom_spec)

    # Re-instantiate from config
    hub2 = ModelHub(config_file=cfg_file)
    resolved = hub2.resolve_model("local-vllm-mistral")
    assert resolved is not None
    assert resolved.name == "Local vLLM Mistral 7B"
    assert resolved.provider == ModelProvider.VLLM


def test_list_models_filtering():
    """Tests listing models with local_only and provider filters."""
    hub = ModelHub()

    all_models = hub.list_models()
    assert len(all_models) >= 15

    local_models = hub.list_models(local_only=True)
    assert all(m.is_local for m in local_models)

    gemini_models = hub.list_models(provider=ModelProvider.GEMINI)
    assert all(m.provider == ModelProvider.GEMINI for m in gemini_models)
    assert len(gemini_models) >= 2


def test_benchmark_model_execution():
    """Tests model benchmark telemetry calculations."""
    hub = ModelHub()
    mock_driver = MagicMock()
    mock_driver.generate.return_value = "def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)"

    res = hub.benchmark_model("qwen2.5-coder:1.5b", prompt="fib", driver=mock_driver)
    assert isinstance(res, ModelBenchmarkResult)
    assert res.success is True
    assert res.tokens_per_second >= 0.0
    assert res.ram_rss_mb > 0.0
    assert "fib" in res.sample_output


def test_cli_models_commands():
    """Tests CLI commands: k-cli models list, test, providers."""
    # 1. List
    res_list = runner.invoke(app, ["models", "list", "--json"])
    assert res_list.exit_code == 0
    models_data = json.loads(res_list.output)
    assert len(models_data) >= 10

    # 2. Providers
    res_prov = runner.invoke(app, ["models", "providers", "--json"])
    assert res_prov.exit_code == 0
    prov_data = json.loads(res_prov.output)
    assert "ollama" in prov_data
    assert "gemini" in prov_data
    assert "anthropic" in prov_data
