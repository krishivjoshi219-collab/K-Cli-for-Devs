"""
tests/test_hackathon_bedrock_and_daemon.py
Unit tests for AWS Strands Hackathon Professional Agents Track features:
1. Amazon Bedrock AgentCore deployment & OpenAPI export.
2. Background Healer Daemon.
"""

import json
import pytest
from pathlib import Path
from typer.testing import CliRunner

from k_cli.agents.agent_core import BedrockAgentCoreEngine, BedrockAgentCoreConfig
from k_cli.agents.background_daemon import BackgroundHealerDaemon
from k_cli.cli import app


@pytest.fixture
def runner():
    return CliRunner()


def test_bedrock_agent_core_export(tmp_path):
    engine = BedrockAgentCoreEngine()
    bundle_dir = engine.export_deployment_bundle(output_dir=str(tmp_path / "bundle"))
    
    assert bundle_dir.exists()
    assert (bundle_dir / "agent_config.json").exists()
    assert (bundle_dir / "openapi_schema.json").exists()
    assert (bundle_dir / "template.yaml").exists()

    schema = json.loads((bundle_dir / "openapi_schema.json").read_text(encoding="utf-8"))
    assert schema["openapi"] == "3.0.0"
    assert "/triage-and-heal" in schema["paths"]
    assert "/verify-code" in schema["paths"]


def test_cli_bedrock_export(runner, tmp_path):
    res = runner.invoke(app, ["bedrock", "export", "--output", str(tmp_path / "agentcore")])
    assert res.exit_code == 0
    assert "Amazon Bedrock AgentCore Bundle Exported" in res.output


def test_background_healer_daemon_sweep(tmp_path):
    daemon = BackgroundHealerDaemon(workspace_dir=str(tmp_path))
    assert daemon.status.is_running is False
    
    # Run a single sweep on a clean directory
    dec = daemon.run_health_sweep()
    assert daemon.status.scan_count == 1
    assert "Healthy" in daemon.status.status_summary
