"""
smart_router.py - Cost & Latency Smart Model Router for K-CLI
Project Bankai v1.0.0

Analyzes task complexity, required reasoning depth, and context size, then
dynamically routes queries to the optimal local SLM or cloud LLM, calculating
and logging cumulative financial savings against a baseline model.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from k_cli.core.llm_driver import LLMDriver, ProviderType
from k_cli.core.models_hub import ModelHub, ModelProvider, ModelSpec

logger = logging.getLogger("k_cli.core.smart_router")


class TaskTier(str, Enum):
    TRIVIAL = "trivial"      # Docstrings, typos, formatting -> Local SLM (Ollama, FREE)
    STANDARD = "standard"    # Standard functions, bug fixes -> Fast Cloud/Local (Groq/DeepSeek)
    COMPLEX = "complex"      # Full multi-file refactors, security, AST -> Claude Sonnet / GPT-4


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

        # Complexity boosters
        if any(w in text for w in ("architecture", "refactor", "security", "distributed", "concurrency", "lock-free", "ast", "compiler", "multi-thread")):
            score += 45
        if any(w in text for w in ("red-team", "adversarial", "cryptographic", "memory leak", "race condition")):
            score += 30
        if context_length > 20000:
            score += 25

        # Simplicity reducers
        if any(w in text for w in ("typo", "docstring", "comment", "format", "rename", "add log", "hello")):
            score -= 30
        if len(task_prompt.split()) < 8 and "fix" not in text:
            score -= 15

        score = max(0, min(100, score))

        if score < 30:
            return TaskTier.TRIVIAL, score, "Low-complexity task suitable for local zero-cost SLM."
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
            selected_model = "qwen2.5-coder:1.5b"
            provider = "ollama (local)"
            cost = 0.0000
        elif tier == TaskTier.STANDARD:
            selected_model = "deepseek-coder"
            provider = "deepseek"
            cost = 0.0002
        else:
            selected_model = "claude-3-5-sonnet-20241022"
            provider = "anthropic"
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
