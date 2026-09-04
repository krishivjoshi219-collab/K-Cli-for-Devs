"""
rate_limit_guard.py - Intelligent Rate-Limit Protection & Auto-Rotation Engine
Project Bankai Engine v1.0.0

Provides:
1. Circuit Breaker for LLM API Providers (Gemini, Claude, OpenAI, DeepSeek, Groq, Ollama).
2. Auto-detection of HTTP 429 (Too Many Requests), RESOURCE_EXHAUSTED, quota limits, and 503 outages.
3. Automatic rotation to the next active provider in the tier hierarchy with zero user disruption.
4. Cooldown management with exponential backoff and jitter.
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("k_cli.core.rate_limit_guard")


# Provider and Model Hierarchies by Capability & Cost Tier
FAST_CHAT_ROTATION_CHAIN = [
    "gemini-2.5-flash",
    "claude-3-5-haiku-20241022",
    "gpt-4o-mini",
    "deepseek-chat",
    "groq/llama-3.1-8b-instant",
    "qwen2.5-coder:1.5b",
    "bankai-7b",
    "mock",
]

FRONTIER_CODING_ROTATION_CHAIN = [
    "claude-3-7-sonnet",
    "gemini-2.5-pro",
    "gpt-4o",
    "claude-3-5-sonnet-20241022",
    "deepseek-coder",
    "gemini-2.5-flash",
    "bankai-14b",
    "qwen2.5-coder:1.5b",
    "mock",
]


@dataclass
class CircuitState:
    provider: str
    is_open: bool = False
    cooldown_until: float = 0.0
    failure_count: int = 0
    last_error: str = ""
    total_trips: int = 0


@dataclass
class RotationEvent:
    timestamp: float
    from_model: str
    to_model: str
    reason: str
    cooldown_sec: float


class RateLimitGuard:
    """
    Central Thread-Safe Rate-Limit Guard and Model Circuit Breaker.
    Protects against 429s, API quota exhaustion, and service unavailability
    by automatically rotating models and managing cooldown windows.
    """

    _instance: Optional[RateLimitGuard] = None
    _lock = threading.Lock()

    def __new__(cls) -> RateLimitGuard:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._circuits: Dict[str, CircuitState] = {}
                cls._instance._rotation_events: List[RotationEvent] = []
                cls._instance._circuit_lock = threading.Lock()
            return cls._instance

    @staticmethod
    def is_rate_limit_error(error: Union[Exception, str]) -> bool:
        """Determines whether an exception or message indicates rate limiting or quota exhaustion."""
        err_str = str(error).lower()
        
        indicators = (
            "429",
            "rate limit",
            "ratelimit",
            "too many requests",
            "resource_exhausted",
            "resourceexhausted",
            "insufficient_quota",
            "quota exceeded",
            "quota_exceeded",
            "tokens per minute",
            "requests per minute",
            "tpm limit",
            "rpm limit",
            "overloaded_error",
            "503 service unavailable",
            "server is overloaded",
            "temporarily unavailable",
        )
        return any(ind in err_str for ind in indicators)

    def _normalize_key(self, provider_or_model: str) -> str:
        k = provider_or_model.lower().strip()
        if "gemini" in k:
            return "gemini"
        elif "claude" in k or "anthropic" in k:
            return "anthropic"
        elif "gpt" in k or "openai" in k or "o1" in k or "o3" in k:
            return "openai"
        elif "deepseek" in k:
            return "deepseek"
        elif "groq" in k:
            return "groq"
        elif "ollama" in k or "qwen" in k or "bankai" in k:
            return "ollama"
        return k

    def is_available(self, provider_or_model: str) -> bool:
        """Returns True if the provider/model is healthy and not in cooldown."""
        key = self._normalize_key(provider_or_model)
        now = time.time()
        with self._circuit_lock:
            circuit = self._circuits.get(key)
            if not circuit:
                return True
            if circuit.is_open:
                if now >= circuit.cooldown_until:
                    # Cooldown expired: half-open recovery
                    circuit.is_open = False
                    logger.info(f"RateLimitGuard: Provider '{key}' cooldown expired, resetting circuit.")
                    return True
                return False
            return True

    def get_remaining_cooldown(self, provider_or_model: str) -> float:
        """Returns remaining cooldown in seconds, or 0.0 if ready."""
        key = self._normalize_key(provider_or_model)
        now = time.time()
        with self._circuit_lock:
            circuit = self._circuits.get(key)
            if circuit and circuit.is_open:
                rem = circuit.cooldown_until - now
                return max(0.0, rem)
            return 0.0

    def trip_circuit(
        self,
        provider_or_model: str,
        reason: str,
        cooldown_seconds: Optional[float] = None,
    ) -> float:
        """
        Opens the circuit breaker for the given provider/model, enforcing cooldown.
        Applies exponential backoff and jitter based on repeat failure counts.
        """
        key = self._normalize_key(provider_or_model)
        with self._circuit_lock:
            circuit = self._circuits.setdefault(key, CircuitState(provider=key))
            circuit.failure_count += 1
            circuit.total_trips += 1
            circuit.last_error = reason

            if cooldown_seconds is None:
                # Exponential backoff: base 45s * (1.5 ^ (failures - 1)) + jitter
                base = 45.0 * (1.5 ** min(circuit.failure_count - 1, 4))
                jitter = random.uniform(2.0, 10.0)
                cooldown = base + jitter
            else:
                cooldown = cooldown_seconds

            circuit.is_open = True
            circuit.cooldown_until = time.time() + cooldown
            logger.warning(
                f"RateLimitGuard: Circuit tripped for '{key}'. "
                f"Cooldown: {cooldown:.1f}s. Reason: {reason}"
            )
            return cooldown

    def record_success(self, provider_or_model: str) -> None:
        """Resets the failure counter upon successful response."""
        key = self._normalize_key(provider_or_model)
        with self._circuit_lock:
            circuit = self._circuits.get(key)
            if circuit:
                circuit.is_open = False
                circuit.failure_count = max(0, circuit.failure_count - 1)

    def log_rotation(self, from_model: str, to_model: str, reason: str, cooldown_sec: float) -> None:
        """Records a rotation event for telemetry and session stats."""
        event = RotationEvent(
            timestamp=time.time(),
            from_model=from_model,
            to_model=to_model,
            reason=reason,
            cooldown_sec=cooldown_sec,
        )
        with self._circuit_lock:
            self._rotation_events.append(event)
            if len(self._rotation_events) > 50:
                self._rotation_events.pop(0)

    def get_rotation_stats(self) -> Dict[str, Any]:
        """Returns circuit health status and rotation history."""
        with self._circuit_lock:
            now = time.time()
            active_cooldowns = {
                k: round(v.cooldown_until - now, 1)
                for k, v in self._circuits.items()
                if v.is_open and v.cooldown_until > now
            }
            return {
                "active_cooldowns": active_cooldowns,
                "total_rotations": len(self._rotation_events),
                "circuits": {
                    k: {
                        "is_open": v.is_open,
                        "failure_count": v.failure_count,
                        "total_trips": v.total_trips,
                        "last_error": v.last_error,
                    }
                    for k, v in self._circuits.items()
                },
            }


class ModelRotator:
    """
    Intelligent Model Rotator that transparently finds the next available
    working model when a rate limit, quota exhaustion, or outage occurs.
    """

    def __init__(self, guard: Optional[RateLimitGuard] = None):
        self.guard = guard or RateLimitGuard()

    def get_candidate_chain(self, current_model: str, task_type: str = "coding") -> List[str]:
        """Returns the appropriate rotation fallback hierarchy based on task type."""
        base_chain = FRONTIER_CODING_ROTATION_CHAIN if task_type == "coding" else FAST_CHAT_ROTATION_CHAIN
        # Ensure current model is first, then deduplicate
        chain = [current_model] + [m for m in base_chain if m.lower() != current_model.lower()]
        return chain

    def resolve_next_available_model(
        self,
        current_model: str,
        task_type: str = "coding",
        require_live: bool = True,
    ) -> Tuple[str, str]:
        """
        Finds the next active model in the chain that is NOT currently in cooldown.
        Returns (next_model_name, rationale).
        """
        from k_cli.core.smart_router import AdaptiveIntentRouter

        chain = self.get_candidate_chain(current_model, task_type)
        
        for candidate in chain:
            if candidate.lower() == current_model.lower() and not self.guard.is_available(candidate):
                continue
            
            # Check circuit breaker
            if not self.guard.is_available(candidate):
                rem = self.guard.get_remaining_cooldown(candidate)
                logger.debug(f"ModelRotator: Candidate '{candidate}' is in cooldown ({rem:.1f}s remaining). Skipping.")
                continue

            # Check if model has credentials or is installed
            if require_live and not AdaptiveIntentRouter.is_model_live(candidate):
                continue

            return candidate, f"Auto-rotated to '{candidate}' (healthy circuit, active credentials)"

        # Fallback to deterministic mock if all cloud and local models exhausted
        return "mock", "Deterministic fallback engine (all primary endpoints in cooldown or exhausted)"

    def execute_with_auto_rotation(
        self,
        call_fn: Callable[[str], str],
        initial_model: str,
        task_type: str = "coding",
        max_rotations: int = 4,
        on_rotation_cb: Optional[Callable[[str, str, str], None]] = None,
    ) -> Tuple[str, str, List[str]]:
        """
        Executes call_fn(model_name) with automatic rate-limit interception and model rotation.
        Returns (result_text, final_model_used, list_of_models_attempted).
        """
        current_model = initial_model
        attempted_models: List[str] = []

        for attempt in range(max_rotations + 1):
            attempted_models.append(current_model)
            try:
                # Check if model is in cooldown before calling
                if not self.guard.is_available(current_model):
                    next_model, reason = self.resolve_next_available_model(current_model, task_type)
                    if next_model != current_model:
                        if on_rotation_cb:
                            on_rotation_cb(current_model, next_model, "Provider currently cooling down")
                        current_model = next_model

                result = call_fn(current_model)
                self.guard.record_success(current_model)
                return result, current_model, attempted_models

            except Exception as exc:
                is_rate_limit = self.guard.is_rate_limit_error(exc)
                if is_rate_limit:
                    cooldown = self.guard.trip_circuit(current_model, str(exc))
                    next_model, reason = self.resolve_next_available_model(current_model, task_type)
                    
                    self.guard.log_rotation(current_model, next_model, str(exc), cooldown)
                    
                    if on_rotation_cb:
                        on_rotation_cb(
                            current_model,
                            next_model,
                            f"Rate limit / Quota exceeded (429). Cooldown: {cooldown:.0f}s. Auto-rotating."
                        )
                    
                    if next_model == current_model:
                        # No alternate candidate available
                        raise exc
                    
                    current_model = next_model
                    # Short sleep with jitter before trying next candidate
                    time.sleep(random.uniform(0.5, 1.5))
                else:
                    # Non-rate-limit exception: raise directly
                    raise exc

        raise RuntimeError(f"ModelRotator exceeded max rotations ({max_rotations}). Models attempted: {attempted_models}")


# Global Singleton Accessor
global_rate_limit_guard = RateLimitGuard()
global_model_rotator = ModelRotator(guard=global_rate_limit_guard)
