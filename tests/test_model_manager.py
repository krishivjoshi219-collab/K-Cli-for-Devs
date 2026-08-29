"""
test_model_manager.py - Comprehensive Unit & Integration Tests for Model Bootstrapper & Auto-Sync Engine
"""

import hashlib
import json
import os
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
from typer.testing import CliRunner

from k_cli.cli import app
from k_cli.core.model_manager import (
    DEFAULT_CHATML_TEMPLATE,
    MODEL_CATALOG,
    ModelManager,
    ModelPullResult,
)
from k_cli.core.llm_driver import LLMDriver

runner = CliRunner()


# ==============================================================================
# 1. Model Catalog & Spec Resolution Tests
# ==============================================================================

def test_resolve_model_spec_bankai_7b():
    spec = ModelManager.resolve_model_spec("bankai-7b")
    assert spec["repo_id"] == "krishivjoshi/bankai-7b"
    assert spec["ollama_tag"] == "bankai:7b"
    assert "bankai-7b.gguf" in spec["default_filename"]
    assert "Bankai-7B" in spec["system_prompt"]
    assert "<|im_start|>" in spec["stop_tokens"]


def test_resolve_model_spec_bankai_10b():
    spec = ModelManager.resolve_model_spec("bankai-10b")
    assert spec["repo_id"] == "krishivjoshi/bankai-10b"
    assert spec["ollama_tag"] == "bankai:10b"
    assert "bankai-10b.gguf" in spec["default_filename"]
    assert "Bankai-10B" in spec["system_prompt"]


def test_resolve_model_spec_aliases():
    spec_7b_alias = ModelManager.resolve_model_spec("7b")
    assert spec_7b_alias["repo_id"] == "krishivjoshi/bankai-7b"

    spec_10b_alias = ModelManager.resolve_model_spec("10b")
    assert spec_10b_alias["repo_id"] == "krishivjoshi/bankai-10b"


def test_resolve_model_spec_custom_repo():
    spec_custom = ModelManager.resolve_model_spec("custom-user/custom-coder")
    assert spec_custom["repo_id"] == "custom-user/custom-coder"
    assert spec_custom["ollama_tag"] == "custom:coder"
    assert "custom-coder.gguf" in spec_custom["default_filename"]


# ==============================================================================
# 2. SHA256 Cryptographic Integrity Tests
# ==============================================================================

def test_compute_and_verify_sha256(tmp_path):
    test_binary = tmp_path / "test_model.gguf"
    test_data = b"GGUF\x03\x00\x00\x00" + b"X" * 1024 * 100
    test_binary.write_bytes(test_data)

    expected_sha = hashlib.sha256(test_data).hexdigest()
    computed_sha = ModelManager.compute_sha256(test_binary)

    assert computed_sha == expected_sha
    assert ModelManager.verify_sha256(test_binary, expected_sha)
    assert ModelManager.verify_sha256(test_binary, expected_sha.upper())
    assert not ModelManager.verify_sha256(test_binary, "invalid_hash_value_12345")


def test_compute_sha256_missing_file(tmp_path):
    non_existent = tmp_path / "does_not_exist.gguf"
    with pytest.raises(FileNotFoundError):
        ModelManager.compute_sha256(non_existent)


# ==============================================================================
# 3. Modelfile Generation & Verification Tests
# ==============================================================================

def test_generate_modelfile(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    dummy_gguf = tmp_path / "bankai-7b.gguf"
    dummy_gguf.write_bytes(b"GGUF_TEST_HEADER")

    modelfile_text = mm.generate_modelfile(dummy_gguf, model_name="bankai-7b")

    assert f"FROM {dummy_gguf.resolve()}" in modelfile_text
    assert 'TEMPLATE """<|im_start|>system' in modelfile_text
    assert 'PARAMETER stop "<|im_start|>"' in modelfile_text
    assert 'PARAMETER stop "<|im_end|>"' in modelfile_text
    assert "PARAMETER temperature 0.2" in modelfile_text
    assert "PARAMETER top_p 0.95" in modelfile_text
    assert "PARAMETER repeat_penalty 1.1" in modelfile_text
    assert 'SYSTEM """You are Bankai-7B' in modelfile_text


def test_write_modelfile(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    dummy_gguf = tmp_path / "bankai-10b.gguf"
    dummy_gguf.write_bytes(b"GGUF_TEST_HEADER_10B")

    mf_path = mm.write_modelfile(dummy_gguf, model_name="bankai-10b")

    assert mf_path.exists()
    content = mf_path.read_text(encoding="utf-8")
    assert f"FROM {dummy_gguf.resolve()}" in content
    assert "Bankai-10B" in content


# ==============================================================================
# 4. Ollama Health & Model Registration Tests
# ==============================================================================

def test_check_ollama_health_mock():
    mm = ModelManager(mock_mode=True)
    health = mm.check_ollama_health()
    assert health["healthy"] is True
    assert "qwen2.5-coder:1.5b" in health["models"]
    assert mm.is_ollama_available() is True
    assert mm.has_ollama_model("qwen2.5-coder:1.5b") is True


def test_check_ollama_health_real_mocked():
    mm = ModelManager(mock_mode=False)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "models": [{"name": "bankai:7b"}, {"name": "bankai:10b"}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        health = mm.check_ollama_health()
        assert health["healthy"] is True
        assert "bankai:7b" in health["models"]
        assert mm.has_ollama_model("bankai-7b") is True
        assert mm.has_ollama_model("bankai:10b") is True
        assert mm.has_ollama_model("nonexistent-model") is False


def test_create_ollama_model_mock(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    mf = tmp_path / "Modelfile.test"
    mf.write_text("FROM ./test.gguf\n", encoding="utf-8")

    success, msg = mm.create_ollama_model("bankai-test:latest", mf)
    assert success is True
    assert mm.has_ollama_model("bankai-test:latest") is True


# ==============================================================================
# 5. Pull Model & Environment Init Tests
# ==============================================================================

def test_pull_model_bankai_7b(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    result = mm.pull_model(
        model_identifier="bankai-7b",
        create_in_ollama=True,
        verify_sha=True,
    )

    assert result.success is True
    assert result.model_name == "bankai-7b"
    assert result.ollama_tag == "bankai:7b"
    assert result.gguf_path is not None
    assert result.gguf_path.exists()
    assert result.modelfile_path is not None
    assert result.modelfile_path.exists()
    assert result.sha256 is not None
    assert result.sha256_verified is True
    assert result.ollama_created is True


def test_pull_model_bankai_10b(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    result = mm.pull_model(
        model_identifier="bankai-10b",
        create_in_ollama=True,
        verify_sha=True,
    )

    assert result.success is True
    assert result.model_name == "bankai-10b"
    assert result.ollama_tag == "bankai:10b"
    assert result.gguf_path.exists()
    assert result.modelfile_path.exists()
    assert result.sha256_verified is True


def test_pull_model_sha256_mismatch_failure(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=False)
    dummy_gguf = tmp_path / "bankai-7b.gguf"
    dummy_gguf.write_bytes(b"SOME_GGUF_BYTES")

    # Pass an explicitly mismatched expected SHA256
    with patch.object(mm, "find_local_gguf", return_value=dummy_gguf):
        result = mm.pull_model(
            model_identifier="bankai-7b",
            expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
            verify_sha=True,
        )
        assert result.success is False
        assert result.sha256_verified is False
        assert "mismatch" in result.message.lower()


def test_pull_model_without_trusted_sha_fails_closed(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=False)
    dummy_gguf = tmp_path / "bankai-7b.gguf"
    dummy_gguf.write_bytes(b"SOME_GGUF_BYTES")

    with patch.object(mm, "find_local_gguf", return_value=dummy_gguf), \
         patch.object(mm, "fetch_hf_metadata", return_value={"lfs_sha256": {}}):
        result = mm.pull_model(
            model_identifier="bankai-7b",
            verify_sha=True,
        )

    assert result.success is False
    assert result.sha256_verified is False
    assert "trusted sha256" in result.message.lower()


def test_init_environment(tmp_path):
    mm = ModelManager(models_dir=tmp_path, mock_mode=True)
    init_res = mm.init_environment(default_model="bankai-7b", sync_model=True)

    assert init_res["ready"] is True
    assert len(init_res["directories"]) >= 5
    assert init_res["model_pull"] is not None
    assert init_res["model_pull"]["success"] is True


# ==============================================================================
# 6. CLI Commands Tests (init, pull-model, pull)
# ==============================================================================

def test_cli_init_command():
    result = runner.invoke(app, ["init", "--mock", "--model", "bankai-7b"])
    assert result.exit_code == 0
    assert "Initializing K-CLI Environment" in result.output
    assert "Directory Layout" in result.output
    assert "Ollama Inference Diagnostics" in result.output
    assert "Bankai Model Bootstrapper Status" in result.output
    assert "Ready" in result.output or "SUCCESS" in result.output


def test_cli_pull_model_7b_command():
    result = runner.invoke(app, ["pull-model", "bankai-7b", "--mock"])
    assert result.exit_code == 0
    assert "Auto-Sync Engine" in result.output
    assert "Model Identifier" in result.output
    assert "bankai-7b" in result.output
    assert "SHA256 Integrity" in result.output
    assert "SUCCESS" in result.output


def test_cli_pull_model_10b_command():
    result = runner.invoke(app, ["pull-model", "bankai-10b", "--mock"])
    assert result.exit_code == 0
    assert "bankai-10b" in result.output
    assert "SUCCESS" in result.output


def test_cli_pull_alias_command():
    result = runner.invoke(app, ["pull", "bankai-7b", "--mock"])
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


# ==============================================================================
# 7. LLMDriver ModelManager Integration Tests
# ==============================================================================

def test_llm_driver_model_manager_integration(tmp_path):
    driver = LLMDriver(model_name="bankai-7b", mock_mode=True)
    mm = driver.get_model_manager()
    assert mm is not None

    status = driver.ensure_model_ready(auto_pull=False)
    assert status["ready"] is True


def test_llm_driver_ollama_normalized_tag_matching():
    driver = LLMDriver(model_name="bankai-7b", mock_mode=False)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "models": [{"name": "bankai:7b"}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert driver.is_ollama_available() is True
