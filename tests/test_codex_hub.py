"""
test_codex_hub.py - Comprehensive Unit & Modal Tests for K-CLI Codex Starting Screen
Project Bankai v1.0.0

Verifies:
1. Universal Key Auto-Detection for ANY provider (Gemini, Claude, OpenAI, DeepSeek, Groq, OpenRouter, GitHub).
2. Local Models Catalog with in-depth Pros & Cons for Coding.
3. Bankai Custom Hugging Face Models Catalog.
4. DevDocs 100% Offline Complete Documentation Downloader & Indexer.
5. Developer Preferences & Auto-Approve Permissions Engine.
6. CodexStartingModal interactive composition and callback handles.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from k_cli.core.credentials import (
    CredentialsManager,
    detect_key_type,
    DevPreferencesManager,
    SUPPORTED_KEYS,
)
from k_cli.core.model_manager import (
    ModelManager,
    list_local_coding_models,
    list_bankai_models,
    LOCAL_CODING_MODELS,
    BANKAI_CUSTOM_MODELS,
)
from k_cli.tools.doc_retriever import DocRetriever
from k_cli.tui.tui_app import (
    CodexStartingModal,
    KCliCyberWorkstation,
)


def test_universal_key_auto_detection():
    """Verifies that ANY entered API key is accurately mapped to its provider."""
    # Gemini
    k, p = detect_key_type("AIzaSyB1234567890abcdefghijklmnopqrstu")
    assert k == "GEMINI_API_KEY"
    assert "Gemini" in p

    # Claude
    k, p = detect_key_type("sk-ant-api03-1234567890abcdef")
    assert k == "ANTHROPIC_API_KEY"
    assert "Claude" in p

    # Groq
    k, p = detect_key_type("gsk_1234567890abcdefghijklmnopqrst")
    assert k == "GROQ_API_KEY"
    assert "Groq" in p

    # OpenRouter
    k, p = detect_key_type("sk-or-v1-1234567890abcdef")
    assert k == "OPENROUTER_API_KEY"
    assert "OpenRouter" in p

    # OpenAI Project Key
    k, p = detect_key_type("sk-proj-1234567890abcdef1234567890abcdef1234567890abcdef")
    assert k == "OPENAI_API_KEY"
    assert "OpenAI" in p

    # GitHub Token
    k, p = detect_key_type("ghp_1234567890abcdef1234567890abcdef1234")
    assert k == "GITHUB_TOKEN"
    assert "GitHub" in p

    # Ollama URL
    k, p = detect_key_type("http://localhost:11434")
    assert k == "OLLAMA_URL"
    assert "Ollama" in p


def test_save_any_key_persistence(tmp_path):
    """Verifies that save_any_key saves both to os.environ and credentials file."""
    with patch.object(CredentialsManager, "CRED_DIR", tmp_path), \
         patch.object(CredentialsManager, "ENV_FILE", tmp_path / "credentials.env"), \
         patch.object(CredentialsManager, "JSON_FILE", tmp_path / "credentials.json"):

        key_name, prov = CredentialsManager.save_any_key("sk-ant-test-key-12345")
        assert key_name == "ANTHROPIC_API_KEY"
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-key-12345"

        statuses = CredentialsManager.get_key_statuses()
        anthropic_stat = next(s for s in statuses if s["key"] == "ANTHROPIC_API_KEY")
        assert anthropic_stat["active"] is True


def test_local_coding_models_pros_and_cons():
    """Verifies that local models list contains coding pros and cons."""
    models = list_local_coding_models()
    assert len(models) >= 8

    # Qwen 2.5 Coder 7B
    qwen7b = next(m for m in models if m["id"] == "qwen2.5-coder:7b")
    assert "HumanEval" in " ".join(qwen7b["pros"])
    assert len(qwen7b["cons"]) > 0
    assert qwen7b["ollama_tag"] == "qwen2.5-coder:7b"

    # DeepSeek R1 7B
    ds7b = next(m for m in models if m["id"] == "deepseek-r1:7b")
    assert "Chain-of-Thought" in " ".join(ds7b["pros"])
    assert "thinking" in " ".join(ds7b["cons"]).lower() or "tokens" in " ".join(ds7b["cons"]).lower()

    # Llama 3.3 70B
    llama = next(m for m in models if m["id"] == "llama3.3:70b")
    assert "128k" in " ".join(llama["pros"]).lower() or "128k" in llama["context"].lower()


def test_bankai_hugging_face_models_catalog():
    """Verifies custom Bankai fine-tuned models list from Hugging Face."""
    bankai_models = list_bankai_models()
    assert len(bankai_models) >= 4

    b7b = next(m for m in bankai_models if m["id"] == "bankai-7b")
    assert b7b["repo_id"] == "krishivjoshi/bankai-7b"
    assert "AST" in b7b["description"]

    b10b = next(m for m in bankai_models if m["id"] == "bankai-10b")
    assert b10b["repo_id"] == "krishivjoshi/bankai-10b"


def test_doc_retriever_download_all_devdocs(tmp_path):
    """Verifies that download_all_devdocs builds local SQLite database with stdlib and official libraries."""
    test_db = tmp_path / "test_docs.db"
    retriever = DocRetriever(db_path=str(test_db))

    progress_events = []
    def on_prog(msg, pct):
        progress_events.append((msg, pct))

    res = retriever.download_all_devdocs(progress_callback=on_prog)
    assert res["success"] is True
    assert res["total_database_symbols"] > 0
    assert test_db.exists()
    assert len(progress_events) >= 2

    # Verify search against newly built database
    hits = retriever.search("asyncio Queue", limit=3)
    assert len(hits) > 0


def test_dev_preferences_manager(tmp_path):
    """Verifies developer preferences auto-approve modes and session settings."""
    cfg_file = tmp_path / "config.json"
    with patch.object(DevPreferencesManager, "CONFIG_FILE", cfg_file):
        # Default policy
        assert DevPreferencesManager.should_auto_approve("safe") is True
        assert DevPreferencesManager.should_auto_approve("write") is False

        # Set YOLO mode
        DevPreferencesManager.set("auto_approve_mode", "all")
        assert DevPreferencesManager.should_auto_approve("write") is True
        assert DevPreferencesManager.should_auto_approve("destructive") is True

        # Set Ask mode
        DevPreferencesManager.set("auto_approve_mode", "ask")
        assert DevPreferencesManager.should_auto_approve("safe") is False


def test_codex_starting_modal_structure():
    """Verifies CodexStartingModal composition and callback methods."""
    modal = CodexStartingModal()
    assert hasattr(modal, "on_universal_key_changed")
    assert hasattr(modal, "on_save_universal_key")
    assert hasattr(modal, "on_test_universal_key")
    assert hasattr(modal, "on_download_local_model")
    assert hasattr(modal, "on_download_bankai_model")
    assert hasattr(modal, "on_download_all_devdocs")
    assert hasattr(modal, "on_save_prefs")
    assert hasattr(modal, "on_done")


def test_cyber_workstation_has_codex_binding():
    """Verifies that KCliCyberWorkstation has Ctrl+O binding and action_open_codex."""
    app = KCliCyberWorkstation(show_codex_on_start=True)
    bindings = [b.key for b in app.BINDINGS]
    assert "ctrl+o" in bindings
    assert hasattr(app, "action_open_codex")
