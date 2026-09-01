"""
test_intent_sensor.py - Automated Tests for K-CLI Intent Sensor & Adaptive Fast-Path Router
"""

import pytest
from k_cli.core.intent_sensor import IntentSensor, UserIntent, ExecutionStrategy


def test_intent_sensor_greetings_and_chit_chat():
    queries = [
        "hi", "hello", "hey there", "howdy!", "what's up", "who are you?",
        "what can you do", "thanks a lot", "bye"
    ]
    for q in queries:
        res = IntentSensor.sense(q)
        assert res.intent == UserIntent.CHAT, f"Failed on {q}: got {res.intent}"
        assert res.skip_heavy_tools is True
        assert res.execution_strategy == ExecutionStrategy.DIRECT_FAST_STREAM


def test_intent_sensor_crash_triage_detection():
    traceback_sample = """Traceback (most recent call last):
  File "app.py", line 12, in <module>
    res = user_db.get(user_id)
KeyError: 'user_id'"""
    res = IntentSensor.sense(traceback_sample)
    assert res.intent == UserIntent.TRIAGE
    assert res.execution_strategy == ExecutionStrategy.INCIDENT_AUTOHEAL
    assert res.skip_heavy_tools is False


def test_intent_sensor_planning_detection():
    queries = [
        "plan the refactoring of our auth module",
        "give me an architecture roadmap for microservices",
        "design a blueprint for distributed caching",
        "what is the best approach to structure our database migrations"
    ]
    for q in queries:
        res = IntentSensor.sense(q)
        assert res.intent == UserIntent.PLAN, f"Failed on {q}: got {res.intent}"
        assert res.execution_strategy == ExecutionStrategy.PLANNING_BLUEPRINT


def test_intent_sensor_chaos_and_immunity():
    queries = [
        "probe this module for edge-case chaos immunity",
        "run security vulnerability audit on user_db.py",
        "sanitize inputs against redos attacks"
    ]
    for q in queries:
        res = IntentSensor.sense(q)
        assert res.intent == UserIntent.IMMUNITY, f"Failed on {q}: got {res.intent}"
        assert res.execution_strategy == ExecutionStrategy.CHAOS_INOCULATION


def test_intent_sensor_codebase_explanations():
    queries = [
        "explain how this authentication flow works",
        "walkthrough the verifier execution pipeline"
    ]
    for q in queries:
        res = IntentSensor.sense(q)
        assert res.intent == UserIntent.EXPLAIN, f"Failed on {q}: got {res.intent}"
        assert res.skip_heavy_tools is True


def test_intent_sensor_building_and_coding():
    queries = [
        "build a FastAPI endpoint for user registration",
        "create a lock-free ring buffer in Python",
        "refactor database connection pool with automatic retries"
    ]
    for q in queries:
        res = IntentSensor.sense(q)
        assert res.intent == UserIntent.BUILD, f"Failed on {q}: got {res.intent}"
        assert res.skip_heavy_tools is False
        assert res.execution_strategy == ExecutionStrategy.FULL_AGENTIC_BUILD
