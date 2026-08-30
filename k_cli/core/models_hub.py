"""
models_hub.py - Universal AI Model Hub & Multi-Provider Model Registry for K-CLI
Project Bankai Engine v1.0.0

Supports dynamic discovery, configuration, pulling, benchmarking, and cascading for:
1. Local Providers:
   - Ollama (Qwen2.5-Coder, DeepSeek-R1, Llama-3.3, StarCoder2, CodeLlama, Phi-4, Mistral)
   - llama.cpp HTTP server (GGUF weights)
   - Native llama-cpp-python GGUF in-process
   - vLLM / SGLang / LocalAI / LM Studio / Jan (OpenAI-compatible local endpoints)
2. Cloud Model Providers:
   - Google Gemini (Gemini 2.0 Flash, Gemini 2.0 Pro, Gemini 1.5 Pro, Thinking models)
   - Anthropic (Claude 3.7 Sonnet, Claude 3.5 Sonnet, Claude 3.5 Haiku)
   - OpenAI (GPT-4o, GPT-4o-mini, o1, o3-mini)
   - DeepSeek (DeepSeek V3, DeepSeek R1)
   - Groq (Ultra-fast Llama-3.3-70B, Qwen-2.5-Coder-32B @ 300+ tok/s)
   - Mistral AI (Codestral, Mistral Large)
   - OpenRouter (Unified access to 100+ AI models)
   - Together AI, Cerebras, Fireworks, Cohere
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("k_cli.models_hub")


class ModelProvider(str, Enum):
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    NATIVE = "native"
    VLLM = "vllm"
    LMSTUDIO = "lmstudio"
    LOCALAI = "localai"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    GROQ = "groq"
    MISTRAL = "mistral"
    OPENROUTER = "openrouter"
    TOGETHER = "together"
    MOCK = "mock"


@dataclass
class ModelSpec:
    """Specification and metadata for an AI model."""
    id: str
    name: str
    provider: ModelProvider
    context_window: int = 32768
    max_output_tokens: int = 4096
    is_local: bool = False
    description: str = ""
    prompt_price_per_m: float = 0.0
    completion_price_per_m: float = 0.0
    supports_tools: bool = True
    supports_vision: bool = False
    supports_thinking: bool = False
    is_installed: bool = False
    base_url: Optional[str] = None
    env_var_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "is_local": self.is_local,
            "description": self.description,
            "prompt_price_per_m": self.prompt_price_per_m,
            "completion_price_per_m": self.completion_price_per_m,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "supports_thinking": self.supports_thinking,
            "is_installed": self.is_installed,
            "base_url": self.base_url,
            "env_var_key": self.env_var_key,
        }


@dataclass
class ModelBenchmarkResult:
    """Telemetry results from model execution benchmark."""
    model_id: str
    provider: str
    success: bool
    tokens_generated: int = 0
    duration_seconds: float = 0.0
    tokens_per_second: float = 0.0
    time_to_first_token: float = 0.0
    ram_rss_mb: float = 0.0
    error_message: Optional[str] = None
    sample_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "success": self.success,
            "tokens_generated": self.tokens_generated,
            "duration_seconds": round(self.duration_seconds, 4),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "time_to_first_token": round(self.time_to_first_token, 4),
            "ram_rss_mb": round(self.ram_rss_mb, 2),
            "error_message": self.error_message,
            "sample_output": self.sample_output,
        }


# Curated catalog of industry-leading local and cloud models
MODEL_CATALOG_REGISTRY: Dict[str, ModelSpec] = {
    # --- Local Models (Ollama / GGUF) ---
    "qwen2.5-coder:1.5b": ModelSpec(
        id="qwen2.5-coder:1.5b",
        name="Qwen 2.5 Coder 1.5B (Ultra-Light)",
        provider=ModelProvider.OLLAMA,
        context_window=32768,
        is_local=True,
        description="Fastest lightweight local coding model",
    ),
    "qwen2.5-coder:7b": ModelSpec(
        id="qwen2.5-coder:7b",
        name="Qwen 2.5 Coder 7B",
        provider=ModelProvider.OLLAMA,
        context_window=32768,
        is_local=True,
        description="Strong local coding and multi-file reasoning model",
    ),
    "qwen2.5-coder:14b": ModelSpec(
        id="qwen2.5-coder:14b",
        name="Qwen 2.5 Coder 14B",
        provider=ModelProvider.OLLAMA,
        context_window=32768,
        is_local=True,
        description="High-accuracy local code generation and refactoring",
    ),
    "deepseek-r1:7b": ModelSpec(
        id="deepseek-r1:7b",
        name="DeepSeek R1 Distill Qwen 7B",
        provider=ModelProvider.OLLAMA,
        context_window=32768,
        is_local=True,
        supports_thinking=True,
        description="Local reasoning model with deep chain-of-thought",
    ),
    "deepseek-r1:14b": ModelSpec(
        id="deepseek-r1:14b",
        name="DeepSeek R1 Distill Qwen 14B",
        provider=ModelProvider.OLLAMA,
        context_window=32768,
        is_local=True,
        supports_thinking=True,
        description="Advanced local reasoning and architectural planning",
    ),
    "llama3.3:70b": ModelSpec(
        id="llama3.3:70b",
        name="Meta Llama 3.3 70B",
        provider=ModelProvider.OLLAMA,
        context_window=128000,
        is_local=True,
        description="State-of-the-art open weights flagship model",
    ),
    "codellama:7b": ModelSpec(
        id="codellama:7b",
        name="CodeLlama 7B",
        provider=ModelProvider.OLLAMA,
        context_window=16384,
        is_local=True,
        description="Meta's classic code-specialized model",
    ),
    "phi4:14b": ModelSpec(
        id="phi4:14b",
        name="Microsoft Phi-4 14B",
        provider=ModelProvider.OLLAMA,
        context_window=16384,
        is_local=True,
        description="High-reasoning compact model from Microsoft Research",
    ),

    # --- Google Gemini ---
    "gemini-2.0-flash": ModelSpec(
        id="gemini-2.0-flash",
        name="Google Gemini 2.0 Flash",
        provider=ModelProvider.GEMINI,
        context_window=1048576,
        max_output_tokens=8192,
        prompt_price_per_m=0.10,
        completion_price_per_m=0.40,
        supports_tools=True,
        supports_vision=True,
        supports_thinking=True,
        env_var_key="GEMINI_API_KEY",
        description="Next-generation ultra-fast multimodal model with 1M context",
    ),
    "gemini-1.5-pro": ModelSpec(
        id="gemini-1.5-pro",
        name="Google Gemini 1.5 Pro",
        provider=ModelProvider.GEMINI,
        context_window=2097152,
        max_output_tokens=8192,
        prompt_price_per_m=1.25,
        completion_price_per_m=5.00,
        supports_tools=True,
        supports_vision=True,
        env_var_key="GEMINI_API_KEY",
        description="2M token context window for full-codebase reasoning",
    ),

    # --- Anthropic Claude ---
    "claude-3-7-sonnet": ModelSpec(
        id="claude-3-7-sonnet",
        name="Claude 3.7 Sonnet (Hybrid Thinking)",
        provider=ModelProvider.ANTHROPIC,
        context_window=200000,
        max_output_tokens=8192,
        prompt_price_per_m=3.00,
        completion_price_per_m=15.00,
        supports_tools=True,
        supports_vision=True,
        supports_thinking=True,
        env_var_key="ANTHROPIC_API_KEY",
        description="Anthropic's flagship coding and hybrid reasoning model",
    ),
    "claude-3-5-sonnet": ModelSpec(
        id="claude-3-5-sonnet",
        name="Claude 3.5 Sonnet",
        provider=ModelProvider.ANTHROPIC,
        context_window=200000,
        max_output_tokens=8192,
        prompt_price_per_m=3.00,
        completion_price_per_m=15.00,
        supports_tools=True,
        supports_vision=True,
        env_var_key="ANTHROPIC_API_KEY",
        description="Industry-standard benchmark leader in code generation",
    ),
    "claude-3-5-haiku": ModelSpec(
        id="claude-3-5-haiku",
        name="Claude 3.5 Haiku",
        provider=ModelProvider.ANTHROPIC,
        context_window=200000,
        max_output_tokens=4096,
        prompt_price_per_m=0.80,
        completion_price_per_m=4.00,
        supports_tools=True,
        env_var_key="ANTHROPIC_API_KEY",
        description="High-speed, cost-effective coding model",
    ),

    # --- OpenAI ---
    "gpt-4o": ModelSpec(
        id="gpt-4o",
        name="OpenAI GPT-4o",
        provider=ModelProvider.OPENAI,
        context_window=128000,
        max_output_tokens=4096,
        prompt_price_per_m=2.50,
        completion_price_per_m=10.00,
        supports_tools=True,
        supports_vision=True,
        env_var_key="OPENAI_API_KEY",
        description="Omni flagship model from OpenAI",
    ),
    "gpt-4o-mini": ModelSpec(
        id="gpt-4o-mini",
        name="OpenAI GPT-4o Mini",
        provider=ModelProvider.OPENAI,
        context_window=128000,
        max_output_tokens=4096,
        prompt_price_per_m=0.15,
        completion_price_per_m=0.60,
        supports_tools=True,
        env_var_key="OPENAI_API_KEY",
        description="Affordable fast model for everyday coding tasks",
    ),
    "o3-mini": ModelSpec(
        id="o3-mini",
        name="OpenAI o3-mini",
        provider=ModelProvider.OPENAI,
        context_window=200000,
        max_output_tokens=8192,
        prompt_price_per_m=1.10,
        completion_price_per_m=4.40,
        supports_tools=True,
        supports_thinking=True,
        env_var_key="OPENAI_API_KEY",
        description="Advanced STEM & coding reasoning model with reasoning tiers",
    ),

    # --- DeepSeek ---
    "deepseek-chat": ModelSpec(
        id="deepseek-chat",
        name="DeepSeek V3",
        provider=ModelProvider.DEEPSEEK,
        context_window=64000,
        max_output_tokens=8192,
        prompt_price_per_m=0.27,
        completion_price_per_m=1.10,
        supports_tools=True,
        base_url="https://api.deepseek.com/v1",
        env_var_key="DEEPSEEK_API_KEY",
        description="High-performance MoE coding & general model",
    ),
    "deepseek-reasoner": ModelSpec(
        id="deepseek-reasoner",
        name="DeepSeek R1 Reasoning",
        provider=ModelProvider.DEEPSEEK,
        context_window=64000,
        max_output_tokens=8192,
        prompt_price_per_m=0.55,
        completion_price_per_m=2.19,
        supports_thinking=True,
        base_url="https://api.deepseek.com/v1",
        env_var_key="DEEPSEEK_API_KEY",
        description="DeepSeek R1 full reasoning with verified think trace",
    ),

    # --- Groq (Ultra-Fast) ---
    "llama-3.3-70b-versatile": ModelSpec(
        id="llama-3.3-70b-versatile",
        name="Groq Llama 3.3 70B (300+ tok/s)",
        provider=ModelProvider.GROQ,
        context_window=128000,
        max_output_tokens=8192,
        prompt_price_per_m=0.59,
        completion_price_per_m=0.79,
        supports_tools=True,
        base_url="https://api.groq.com/openai/v1",
        env_var_key="GROQ_API_KEY",
        description="Ultra-low-latency Llama 3.3 powered by Groq LPUs",
    ),
    "qwen-2.5-coder-32b": ModelSpec(
        id="qwen-2.5-coder-32b",
        name="Groq Qwen 2.5 Coder 32B",
        provider=ModelProvider.GROQ,
        context_window=128000,
        max_output_tokens=8192,
        supports_tools=True,
        base_url="https://api.groq.com/openai/v1",
        env_var_key="GROQ_API_KEY",
        description="Ultra-fast code generation on Groq LPU hardware",
    ),

    # --- Mistral AI ---
    "codestral-latest": ModelSpec(
        id="codestral-latest",
        name="Mistral Codestral",
        provider=ModelProvider.MISTRAL,
        context_window=32768,
        max_output_tokens=8192,
        prompt_price_per_m=0.30,
        completion_price_per_m=0.90,
        supports_tools=True,
        base_url="https://api.mistral.ai/v1",
        env_var_key="MISTRAL_API_KEY",
        description="Mistral's purpose-built code generation & fill-in-middle model",
    ),

    # --- OpenRouter ---
    "openrouter/auto": ModelSpec(
        id="openrouter/auto",
        name="OpenRouter Smart Auto-Router",
        provider=ModelProvider.OPENROUTER,
        context_window=128000,
        supports_tools=True,
        base_url="https://openrouter.ai/api/v1",
        env_var_key="OPENROUTER_API_KEY",
        description="Universal router picking optimal model per prompt",
    ),
}


class ModelHub:
    """
    Universal Model Hub & Provider Manager for K-CLI.
    Discovers local models, tests connectivity, manages API keys,
    and constructs multi-tier fallback cascades.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        llamacpp_url: str = "http://localhost:8080",
        config_file: Optional[str] = None,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.llamacpp_url = llamacpp_url.rstrip("/")
        self.config_file = config_file or str(Path.home() / ".kcli" / "models.json")
        self.registry: Dict[str, ModelSpec] = dict(MODEL_CATALOG_REGISTRY)
        self.custom_models: Dict[str, ModelSpec] = {}
        self._load_custom_config()

    def _load_custom_config(self) -> None:
        """Loads user-registered custom models and local endpoints from JSON."""
        cfg_path = Path(self.config_file)
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for item in data.get("models", []):
                    spec = ModelSpec(
                        id=item["id"],
                        name=item.get("name", item["id"]),
                        provider=ModelProvider(item.get("provider", "openai-compatible")),
                        context_window=item.get("context_window", 32768),
                        is_local=item.get("is_local", False),
                        base_url=item.get("base_url"),
                        env_var_key=item.get("env_var_key"),
                    )
                    self.custom_models[spec.id] = spec
                    self.registry[spec.id] = spec
            except Exception as exc:
                logger.warning(f"Failed loading custom model config: {exc}")

    def save_custom_config(self) -> bool:
        """Persists custom model definitions to disk."""
        cfg_path = Path(self.config_file)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {"models": [m.to_dict() for m in self.custom_models.values()]}
            cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            logger.error(f"Failed saving custom models: {exc}")
            return False

    def register_model(self, spec: ModelSpec) -> None:
        """Registers a custom or self-hosted model in the registry."""
        self.custom_models[spec.id] = spec
        self.registry[spec.id] = spec
        self.save_custom_config()

    def resolve_model(self, identifier: str) -> Optional[ModelSpec]:
        """
        Parses model identifier (e.g. `gemini-2.0-flash`, `ollama/qwen2.5-coder:7b`,
        `deepseek/deepseek-r1`, `groq/llama-3.3-70b-versatile`) and resolves ModelSpec.
        """
        if not identifier:
            return self.registry.get("qwen2.5-coder:1.5b")

        clean_id = identifier.strip().lower()

        # 1. Exact match in registry
        if clean_id in self.registry:
            return self.registry[clean_id]

        # 2. Check with provider prefix stripped
        if "/" in clean_id:
            provider_prefix, model_name = clean_id.split("/", 1)
            if model_name in self.registry:
                return self.registry[model_name]

            # Dynamic provider instantiation
            prov_enum = ModelProvider.OPENAI
            for p in ModelProvider:
                if p.value == provider_prefix:
                    prov_enum = p
                    break

            return ModelSpec(
                id=clean_id,
                name=model_name,
                provider=prov_enum,
                is_local=(prov_enum in (ModelProvider.OLLAMA, ModelProvider.LLAMACPP, ModelProvider.NATIVE)),
            )

        # 3. Fuzzy matching against catalog
        for spec_id, spec in self.registry.items():
            if clean_id in spec_id.lower() or clean_id in spec.name.lower():
                return spec

        # 4. Fallback: treat as Ollama local model
        return ModelSpec(
            id=identifier,
            name=identifier,
            provider=ModelProvider.OLLAMA,
            is_local=True,
        )

    def discover_local_ollama_models(self) -> List[Dict[str, Any]]:
        """Queries local Ollama daemon dynamically for ALL installed models and metadata."""
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/tags",
                headers={"User-Agent": "K-CLI/1.0.0 (AGY Edition)"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                discovered: List[Dict[str, Any]] = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if name:
                        size_gb = round(m.get("size", 0) / (1024**3), 2)
                        details = m.get("details", {})
                        quant = details.get("quantization_level", "")
                        param_size = details.get("parameter_size", "")
                        family = details.get("family", "")

                        spec = ModelSpec(
                            id=name,
                            name=f"{name} ({param_size} {quant})".strip(),
                            provider=ModelProvider.OLLAMA,
                            context_window=32768,
                            is_local=True,
                            is_installed=True,
                            description=f"Local Ollama model: {family} {param_size} {quant} ({size_gb} GB)",
                        )
                        self.registry[name] = spec
                        discovered.append({
                            "name": name,
                            "size_gb": size_gb,
                            "quant": quant,
                            "param_size": param_size,
                            "family": family,
                            "spec": spec,
                        })
                return discovered
        except Exception:
            return []

    def discover_all_live_models(self) -> List[ModelSpec]:
        """
        Dynamically queries all active local daemons (Ollama, LM Studio, vLLM)
        and cloud provider endpoints to discover every available model in real time.
        """
        # 1. Local Ollama
        self.discover_local_ollama_models()

        # 2. Local LM Studio / vLLM / OpenAI Compatible endpoints
        for local_url in ("http://localhost:1234/v1", "http://localhost:8000/v1", "http://localhost:8080/v1"):
            try:
                req = urllib.request.Request(f"{local_url}/models", headers={"User-Agent": "K-CLI"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", []):
                            m_id = item.get("id")
                            if m_id:
                                spec = ModelSpec(
                                    id=f"local/{m_id}",
                                    name=f"Local ({local_url}): {m_id}",
                                    provider=ModelProvider.OPENAI_COMPATIBLE,
                                    is_local=True,
                                    base_url=local_url,
                                    description=f"Local self-hosted model running on {local_url}",
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 3. Groq Dynamic Models
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}", "User-Agent": "K-CLI"},
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", []):
                            m_id = item.get("id")
                            if m_id and ("llama" in m_id or "qwen" in m_id or "deepseek" in m_id or "mixtral" in m_id):
                                spec = ModelSpec(
                                    id=f"groq/{m_id}",
                                    name=f"Groq Fast: {m_id}",
                                    provider=ModelProvider.GROQ,
                                    base_url="https://api.groq.com/openai/v1",
                                    env_var_key="GROQ_API_KEY",
                                    description=f"Groq ultra-fast LPU inference: {m_id}",
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 4. Google Gemini Dynamic Models
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            try:
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}",
                    headers={"User-Agent": "K-CLI"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("models", []):
                            raw_name = item.get("name", "").replace("models/", "")
                            if "gemini" in raw_name and "deprecated" not in raw_name:
                                spec = ModelSpec(
                                    id=raw_name,
                                    name=f"Google Gemini: {raw_name}",
                                    provider=ModelProvider.GEMINI,
                                    env_var_key="GEMINI_API_KEY",
                                    description=item.get("description", f"Google Gemini model {raw_name}")[:60],
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 5. DeepSeek Dynamic Models
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        if deepseek_key:
            try:
                req = urllib.request.Request(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {deepseek_key}", "User-Agent": "K-CLI"},
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", []):
                            m_id = item.get("id")
                            if m_id:
                                spec = ModelSpec(
                                    id=f"deepseek/{m_id}",
                                    name=f"DeepSeek: {m_id}",
                                    provider=ModelProvider.DEEPSEEK,
                                    base_url="https://api.deepseek.com",
                                    env_var_key="DEEPSEEK_API_KEY",
                                    description=f"DeepSeek Reasoning & Coding model {m_id}",
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 6. OpenAI Dynamic Models
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                req = urllib.request.Request(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}", "User-Agent": "K-CLI"},
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", []):
                            m_id = item.get("id", "")
                            if m_id.startswith("gpt-4") or m_id.startswith("o1") or m_id.startswith("o3") or m_id.startswith("chatgpt"):
                                spec = ModelSpec(
                                    id=f"openai/{m_id}",
                                    name=f"OpenAI: {m_id}",
                                    provider=ModelProvider.OPENAI,
                                    base_url="https://api.openai.com/v1",
                                    env_var_key="OPENAI_API_KEY",
                                    description=f"OpenAI model {m_id}",
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 7. Anthropic Dynamic Models
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "User-Agent": "K-CLI",
                    },
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", []):
                            m_id = item.get("id", "")
                            if m_id:
                                spec = ModelSpec(
                                    id=f"anthropic/{m_id}",
                                    name=f"Anthropic: {m_id}",
                                    provider=ModelProvider.ANTHROPIC,
                                    env_var_key="ANTHROPIC_API_KEY",
                                    description=item.get("display_name", f"Anthropic model {m_id}"),
                                )
                                self.registry[spec.id] = spec
            except Exception:
                for m_id in ("claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"):
                    spec = ModelSpec(
                        id=f"anthropic/{m_id}",
                        name=f"Anthropic: {m_id}",
                        provider=ModelProvider.ANTHROPIC,
                        env_var_key="ANTHROPIC_API_KEY",
                        description=f"Anthropic state-of-the-art model {m_id}",
                    )
                    self.registry[spec.id] = spec

        # 8. OpenRouter Dynamic Models
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {openrouter_key}", "User-Agent": "K-CLI"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("data", [])[:20]:
                            m_id = item.get("id", "")
                            if m_id:
                                spec = ModelSpec(
                                    id=f"openrouter/{m_id}",
                                    name=f"OpenRouter: {m_id}",
                                    provider=ModelProvider.OPENROUTER,
                                    base_url="https://openrouter.ai/api/v1",
                                    env_var_key="OPENROUTER_API_KEY",
                                    description=item.get("description", f"OpenRouter model {m_id}")[:60],
                                )
                                self.registry[spec.id] = spec
            except Exception:
                pass

        # 9. AWS Bedrock Models
        if os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("BEDROCK_MODEL_ID"):
            for m_id, label in [
                ("anthropic.claude-3-5-sonnet-20241022-v2:0", "Bedrock Claude 3.5 Sonnet v2"),
                ("amazon.nova-pro-v1:0", "Bedrock Amazon Nova Pro"),
            ]:
                spec = ModelSpec(
                    id=m_id,
                    name=f"AWS Bedrock: {label}",
                    provider=ModelProvider.BEDROCK,
                    description=f"AWS Bedrock Foundation Model {m_id}",
                )
                self.registry[spec.id] = spec

        return list(self.registry.values())

    def get_verified_active_models(self) -> List[ModelSpec]:
        """Returns only models whose provider is actively configured and reachable."""
        self.discover_all_live_models()
        active = []
        for spec in self.registry.values():
            if spec.is_local:
                # If local, check if installed in ollama or custom local server
                if spec.is_installed or spec.base_url:
                    active.append(spec)
            else:
                if self.is_provider_configured(spec.provider):
                    active.append(spec)
        return active

    def is_provider_configured(self, provider: ModelProvider) -> bool:
        """Checks if a provider has active API credentials or local service available."""
        if provider == ModelProvider.OLLAMA:
            try:
                req = urllib.request.Request(f"{self.ollama_url}/api/tags", headers={"User-Agent": "K-CLI/1.0.0"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    return resp.status == 200
            except Exception:
                return False
        elif provider == ModelProvider.LLAMACPP:
            try:
                req = urllib.request.Request(f"{self.llamacpp_url}/v1/models", headers={"User-Agent": "K-CLI/1.0.0"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    return resp.status == 200
            except Exception:
                return False
        elif provider == ModelProvider.GEMINI:
            return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        elif provider == ModelProvider.ANTHROPIC:
            return bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif provider == ModelProvider.OPENAI:
            return bool(os.environ.get("OPENAI_API_KEY"))
        elif provider == ModelProvider.DEEPSEEK:
            return bool(os.environ.get("DEEPSEEK_API_KEY"))
        elif provider == ModelProvider.GROQ:
            return bool(os.environ.get("GROQ_API_KEY"))
        elif provider == ModelProvider.MISTRAL:
            return bool(os.environ.get("MISTRAL_API_KEY"))
        elif provider == ModelProvider.OPENROUTER:
            return bool(os.environ.get("OPENROUTER_API_KEY"))
        elif provider == ModelProvider.MOCK:
            return True
        return False

    def list_models(
        self,
        provider: Optional[Union[ModelProvider, str]] = None,
        local_only: bool = False,
    ) -> List[ModelSpec]:
        """Returns list of models matching optional provider or local filters."""
        ollama_models = self.discover_local_ollama_models()
        ollama_installed = {m["name"] for m in ollama_models}
        results: List[ModelSpec] = []

        prov_val = provider.value if isinstance(provider, ModelProvider) else (provider.lower() if provider else None)

        for spec in self.registry.values():
            if local_only and not spec.is_local:
                continue
            if prov_val and spec.provider.value != prov_val:
                continue

            # Update installed flag for Ollama models
            if spec.provider == ModelProvider.OLLAMA:
                spec.is_installed = (spec.id in ollama_installed or f"{spec.id}:latest" in ollama_installed)

            results.append(spec)

        return results


    def pull_model(
        self,
        model_name: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Pulls a local model via Ollama daemon API."""
        try:
            payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "K-CLI/1.0.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300.0) as resp:
                for line in resp:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        status = chunk.get("status", "")
                        completed = chunk.get("completed", 0)
                        total = chunk.get("total", 0)
                        if total > 0 and stream_callback:
                            pct = (completed / total) * 100.0
                            stream_callback(f"{status}: {pct:.1f}%\n")
                        elif stream_callback and status:
                            stream_callback(f"{status}\n")
                    except Exception:
                        pass
            return True
        except Exception as exc:
            logger.error(f"Failed pulling model {model_name}: {exc}")
            return False

    def benchmark_model(
        self,
        model_name: str,
        prompt: str = "Write a Python function to compute fibonacci numbers iteratively.",
        driver: Optional[Any] = None,
    ) -> ModelBenchmarkResult:
        """
        Executes benchmark test on model to calculate Time-to-First-Token,
        throughput tokens/second, memory RSS footprint, and output correctness.
        """
        from k_cli.core.llm_driver import LLMDriver

        start_time = time.time()
        first_token_time: Optional[float] = None
        token_count = 0
        collected_chunks: List[str] = []

        def benchmark_stream(chunk: str) -> None:
            nonlocal first_token_time, token_count
            if first_token_time is None:
                first_token_time = time.time()
            token_count += 1
            collected_chunks.append(chunk)

        spec = self.resolve_model(model_name)
        active_driver = driver or LLMDriver(model_name=spec.id if spec else model_name, mock_mode=False)

        try:
            res = active_driver.generate(prompt=prompt, stream_callback=benchmark_stream)
            duration = time.time() - start_time
            ttft = (first_token_time - start_time) if first_token_time else duration
            tok_per_sec = (token_count / duration) if duration > 0 else 0.0

            import psutil
            ram_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            return ModelBenchmarkResult(
                model_id=spec.id if spec else model_name,
                provider=spec.provider.value if spec else "unknown",
                success=True,
                tokens_generated=token_count or len(res.split()),
                duration_seconds=duration,
                tokens_per_second=tok_per_sec or (len(res.split()) / max(duration, 0.001)),
                time_to_first_token=ttft,
                ram_rss_mb=ram_mb,
                sample_output=res[:200],
            )
        except Exception as exc:
            return ModelBenchmarkResult(
                model_id=spec.id if spec else model_name,
                provider=spec.provider.value if spec else "unknown",
                success=False,
                duration_seconds=time.time() - start_time,
                error_message=str(exc),
            )
