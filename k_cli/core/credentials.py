"""
credentials.py - Universal Credentials, Key Auto-Detection & Preferences Manager for K-CLI
Project Bankai Engine v1.0.0

Provides multi-tier key discovery, auto-detection for ANY entered API key,
interactive terminal setup, developer preferences (auto-approve, session storage),
and persistent storage for all AI model providers and GitHub tokens.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("k_cli.core.credentials")

SUPPORTED_KEYS = [
    ("GEMINI_API_KEY", "Google Gemini API Key", "AIzaSy..."),
    ("ANTHROPIC_API_KEY", "Anthropic Claude API Key", "sk-ant-..."),
    ("OPENAI_API_KEY", "OpenAI API Key", "sk-proj-..."),
    ("DEEPSEEK_API_KEY", "DeepSeek API Key", "sk-..."),
    ("GROQ_API_KEY", "Groq Fast Inference API Key", "gsk_..."),
    ("MISTRAL_API_KEY", "Mistral AI API Key", "..."),
    ("OPENROUTER_API_KEY", "OpenRouter Multi-Model Key", "sk-or-..."),
    ("GITHUB_TOKEN", "GitHub Personal Access Token", "ghp_..."),
    ("OLLAMA_URL", "Local Ollama Endpoint URL", "http://localhost:11434"),
]


def detect_key_type(key_val: str) -> Tuple[str, str]:
    """
    Intelligently auto-detects the provider and key_name for ANY entered API key string.
    Returns (key_name, provider_display_name).
    """
    k = key_val.strip()
    if not k:
        return "UNKNOWN", "Empty Key"

    # Google Gemini
    if k.startswith("AIzaSy") or (len(k) == 39 and k.isalnum()):
        return "GEMINI_API_KEY", "Google Gemini API Key"

    # Anthropic Claude
    if k.startswith("sk-ant-"):
        return "ANTHROPIC_API_KEY", "Anthropic Claude API Key"

    # Groq
    if k.startswith("gsk_"):
        return "GROQ_API_KEY", "Groq Fast API Key"

    # OpenRouter
    if k.startswith("sk-or-"):
        return "OPENROUTER_API_KEY", "OpenRouter Multi-Model Key"

    # OpenAI Project Keys
    if k.startswith("sk-proj-") or k.startswith("sk-admin-"):
        return "OPENAI_API_KEY", "OpenAI API Key"

    # GitHub Tokens
    if k.startswith("ghp_") or k.startswith("github_pat_") or k.startswith("gho_"):
        return "GITHUB_TOKEN", "GitHub Personal Access Token"

    # Ollama URL
    if k.startswith("http://") or k.startswith("https://") or ":11434" in k:
        return "OLLAMA_URL", "Local Ollama Endpoint URL"

    # DeepSeek / Mistral / Generic OpenAI Compatible
    if k.startswith("sk-"):
        if len(k) == 35 or len(k) == 34:
            return "DEEPSEEK_API_KEY", "DeepSeek API Key"
        return "OPENAI_API_KEY", "OpenAI API Key"

    if len(k) == 32 and k.isalnum():
        return "MISTRAL_API_KEY", "Mistral AI API Key"

    return "OPENAI_API_KEY", "General / OpenAI-Compatible Key"


class CredentialsManager:
    """
    Central API Key & Credentials Store for K-CLI.
    """

    CRED_DIR = Path.home() / ".kcli"
    ENV_FILE = CRED_DIR / "credentials.env"
    JSON_FILE = CRED_DIR / "credentials.json"
    CONFIG_FILE = CRED_DIR / "config.json"

    @classmethod
    def load_all_credentials(cls) -> Dict[str, str]:
        """
        Loads all credentials into os.environ from files, environment, and common locations.
        """
        loaded: Dict[str, str] = {}

        # 1. Load from ~/.kcli/credentials.env
        if cls.ENV_FILE.exists():
            try:
                for line in cls.ENV_FILE.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k and v:
                            os.environ[k] = v
                            loaded[k] = v
            except Exception:
                pass

        # 2. Load from ~/.kcli/credentials.json
        if cls.JSON_FILE.exists():
            try:
                data = json.loads(cls.JSON_FILE.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if isinstance(v, str) and v.strip():
                        os.environ[k] = v.strip()
                        loaded[k] = v.strip()
            except Exception:
                pass

        # 3. Load from local .env / key.json if present in cwd or parents
        cwd = Path.cwd()
        candidates = [
            cwd / ".env",
            cwd / "key.json",
            cwd.parent / ".env",
            cwd.parent / "key.json",
            Path.home() / "BankaiProject" / "key.json",
            Path.home() / "BankaiProject" / "finance.key.json",
            Path.home() / ".env",
        ]
        
        KEY_ALIASES = {
            "GOOGLE_KEYS": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "GEMINI_KEYS": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "GEMINI_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "GOOGLE_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "GROQ_KEYS": ["GROQ_API_KEY"],
            "GROQ_API_KEY": ["GROQ_API_KEY"],
            "OPENROUTER_KEYS": ["OPENROUTER_API_KEY"],
            "OPENROUTER_API_KEY": ["OPENROUTER_API_KEY"],
            "DEEPSEEK_KEYS": ["DEEPSEEK_API_KEY"],
            "DEEPSEEK_API_KEY": ["DEEPSEEK_API_KEY"],
            "GITHUB_KEYS": ["GITHUB_TOKEN"],
            "GITHUB_TOKEN": ["GITHUB_TOKEN"],
            "ANTHROPIC_KEYS": ["ANTHROPIC_API_KEY"],
            "ANTHROPIC_API_KEY": ["ANTHROPIC_API_KEY"],
            "OPENAI_KEYS": ["OPENAI_API_KEY"],
            "OPENAI_API_KEY": ["OPENAI_API_KEY"],
        }

        for cand in candidates:
            if cand.exists():
                try:
                    if cand.suffix == ".json":
                        data = json.loads(cand.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            for k, v in data.items():
                                val_str = None
                                if isinstance(v, str) and v.strip():
                                    val_str = v.strip()
                                elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and v[0].strip():
                                    val_str = v[0].strip()
                                elif isinstance(v, dict):
                                    for sub_k, sub_v in v.items():
                                        if isinstance(sub_v, str) and sub_v.strip():
                                            val_str = sub_v.strip()
                                            break
                                
                                if val_str:
                                    target_keys = KEY_ALIASES.get(k.upper(), [k.upper()])
                                    for t_key in target_keys:
                                        if t_key not in loaded:
                                            loaded[t_key] = val_str
                                            if t_key not in os.environ:
                                                os.environ[t_key] = val_str
                    else:
                        for line in cand.read_text(encoding="utf-8").splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip().upper(), v.strip()
                                if v:
                                    target_keys = KEY_ALIASES.get(k, [k])
                                    for t_key in target_keys:
                                        if t_key not in loaded:
                                            loaded[t_key] = v
                                            if t_key not in os.environ:
                                                os.environ[t_key] = v
                except Exception:
                    pass

        return loaded

    @classmethod
    def set_key(cls, key_name: str, key_val: str) -> None:
        """
        Saves a single key to persistent storage and active os.environ.
        """
        key_name = key_name.strip().upper()
        key_val = key_val.strip()
        if not key_name:
            return
        os.environ[key_name] = key_val

        cls.CRED_DIR.mkdir(parents=True, exist_ok=True)
        existing = {}
        if cls.JSON_FILE.exists():
            try:
                existing = json.loads(cls.JSON_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing[key_name] = key_val
        cls.JSON_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        # Also write .env format
        env_lines = [f"{k}={v}" for k, v in existing.items() if v]
        cls.ENV_FILE.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    @classmethod
    def save_any_key(cls, raw_key_val: str, explicit_key_name: Optional[str] = None) -> Tuple[str, str]:
        """
        Takes ANY raw entered API key string, detects its type if needed, saves it, and returns (key_name, provider_name).
        """
        raw_key_val = raw_key_val.strip()
        if not raw_key_val:
            return "", ""

        if explicit_key_name:
            key_name = explicit_key_name.strip().upper()
            provider_name = dict(SUPPORTED_KEYS).get(key_name, key_name)
        else:
            key_name, provider_name = detect_key_type(raw_key_val)

        cls.set_key(key_name, raw_key_val)
        return key_name, provider_name

    @classmethod
    def get_key_statuses(cls) -> List[Dict[str, Any]]:
        """
        Returns status summary for all supported keys.
        """
        cls.load_all_credentials()
        statuses = []
        for key_name, label, placeholder in SUPPORTED_KEYS:
            val = os.environ.get(key_name, "")
            is_active = bool(val and len(val.strip()) > 0)
            masked = f"{val[:4]}...{val[-4:]}" if len(val) >= 10 else ("***" if val else "")
            statuses.append({
                "key": key_name,
                "label": label,
                "active": is_active,
                "masked": masked,
                "placeholder": placeholder,
            })
        return statuses

    @classmethod
    def test_key_connectivity(cls, key_name: str) -> Tuple[bool, str]:
        """
        Quick connectivity test for a specific provider key.
        """
        val = os.environ.get(key_name, "").strip()
        if not val and key_name != "OLLAMA_URL":
            return False, "Key missing"

        if key_name == "OLLAMA_URL":
            url = val or "http://localhost:11434"
            try:
                req = urllib.request.Request(f"{url}/api/tags", headers={"User-Agent": "K-CLI"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        return True, "Ollama running"
            except Exception as e:
                return False, f"Ollama not reachable: {e}"

        elif key_name == "GEMINI_API_KEY":
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={val}"
                req = urllib.request.Request(url, headers={"User-Agent": "K-CLI"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        return True, "Gemini connected"
            except Exception as e:
                return False, f"Auth failed ({e})"

        elif key_name == "GITHUB_TOKEN":
            try:
                req = urllib.request.Request(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {val}", "User-Agent": "K-CLI", "Accept": "application/vnd.github.v3+json"},
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        return True, "GitHub connected"
            except Exception as e:
                return False, f"GitHub auth failed ({e})"

        # Default check for others
        return True, "Key configured"


class DevPreferencesManager:
    """
    Developer Preferences & Autonomous Permissions Engine for K-CLI.
    Manages Auto-Approve modes, persistent session data, offline airgap, and workspace defaults.
    """

    CONFIG_FILE = Path.home() / ".kcli" / "config.json"

    DEFAULT_PREFERENCES: Dict[str, Any] = {
        "auto_approve_mode": "safe",  # "safe" | "all" | "ask"
        "auto_save_sessions": True,
        "auto_index_repo": True,
        "airgap_offline_mode": False,
        "default_model": "gemini-2.0-flash",
        "local_fallback_model": "qwen2.5-coder:1.5b",
        "context_token_limit": 32768,
        "verifier_strict_gate": True,
        "telemetry_logging": True,
        "theme": "cyber_dark",
    }

    @classmethod
    def load_preferences(cls) -> Dict[str, Any]:
        """Loads preferences merged with defaults."""
        prefs = dict(cls.DEFAULT_PREFERENCES)
        if cls.CONFIG_FILE.exists():
            try:
                user_data = json.loads(cls.CONFIG_FILE.read_text(encoding="utf-8"))
                prefs.update(user_data)
            except Exception:
                pass
        return prefs

    @classmethod
    def save_preferences(cls, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates and persists preferences."""
        current = cls.load_preferences()
        current.update(updates)
        cls.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            cls.CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception:
            pass
        return current

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        prefs = cls.load_preferences()
        return prefs.get(key, default if default is not None else cls.DEFAULT_PREFERENCES.get(key))

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        cls.save_preferences({key: value})

    @classmethod
    def should_auto_approve(cls, action_type: str = "safe") -> bool:
        """
        Determines whether an action should be automatically approved.
        action_type can be: "safe" (read, test, lint, AST check), "write" (file patch), "destructive" (git reset, delete).
        """
        mode = cls.get("auto_approve_mode", "safe")
        if mode == "all":
            return True
        if mode == "safe":
            return action_type in ("safe", "test", "read", "verify", "diff")
        return False
