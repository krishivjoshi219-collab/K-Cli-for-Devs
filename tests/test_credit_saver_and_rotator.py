import pytest
import time
from k_cli.core.rate_limit_guard import RateLimitGuard, ModelRotator, global_rate_limit_guard, global_model_rotator
from k_cli.core.credit_saver import CreditSaver, global_credit_saver
from k_cli.agents.autonomous_agent import AutonomousAgent, tool_spawn_subagent
from k_cli.core.llm_driver import LLMDriver

def test_rate_limit_guard_detection():
    assert RateLimitGuard.is_rate_limit_error("HTTP 429: Too Many Requests") is True
    assert RateLimitGuard.is_rate_limit_error("google.api_core.exceptions.ResourceExhausted: Quota exceeded") is True
    assert RateLimitGuard.is_rate_limit_error("openai.RateLimitError: Rate limit reached for requests") is True
    assert RateLimitGuard.is_rate_limit_error("anthropic.RateLimitError: tokens per minute exceeded") is True
    assert RateLimitGuard.is_rate_limit_error("503 Service Unavailable: Server is overloaded") is True
    assert RateLimitGuard.is_rate_limit_error("SyntaxError: invalid syntax") is False

def test_rate_limit_guard_circuit_breaker():
    guard = RateLimitGuard()
    provider = "test_provider_gemini"
    
    # Initially healthy
    assert guard.is_available(provider) is True
    
    # Trip circuit with 2 second cooldown
    cooldown = guard.trip_circuit(provider, "HTTP 429", cooldown_seconds=1.5)
    assert cooldown == 1.5
    assert guard.is_available(provider) is False
    assert guard.get_remaining_cooldown(provider) > 0.0

    # Wait for cooldown to expire
    time.sleep(1.6)
    assert guard.is_available(provider) is True

def test_model_rotator_fallback():
    guard = RateLimitGuard()
    rotator = ModelRotator(guard=guard)
    
    # Simulate gemini-2.5-flash tripping rate limit
    guard.trip_circuit("gemini-2.5-flash", "Quota exceeded", cooldown_seconds=5.0)
    
    # Next model should NOT be gemini
    next_model, reason = rotator.resolve_next_available_model("gemini-2.5-flash", task_type="fast_chat", require_live=False)
    assert "gemini" not in next_model
    assert next_model in ["claude-3-5-haiku-20241022", "gpt-4o-mini", "deepseek-chat", "mock"]

def test_credit_saver_command_compression():
    saver = CreditSaver()
    
    verbose_pytest_output = (
        "============================= test session starts ==============================\n"
        "platform linux -- Python 3.12.3\n"
        + "".join(f"tests/test_mod.py::test_case_{i} PASSED [ {i}%]\n" for i in range(1, 40))
        + "FAILED tests/test_mod.py::test_case_broken - AssertionError: 42 != 0\n"
        "E   AssertionError: assert 42 == 0\n"
        "============================== 1 failed, 39 passed in 2.15s =============================="
    )
    
    compressed = saver.compress_tool_output("execute_command", verbose_pytest_output, max_lines=20)
    assert "CreditSaver: Compacted" in compressed
    assert "FAILED tests/test_mod.py::test_case_broken" in compressed
    assert "1 failed, 39 passed" in compressed
    # The compressed version should be noticeably shorter
    assert len(compressed) < len(verbose_pytest_output)

def test_credit_saver_prune_conversation_history():
    saver = CreditSaver()
    history = [
        "User Task: Build a full stack application",
        "Turn 1: Reading file 1 <tool_result tool=\"read_workspace_file\">content...</tool_result>",
        "Turn 2: Reading file 2 <tool_result tool=\"read_workspace_file\">content...</tool_result>",
        "Turn 3: Executing command <tool_result tool=\"execute_command\">content...</tool_result>",
        "Turn 4: Latest step content here",
    ]
    
    pruned = saver.prune_conversation_history(history, max_tokens=20)
    assert len(pruned) < len(history)
    assert "CreditSaver: Condensed" in pruned[1]
    assert pruned[0].startswith("User Task:")

def test_credit_saver_financial_calculation():
    saver = CreditSaver()
    saver.record_local_ast_verification()
    saver.record_local_ast_verification()
    
    savings = saver.calculate_savings("gemini-2.5-flash", prompt_tokens=5000, completion_tokens=800)
    assert savings["actual_cost_usd"] < savings["baseline_cost_usd"]
    assert savings["saved_usd"] > 0.0
    assert savings["savings_percent"] > 50.0
    assert "CreditSaver: Spent" in savings["summary"]

def test_tool_spawn_subagent():
    # Spawns subagent in offline/mock driver
    result = tool_spawn_subagent("researcher", "Analyze the git directory structure")
    assert "Completed Task" in result
    assert "RESEARCHER" in result

def test_autonomous_agent_with_credit_saver(tmp_path):
    driver = LLMDriver(mock_mode=True)
    agent = AutonomousAgent(driver=driver, cwd=str(tmp_path), model_name="gemini-2.5-flash")
    
    res = agent.run("build a hello world script in python and verify syntax")
    assert res.success is True
    assert res.actual_cost_usd >= 0.0
    assert res.saved_usd >= 0.0
    assert "CreditSaver" in res.savings_summary
    assert res.model_rotations >= 0
