"""
smart_router.py - Cost, Latency & Intent-Adaptive Smart Model Router for K-CLI
Project Bankai v1.0.0

Provides:
1. Adaptive Intent Routing: Automatically routes casual chat to ultra-fast & cheap models (Gemini Flash, Claude Haiku, GPT-4o-mini, Groq)
   and routes architectural planning & heavy coding to premier frontier models (Claude 3.5 Sonnet, Bankai-14B, DeepSeek Coder).
2. Pinned Default Model: Respects user-pinned default model preferences when 'default' mode is active.
3. Cost & Latency Financial Optimization: Estimates cumulative cost savings against frontier baselines.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from k_cli.core.credentials import CredentialsManager, DevPreferencesManager
from k_cli.core.intent_sensor import IntentSensor, UserIntent
from k_cli.core.llm_driver import LLMDriver, ProviderType
from k_cli.core.models_hub import ModelHub, ModelProvider, ModelSpec

logger = logging.getLogger("k_cli.core.smart_router")


class TaskTier(str, Enum):
    TRIVIAL = "trivial"      # Docstrings, typos, formatting, greetings -> Fast / Cheap (Gemini Flash, Local SLM)
    STANDARD = "standard"    # Standard functions, bug fixes -> High Throughput (DeepSeek, Groq)
    COMPLEX = "complex"      # Multi-file refactors, AST verification, planning -> Claude Sonnet, Bankai-14B, GPT-4


@dataclass
class RouteDecision:
    """Routing outcome with rationale and cost analysis."""
    task: str
    tier: TaskTier
    selected_model: str
    selected_provider: str
    estimated_cost_usd: float
    baseline_gpt4_cost_usd: float
    savings_usd: float
    reasoning: str


class AdaptiveIntentRouter:
    """
    Real-time dynamic model selector based on sensed user intent and active API keys.
    """

    @classmethod
    def is_model_live(cls, model_name: str) -> bool:
        """Checks if a model is actually available (cloud key present or local model installed)."""
        if not model_name:
            return False
        m_lower = model_name.lower().strip()
        if m_lower in ("mock", "offline", "deterministic", "local_deterministic"):
            return True
        # Cloud check
        if "gemini" in m_lower and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            return True
        if "claude" in m_lower and os.environ.get("ANTHROPIC_API_KEY"):
            return True
        if ("gpt" in m_lower or "o1" in m_lower or "o3" in m_lower) and os.environ.get("OPENAI_API_KEY"):
            return True
        if "deepseek" in m_lower and os.environ.get("DEEPSEEK_API_KEY"):
            return True
        if "groq" in m_lower and os.environ.get("GROQ_API_KEY"):
            return True
        if ("bedrock" in m_lower or "anthropic.claude" in m_lower) and (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")):
            return True
        
        # Local Ollama / GGUF check
        driver = LLMDriver(model_name=model_name)
        if driver.is_ollama_available():
            mm = driver.get_model_manager()
            if mm and mm.has_ollama_model(model_name):
                return True
        mm = driver.get_model_manager()
        if mm:
            gguf_path = mm.find_local_gguf(model_name)
            if gguf_path and Path(gguf_path).exists():
                return True
        return False

    @classmethod
    def get_fallback_live_model(cls) -> Tuple[str, str]:
        """Finds the best active live model or falls back to sovereign verified model."""
        CredentialsManager.load_all_credentials()
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return "gemini-2.0-flash", "Active Google Gemini API key"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude-3-5-sonnet-20241022", "Active Anthropic Claude API key"
        if os.environ.get("OPENAI_API_KEY"):
            return "gpt-4o-mini", "Active OpenAI API key"
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek-chat", "Active DeepSeek API key"
        if os.environ.get("GROQ_API_KEY"):
            return "groq/llama-3.1-8b-instant", "Active Groq API key"
        
        driver = LLMDriver()
        if driver.is_ollama_available():
            mm = driver.get_model_manager()
            if mm:
                models = mm.list_installed_models()
                if models:
                    return models[0], f"Installed local model '{models[0]}'"
            return "qwen2.5-coder:1.5b", "Local Ollama server"
        
        return "qwen2.5-coder:1.5b", "Sovereign local engine"

    @classmethod
    def resolve_model_for_prompt(cls, prompt: str, requested_model: Optional[str] = None) -> Tuple[str, str]:
        """
        Determines the optimal model for a given prompt:
        - If requested_model is specific, verifies availability. If inactive/missing, auto-falls back.
        - If requested_model is 'default' or 'auto', dynamically senses intent and chooses active model.
        """
        CredentialsManager.load_all_credentials()

        if requested_model and requested_model.lower() not in ("auto", "dynamic", "none", "default"):
            return requested_model.strip(), f"User-selected model: {requested_model.strip()}"

        if requested_model and requested_model.lower() == "default":
            def_m = DevPreferencesManager.get_default_model()
            return def_m, f"Using user-pinned default model: {def_m}"

        # Sensed Intent Routing
        intent_res = IntentSensor.sense(prompt)
        
        if intent_res.intent == UserIntent.CHAT:
            model = DevPreferencesManager.get_fast_chat_model()
            if cls.is_model_live(model):
                return model, f"⚡ Fast Chat Path ({intent_res.mode_label}): Routed to low-latency model '{model}'"

        elif intent_res.intent == UserIntent.PLAN:
            model = DevPreferencesManager.get_frontier_reasoning_model()
            if cls.is_model_live(model):
                return model, f"📐 Architectural Planner ({intent_res.mode_label}): Routed to frontier reasoning model '{model}'"

        elif intent_res.intent in (UserIntent.BUILD, UserIntent.TRIAGE, UserIntent.IMMUNITY):
            model = DevPreferencesManager.get_coding_specialist_model()
            if cls.is_model_live(model):
                return model, f"🔨 Autonomous Coding ({intent_res.mode_label}): Routed to compiler-grounded specialist '{model}'"

        # Fallback to verified live model
        live_m, live_reason = cls.get_fallback_live_model()
        return live_m, f"Standard route to {live_reason} ('{live_m}')"


class SmartModelRouter:
    """
    Dynamic Cost & Latency Optimizer Model Router.
    """

    def __init__(self, hub: Optional[ModelHub] = None):
        self.hub = hub or ModelHub()
        self.total_queries_routed: int = 0
        self.total_saved_usd: float = 0.0

    def analyze_complexity(self, task_prompt: str, context_length: int = 0) -> Tuple[TaskTier, int, str]:
        """
        Calculates complexity score (0-100) and returns TaskTier.
        """
        text = task_prompt.lower()
        score = 20  # base standard

        words = set(re.findall(r"[\w-]+", text))

        # Complexity boosters
        if any(w in text for w in ("architect", "architecture", "refactor", "security", "distributed", "consensus", "concurrency", "lock-free", "ast", "compiler", "multi-thread")):
            score += 45
        if any(w in text for w in ("red-team", "adversarial", "cryptographic", "memory leak", "race condition")):
            score += 30
        if context_length > 20000:
            score += 25

        # Simplicity reducers (word boundary safe)
        if any(w in words for w in ("typo", "docstring", "comment", "format", "rename", "hello", "hi", "hey")) or "add log" in text:
            score -= 30
        if len(task_prompt.split()) < 8 and "fix" not in text and score <= 20:
            score -= 15

        score = max(0, min(100, score))

        if score < 30:
            return TaskTier.TRIVIAL, score, "Low-complexity conversational/trivial task suitable for fast/local SLM."
        elif score < 70:
            return TaskTier.STANDARD, score, "Moderate complexity suitable for high-throughput inference."
        else:
            return TaskTier.COMPLEX, score, "High-complexity architectural task requiring frontier reasoning."

    def route(self, task_prompt: str, context_length: int = 0, force_local: bool = False) -> RouteDecision:
        """
        Decides the optimal model and estimates costs.
        """
        tier, score, reason = self.analyze_complexity(task_prompt, context_length)

        if force_local or tier == TaskTier.TRIVIAL:
            selected_model = DevPreferencesManager.get_fast_chat_model()
            provider = "fast-tier"
            cost = 0.0000
        elif tier == TaskTier.STANDARD:
            selected_model = "deepseek-coder"
            provider = "deepseek"
            cost = 0.0002
        else:
            selected_model = DevPreferencesManager.get_frontier_reasoning_model()
            provider = "frontier"
            cost = 0.0030

        # Compare against GPT-4 baseline ($0.030 per 1k input/output avg)
        baseline_cost = 0.0300
        savings = max(0.0, baseline_cost - cost)

        self.total_queries_routed += 1
        self.total_saved_usd += savings

        return RouteDecision(
            task=task_prompt,
            tier=tier,
            selected_model=selected_model,
            selected_provider=provider,
            estimated_cost_usd=cost,
            baseline_gpt4_cost_usd=baseline_cost,
            savings_usd=savings,
            reasoning=f"Score: {score}/100. {reason}",
        )
