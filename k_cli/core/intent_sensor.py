"""
intent_sensor.py - Real-Time Zero-Latency User Intent Sensor & Adaptive Router for K-CLI
Project Bankai v1.0.0

Classifies user prompts in microseconds (<0.1ms) into high-level operational intents:
1. CHAT / CONVERSATION: Direct ultra-fast streaming response without heavy agent tool overhead.
2. PLAN / ARCHITECTURE: Generates step-by-step milestone execution blueprints.
3. BUILD / CODE: Full agentic code generator with surgical AST verification and test execution.
4. TRIAGE / CRASH: Instant stack trace diagnosis and incident auto-healing.
5. IMMUNITY / CHAOS: Edge-case resilience probing and defensive inoculation.
6. EXPLAIN / KNOWLEDGE: Semantic codebase & devdocs retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class UserIntent(str, Enum):
    CHAT = "chat"          # Casual conversation, greetings, simple Q&A
    PLAN = "plan"          # Strategy, architectural design, milestones
    BUILD = "build"        # Writing new code, features, refactoring
    TRIAGE = "triage"      # Debugging errors, stack traces, exceptions
    IMMUNITY = "immunity"  # Chaos edge-cases, security audits
    EXPLAIN = "explain"    # Codebase walkthrough, concept explanations


class ExecutionStrategy(str, Enum):
    DIRECT_FAST_STREAM = "direct_fast_stream"  # Sub-second streaming, bypasses heavy tool chain
    PLANNING_BLUEPRINT = "planning_blueprint"  # Structured blueprint generation
    FULL_AGENTIC_BUILD = "full_agentic_build"  # Full multi-turn verification loop
    INCIDENT_AUTOHEAL = "incident_autoheal"    # Root cause analysis & surgical repair
    CHAOS_INOCULATION = "chaos_inoculation"    # AST chaos probe & test generator


@dataclass
class IntentSensorResult:
    intent: UserIntent
    confidence: float
    mode_label: str
    execution_strategy: ExecutionStrategy
    skip_heavy_tools: bool
    reasoning: str


class IntentSensor:
    """
    Sub-millisecond heuristic intent classifier for adaptive routing.
    """

    # Regex patterns for fast-path detection
    CHAT_GREETINGS = re.compile(
        r"^(hi|hello|hey|hey there|yo|greetings|howdy|sup|what's up|good (morning|afternoon|evening)|who are you|what is your name|how are you|how's it going|what can you do|thanks|thank you|thanks a lot|cool|awesome|great|bye|goodbye)\b",
        re.IGNORECASE,
    )

    CHAT_SIMPLE_QA = re.compile(
        r"^(what is|who is|when was|define|meaning of|tell me a joke|tell me about yourself|are you ai|are you real)\b",
        re.IGNORECASE,
    )

    PLAN_PATTERNS = re.compile(
        r"\b(plan|design|architect|roadmap|strategy|blueprint|breakdown|milestones|architecture diagram|how should we structure|best approach to|how to structure)\b",
        re.IGNORECASE,
    )

    TRIAGE_PATTERNS = re.compile(
        r"(traceback \(most recent call last\)|panic:|error:|exception:|failed with exit code|nullpointerexception|typeerror:|syntaxerror:|valueerror:|keyerror:|segmentation fault)",
        re.IGNORECASE,
    )

    IMMUNITY_PATTERNS = re.compile(
        r"\b(chaos|immunity|inoculate|brittle|edge[- ]?case|security audit|vulnerability|redos|sql injection|sanitize|hardening)\b",
        re.IGNORECASE,
    )

    EXPLAIN_PATTERNS = re.compile(
        r"\b(explain|walkthrough|how does|does (the|this|my)|is (the|this|my)|look solid|review|audit|check (my|the|this)|how to use|documentation for)\b",
        re.IGNORECASE,
    )

    BUILD_PATTERNS = re.compile(
        r"\b(build|create|implement|write|generate|add|refactor|fix|update|modify|scaffold|endpoint|api|database|write code|code up)\b",
        re.IGNORECASE,
    )

    @classmethod
    def sense(cls, prompt: str) -> IntentSensorResult:
        text = prompt.strip()
        if not text:
            return IntentSensorResult(
                intent=UserIntent.CHAT,
                confidence=1.0,
                mode_label="💬 Fast Chat",
                execution_strategy=ExecutionStrategy.DIRECT_FAST_STREAM,
                skip_heavy_tools=True,
                reasoning="Empty prompt defaults to conversational fast stream.",
            )

        # 1. Check for Crash / Triage (Highest priority if stacktrace detected)
        if cls.TRIAGE_PATTERNS.search(text):
            return IntentSensorResult(
                intent=UserIntent.TRIAGE,
                confidence=0.98,
                mode_label="🚨 Incident Auto-Heal",
                execution_strategy=ExecutionStrategy.INCIDENT_AUTOHEAL,
                skip_heavy_tools=False,
                reasoning="Detected exception stack trace or error log.",
            )

        # 2. Check for Planning / Strategy (Priority over simple question words)
        if cls.PLAN_PATTERNS.search(text) and not any(w in text.lower() for w in ("implement", "write code", "fix")):
            return IntentSensorResult(
                intent=UserIntent.PLAN,
                confidence=0.90,
                mode_label="📐 Architectural Planner",
                execution_strategy=ExecutionStrategy.PLANNING_BLUEPRINT,
                skip_heavy_tools=True,
                reasoning="Strategic planning request. Synthesizing architecture blueprint without file modifications.",
            )

        # 3. Check for Chaos / Immunity / Security
        if cls.IMMUNITY_PATTERNS.search(text):
            return IntentSensorResult(
                intent=UserIntent.IMMUNITY,
                confidence=0.92,
                mode_label="🛡️ Chaos & Security Immunity",
                execution_strategy=ExecutionStrategy.CHAOS_INOCULATION,
                skip_heavy_tools=False,
                reasoning="Chaos edge-case probing or security hardening requested.",
            )

        # 4. Check for Greetings / Chit-Chat / Quick Q&A
        if cls.CHAT_GREETINGS.match(text) or (cls.CHAT_SIMPLE_QA.match(text) and len(text.split()) < 12 and not cls.BUILD_PATTERNS.search(text)):
            return IntentSensorResult(
                intent=UserIntent.CHAT,
                confidence=0.95,
                mode_label="⚡ Instant Conversation",
                execution_strategy=ExecutionStrategy.DIRECT_FAST_STREAM,
                skip_heavy_tools=True,
                reasoning="Direct conversation query. Bypassing heavy agentic tools for sub-second latency.",
            )

        # 4. Check for Chaos / Immunity / Security
        if cls.IMMUNITY_PATTERNS.search(text):
            return IntentSensorResult(
                intent=UserIntent.IMMUNITY,
                confidence=0.92,
                mode_label="🛡️ Chaos & Security Immunity",
                execution_strategy=ExecutionStrategy.CHAOS_INOCULATION,
                skip_heavy_tools=False,
                reasoning="Chaos edge-case probing or security hardening requested.",
            )

        # 5. Check for Codebase Walkthrough / Explanations
        if cls.EXPLAIN_PATTERNS.search(text) and not any(w in text.lower() for w in ("create", "build", "write code")):
            return IntentSensorResult(
                intent=UserIntent.EXPLAIN,
                confidence=0.88,
                mode_label="📖 Codebase Q&A",
                execution_strategy=ExecutionStrategy.DIRECT_FAST_STREAM,
                skip_heavy_tools=True,
                reasoning="Explanatory Q&A query with semantic doc retrieval.",
            )

        # 6. Default to Autonomous Builder
        return IntentSensorResult(
            intent=UserIntent.BUILD,
            confidence=0.85,
            mode_label="🔨 Autonomous Builder",
            execution_strategy=ExecutionStrategy.FULL_AGENTIC_BUILD,
            skip_heavy_tools=False,
            reasoning="Engineering coding task requiring AST verification and surgical tool execution.",
        )
