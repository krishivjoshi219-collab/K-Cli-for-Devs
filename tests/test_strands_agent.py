"""
test_strands_agent.py - Comprehensive Unit & Integration Tests for Strands Agents SDK Integration
Built for the AWS 'Agents for Humans' Hackathon
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from k_cli.agents.strands_agent import (
    StrandsDevAgent,
    StrandsModelFactory,
    create_strands_agent,
    STRANDS_DEV_TOOLS,
    triage_and_heal_incident,
    verify_code_file,
    apply_surgical_patch,
    resolve_git_merge_conflict,
    inspect_repo_structure,
    search_offline_docs,
    generate_architecture_diagram,
    generate_chaos_immunity_patch,
)


class TestStrandsTools:
    """Test suite for Strands-registered deterministic tools."""

    def test_registered_tools_count(self):
        assert len(STRANDS_DEV_TOOLS) >= 8

    def test_execute_command_tool(self):
        from k_cli.agents.strands_agent import execute_command
        res = json.loads(execute_command("echo 'Strands Agent Tool Executed'"))
        assert res["success"] is True
        assert "Strands Agent Tool Executed" in res["stdout"]

    def test_verify_code_file_valid_python(self, tmp_path):
        test_file = tmp_path / "valid.py"
        test_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        res_str = verify_code_file(str(test_file))
        res = json.loads(res_str)
        assert res["passed"] is True
        assert len(res["errors"]) == 0

    def test_verify_code_file_syntax_error(self, tmp_path):
        test_file = tmp_path / "invalid.py"
        test_file.write_text("def broken(:\n    return 42\n")

        res_str = verify_code_file(str(test_file))
        res = json.loads(res_str)
        assert res["passed"] is False
        assert len(res["errors"]) > 0

    def test_verify_code_file_nonexistent(self):
        res_str = verify_code_file("/nonexistent/path/file.py")
        res = json.loads(res_str)
        assert res["passed"] is False
        assert "does not exist" in res["error"]

    def test_apply_surgical_patch(self, tmp_path):
        target_file = tmp_path / "sample.py"
        target_file.write_text("def greet():\n    return 'hello world'\n")

        res_str = apply_surgical_patch(
            file_path=str(target_file),
            search_block="return 'hello world'",
            replace_block="return 'hello AWS Strands'",
        )
        res = json.loads(res_str)
        assert res["success"] is True
        assert "hello AWS Strands" in target_file.read_text()

    def test_resolve_git_merge_conflict_clean(self, tmp_path):
        conflicted_file = tmp_path / "conflict.py"
        conflicted_file.write_text(
            "<<<<<<< HEAD\n"
            "def foo(): return 1\n"
            "=======\n"
            "def foo(): return 2\n"
            ">>>>>>> feature\n"
        )
        res_str = resolve_git_merge_conflict(str(conflicted_file))
        res = json.loads(res_str)
        assert "conflicts_detected" in res
        assert res["conflicts_detected"] == 1

    def test_inspect_repo_structure(self, tmp_path):
        res = inspect_repo_structure(str(tmp_path))
        assert isinstance(res, str)
        assert len(res) > 0

    def test_search_offline_docs(self):
        res = search_offline_docs("asyncio")
        assert res is not None
        assert "asyncio" in str(res)

    def test_generate_architecture_diagram(self, tmp_path):
        res = generate_architecture_diagram(str(tmp_path))
        assert "mermaid" in res.lower()

    def test_generate_chaos_immunity_patch(self, tmp_path):
        sample_file = tmp_path / "calc.py"
        sample_file.write_text("def calc(d):\n    return d['v']\n")
        res_str = generate_chaos_immunity_patch(str(sample_file), repo_path=str(tmp_path))
        res = json.loads(res_str)
        assert "patterns_detected" in res
        assert res["verification_passed"] is True

    def test_triage_and_heal_incident_python_traceback(self):
        sample_traceback = (
            "Traceback (most recent call last):\n"
            '  File "app/service.py", line 42, in process_data\n'
            "    result = 10 / divisor\n"
            "ZeroDivisionError: division by zero\n"
        )
        res_str = triage_and_heal_incident(sample_traceback)
        res = json.loads(res_str)
        assert res["status"] == "ANALYZED"
        assert "ZeroDivisionError" in str(res.get("error_type", "")) or "ZeroDivisionError" in str(res)


class TestStrandsDevAgent:
    """Test suite for StrandsDevAgent factory, execution loop, and model fallbacks."""

    def test_strands_agent_instantiation(self):
        agent = create_strands_agent(provider="auto")
        assert agent is not None
        assert len(agent.tools) >= 8

    def test_strands_agent_fallback_run(self):
        agent = StrandsDevAgent(provider="none")
        prompt = "Traceback (most recent call last):\n  File 'test.py', line 1, in <module>\nValueError: invalid literal"
        output = agent.run(prompt)
        assert "K-CLI Strands Autonomous Agent" in output
        assert "Incident Triage" in output

    def test_strands_model_factory_defaults(self):
        model = StrandsModelFactory.create_model(provider="unknown_provider")
        # Should gracefully return None or default fallback
        assert model is None or hasattr(model, "stream") or hasattr(model, "model_id")
