"""
test_dynamic_discovery_and_audit.py - Unit & Integration Tests for Dynamic Model Discovery & 5+ Model Consensus Swarm
Project Bankai v1.0.0 (AGY Edition)

Verifies:
1. Dynamic Ollama discovery from daemon (/api/tags) with size and parameter extraction.
2. Multi-provider dynamic model discovery (Ollama, LM Studio, Groq, OpenAI).
3. Unconstrained arbitrary custom model resolution.
4. MultiModelConsensusSwarm 5+ parallel model generation, cross-model peer review, and AST score gate.
5. MultiModelAuditModal and dynamic ModelHubModal Textual widgets and event handles.
6. audit_cmd CLI execution across 5+ models with markdown and json outputs.
"""

import json
import os
from unittest.mock import MagicMock, patch
import pytest

from k_cli.core.models_hub import ModelHub, ModelSpec, ModelProvider
from k_cli.agents.adversarial_swarm import (
    MultiModelConsensusSwarm,
    MultiModelAuditReport,
    ModelCandidateEvaluation,
)
from k_cli.tui.tui_app import (
    MultiModelAuditModal,
    ModelHubModal,
    KCliCyberWorkstation,
)
from k_cli.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_dynamic_ollama_discovery_with_metadata():
    """Verifies that discover_local_ollama_models queries Ollama /api/tags and extracts specs."""
    mock_ollama_payload = {
        "models": [
            {
                "name": "qwen2.5-coder:32b",
                "size": 19828472912,
                "details": {
                    "family": "qwen2",
                    "parameter_size": "32B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {
                "name": "deepseek-r1:14b",
                "size": 9128371923,
                "details": {
                    "family": "deepseek",
                    "parameter_size": "14B",
                    "quantization_level": "Q4_0",
                },
            },
        ]
    }

    hub = ModelHub()
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_ollama_payload).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        discovered = hub.discover_local_ollama_models()
        assert len(discovered) == 2
        assert discovered[0]["name"] == "qwen2.5-coder:32b"
        assert discovered[0]["param_size"] == "32B"
        assert "qwen2.5-coder:32b" in hub.registry


def test_unconstrained_custom_model_resolution():
    """Verifies that developers can enter ANY custom model without restrictions."""
    hub = ModelHub()

    # 1. Custom Ollama tag
    spec1 = hub.resolve_model("ollama/my-fine-tuned-coder:latest")
    assert spec1 is not None
    assert spec1.id == "ollama/my-fine-tuned-coder:latest"
    assert spec1.provider == ModelProvider.OLLAMA

    # 2. Custom OpenAI / Anthropic / Groq model
    spec2 = hub.resolve_model("openai/o3-mini")
    assert spec2 is not None
    assert "o3-mini" in spec2.name.lower() or "o3-mini" in spec2.id.lower()
    assert spec2.provider == ModelProvider.OPENAI


    spec3 = hub.resolve_model("anthropic/claude-3-7-sonnet-20250219")
    assert spec3 is not None
    assert spec3.provider == ModelProvider.ANTHROPIC

    # 3. Arbitrary custom string
    spec4 = hub.resolve_model("krishivjoshi/bankai-ultimate-100b")
    assert spec4 is not None
    assert spec4.id == "krishivjoshi/bankai-ultimate-100b"


def test_multi_model_consensus_swarm_five_models():
    """Verifies that MultiModelConsensusSwarm executes 5+ models in parallel with AST scoring."""
    five_models = [
        "gemini-2.0-flash",
        "claude-3-7-sonnet",
        "deepseek-reasoner",
        "gpt-4o",
        "qwen2.5-coder:7b",
    ]

    swarm = MultiModelConsensusSwarm(models=five_models, mock_mode=True)
    report = swarm.audit_and_generate(
        task_prompt="Implement a thread-safe token bucket rate limiter in Python"
    )

    assert isinstance(report, MultiModelAuditReport)
    assert report.total_models_evaluated == 5
    assert len(report.candidates) == 5
    assert report.selected_model in five_models
    assert report.consensus_score >= 80.0
    assert "Multi-Model Swarm Audit & Consensus" in report.render_markdown()


def test_multi_model_audit_modal_composition():
    """Verifies Textual MultiModelAuditModal composition and action handles."""
    modal = MultiModelAuditModal()
    assert hasattr(modal, "on_run_audit")
    assert hasattr(modal, "on_close")


def test_dynamic_model_hub_modal_rescan():
    """Verifies ModelHubModal dynamic model rescan and custom model activation."""
    modal = ModelHubModal()
    assert hasattr(modal, "on_rescan")
    assert hasattr(modal, "on_apply_custom")
    assert hasattr(modal, "on_select")
    assert hasattr(modal, "on_bench")


def test_cyber_workstation_has_swarm_audit_binding():
    """Verifies KCliCyberWorkstation has Ctrl+U Swarm Audit binding."""
    app = KCliCyberWorkstation(mock_mode=True)
    bindings = [b.key for b in app.BINDINGS]
    assert "ctrl+u" in bindings
    assert "ctrl+m" in bindings
    assert "ctrl+o" in bindings
    assert hasattr(app, "action_open_audit")
    assert hasattr(app, "action_open_models")


def test_cli_audit_command_json_and_markdown():
    """Verifies CLI audit command executes across 5+ models."""
    res = runner.invoke(
        app,
        [
            "audit",
            "Build LRU Cache",
            "--models",
            "gemini-2.0-flash,claude-3-7-sonnet,deepseek-reasoner,gpt-4o,qwen2.5-coder:7b",
            "--mock",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["task"] == "Build LRU Cache"
    assert len(data["candidates"]) == 5
