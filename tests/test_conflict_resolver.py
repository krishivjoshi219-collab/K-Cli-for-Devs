"""
test_conflict_resolver.py - Comprehensive Unit Tests for ConflictResolver Module
"""

import ast
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from k_cli.git.conflict_resolver import (
    ConflictBlock,
    ConflictResolution,
    ConflictResolver,
    ConflictSummary,
    FileResolutionResult,
)
from k_cli.git.verifier import Verifier


class MockLLMDriver:
    """Mock LLM Driver for conflict resolution tests."""

    def __init__(self, fixed_responses: Optional[List[str]] = None, default_response: Optional[str] = None):
        self.fixed_responses = list(fixed_responses) if fixed_responses else []
        self.default_response = default_response or "```python\ndef merged_func():\n    return 'resolved'\n```"
        self.call_count = 0
        self.prompts_received: List[str] = []

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.2) -> str:
        self.call_count += 1
        self.prompts_received.append(prompt)
        if self.fixed_responses:
            return self.fixed_responses.pop(0)
        return self.default_response


@pytest.fixture
def temp_repo():
    """Creates an isolated git repository in a temporary directory."""
    tmp_dir = tempfile.mkdtemp()
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"

    subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_dir, check=True, capture_output=True, env=env)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_dir, check=True, capture_output=True, env=env)

    yield Path(tmp_dir)

    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestConflictBlockAndDataclasses:
    def test_conflict_block_properties(self):
        block = ConflictBlock(
            file_path="src/main.py",
            start_line=10,
            end_line=20,
            ours_content="x = 1\n",
            theirs_content="x = 2\n",
            base_content="x = 0\n",
            ours_label="HEAD",
            theirs_label="feature",
            base_label="base",
            raw_block="<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> feature\n",
            scope_name="calculate_score",
            language="python",
        )
        assert block.is_3way() is True
        d = block.to_dict()
        assert d["file_path"] == "src/main.py"
        assert d["start_line"] == 10
        assert d["end_line"] == 20
        assert d["is_3way"] is True

    def test_conflict_resolution_and_summary_to_dict(self):
        block = ConflictBlock(
            file_path="src/calc.py",
            start_line=5,
            end_line=15,
            ours_content="a = 1\n",
            theirs_content="a = 2\n",
        )
        res = ConflictResolution(
            conflict=block,
            resolved_content="a = 3\n",
            success=True,
            attempts=1,
            explanation="Synthesized",
        )
        assert res.to_dict()["success"] is True
        assert res.to_dict()["resolved_content"] == "a = 3\n"

        file_res = FileResolutionResult(
            file_path="src/calc.py",
            success=True,
            total_conflicts=1,
            resolved_conflicts=1,
            resolutions=[res],
            staged=True,
        )
        assert file_res.to_dict()["staged"] is True

        summary = ConflictSummary(
            repo_path="/tmp/repo",
            total_files=1,
            resolved_files=1,
            failed_files=0,
            file_results={"src/calc.py": file_res},
            success=True,
        )
        assert summary.to_dict()["total_files"] == 1
        assert summary.to_dict()["success"] is True


class TestConflictMarkerParsing:
    def test_parse_2way_conflict(self):
        content = (
            "import os\n"
            "\n"
            "<<<<<<< HEAD\n"
            "def greet():\n"
            "    return 'hello from main'\n"
            "=======\n"
            "def greet():\n"
            "    return 'hello from feature'\n"
            ">>>>>>> feature-branch\n"
            "\n"
            "print(greet())\n"
        )
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="greet.py")

        assert len(blocks) == 1
        b = blocks[0]
        assert b.start_line == 3
        assert b.end_line == 9
        assert b.ours_label == "HEAD"
        assert b.theirs_label == "feature-branch"
        assert "hello from main" in b.ours_content
        assert "hello from feature" in b.theirs_content
        assert b.base_content is None
        assert b.is_3way() is False

    def test_parse_3way_conflict(self):
        content = (
            "<<<<<<< HEAD\n"
            "val = 'modified in HEAD'\n"
            "||||||| merged common ancestors\n"
            "val = 'base value'\n"
            "=======\n"
            "val = 'modified in feature'\n"
            ">>>>>>> feature\n"
        )
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="config.py")

        assert len(blocks) == 1
        b = blocks[0]
        assert b.is_3way() is True
        assert b.base_label == "merged common ancestors"
        assert "base value" in b.base_content
        assert "modified in HEAD" in b.ours_content
        assert "modified in feature" in b.theirs_content

    def test_parse_multiple_conflicts(self):
        content = (
            "# Block 1\n"
            "<<<<<<< HEAD\n"
            "A = 1\n"
            "=======\n"
            "A = 2\n"
            ">>>>>>> branchA\n"
            "\n"
            "# Middle content\n"
            "B = 100\n"
            "\n"
            "# Block 2\n"
            "<<<<<<< HEAD\n"
            "C = 3\n"
            "=======\n"
            "C = 4\n"
            ">>>>>>> branchB\n"
        )
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="vars.py")

        assert len(blocks) == 2
        assert blocks[0].start_line == 2
        assert blocks[0].theirs_label == "branchA"
        assert blocks[1].start_line == 12
        assert blocks[1].theirs_label == "branchB"

    def test_parse_no_conflicts(self):
        content = "def normal():\n    return 42\n"
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="normal.py")
        assert len(blocks) == 0


class TestScopeContextExtraction:
    def test_python_ast_scope_and_imports(self):
        content = (
            "import os\n"
            "from math import sqrt, sin\n"
            "\n"
            "class Calculator:\n"
            "    def __init__(self):\n"
            "        self.factor = 2\n"
            "\n"
            "    def compute(self, x):\n"
            "<<<<<<< HEAD\n"
            "        return x * self.factor\n"
            "=======\n"
            "        return x * self.factor + sqrt(x)\n"
            ">>>>>>> feature\n"
        )
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="calc.py")

        assert len(blocks) == 1
        b = blocks[0]
        assert b.scope_name == "Calculator.compute"
        assert b.surrounding_context is not None
        assert "import os" in b.surrounding_context
        assert "from math import sqrt, sin" in b.surrounding_context

    def test_non_python_scope_extraction(self):
        content = (
            "import { useState } from 'react';\n"
            "\n"
            "function UserProfile(props) {\n"
            "<<<<<<< HEAD\n"
            "  const name = props.username;\n"
            "=======\n"
            "  const name = props.displayName || 'Anonymous';\n"
            ">>>>>>> feature\n"
            "  return <div>{name}</div>;\n"
            "}\n"
        )
        resolver = ConflictResolver()
        blocks = resolver.parse_conflict_blocks(content, file_path="UserProfile.jsx")

        assert len(blocks) == 1
        b = blocks[0]
        assert b.scope_name == "UserProfile"
        assert b.language == "javascript"
        assert "import { useState } from 'react';" in b.surrounding_context


class TestTrivialConflictResolution:
    def test_trivial_identical_content(self):
        block = ConflictBlock(
            file_path="test.py",
            start_line=1,
            end_line=5,
            ours_content="x = 10\n",
            theirs_content="x = 10\n",
        )
        res = ConflictResolver.resolve_trivial(block)
        assert res == "x = 10\n"

    def test_trivial_3way_base_matches_ours(self):
        block = ConflictBlock(
            file_path="test.py",
            start_line=1,
            end_line=7,
            ours_content="x = 1\n",
            base_content="x = 1\n",
            theirs_content="x = 2\n",
        )
        res = ConflictResolver.resolve_trivial(block)
        assert res == "x = 2\n"

    def test_trivial_3way_base_matches_theirs(self):
        block = ConflictBlock(
            file_path="test.py",
            start_line=1,
            end_line=7,
            ours_content="x = 2\n",
            base_content="x = 1\n",
            theirs_content="x = 1\n",
        )
        res = ConflictResolver.resolve_trivial(block)
        assert res == "x = 2\n"

    def test_non_trivial_returns_none(self):
        block = ConflictBlock(
            file_path="test.py",
            start_line=1,
            end_line=7,
            ours_content="x = 2\n",
            base_content="x = 0\n",
            theirs_content="x = 3\n",
        )
        assert ConflictResolver.resolve_trivial(block) is None


class TestBlockResolutionAndVerificationGate:
    def test_resolve_block_with_mock_llm(self):
        verifier = Verifier()
        mock_driver = MockLLMDriver(
            default_response="```python\ndef calculate(a, b):\n    return a + b + 10\n```"
        )
        block = ConflictBlock(
            file_path="math_utils.py",
            start_line=2,
            end_line=8,
            ours_content="def calculate(a, b):\n    return a + b\n",
            theirs_content="def calculate(a, b):\n    return a + b + 10\n",
            language="python",
        )
        resolver = ConflictResolver()
        res = resolver.resolve_conflict_block(
            conflict=block,
            llm_driver=mock_driver,
            verifier=verifier,
        )

        assert res.success is True
        assert res.attempts == 1
        assert "return a + b + 10" in res.resolved_content

    def test_verification_gate_retry_on_syntax_error(self):
        verifier = Verifier()
        mock_driver = MockLLMDriver(
            fixed_responses=[
                "```python\ndef broken(\n    return 42\n```",
                "```python\ndef fixed():\n    return 42\n```",
            ]
        )
        block = ConflictBlock(
            file_path="foo.py",
            start_line=1,
            end_line=5,
            ours_content="def func(): return 1\n",
            theirs_content="def func(): return 2\n",
            language="python",
        )
        resolver = ConflictResolver()
        res = resolver.resolve_conflict_block(
            conflict=block,
            llm_driver=mock_driver,
            verifier=verifier,
            max_retries=3,
        )

        assert res.success is True
        assert res.attempts == 2
        assert "def fixed():" in res.resolved_content

    def test_verification_gate_fails_after_max_retries(self):
        verifier = Verifier()
        mock_driver = MockLLMDriver(
            default_response="```python\ndef syntax_error(\n```"
        )
        block = ConflictBlock(
            file_path="foo.py",
            start_line=1,
            end_line=5,
            ours_content="foo = 1\n",
            theirs_content="foo = 2\n",
            language="python",
        )
        resolver = ConflictResolver()
        res = resolver.resolve_conflict_block(
            conflict=block,
            llm_driver=mock_driver,
            verifier=verifier,
            max_retries=2,
        )

        assert res.success is False
        assert res.attempts == 2
        assert "SyntaxError" in (res.error_message or "")

    def test_reject_output_with_conflict_markers(self):
        mock_driver = MockLLMDriver(
            fixed_responses=[
                "```python\n<<<<<<< HEAD\nfoo = 1\n=======\nfoo = 2\n>>>>>>> branch\n```",
                "```python\nfoo = 3\n```",
            ]
        )
        block = ConflictBlock(
            file_path="foo.py",
            start_line=1,
            end_line=5,
            ours_content="foo = 1\n",
            theirs_content="foo = 2\n",
            language="python",
        )
        resolver = ConflictResolver()
        res = resolver.resolve_conflict_block(
            conflict=block,
            llm_driver=mock_driver,
            max_retries=3,
        )
        assert res.success is True
        assert res.attempts == 2
        assert res.resolved_content == "foo = 3"


class TestFileResolutionAndAutoStaging:
    def test_resolve_file_e2e(self, temp_repo):
        verifier = Verifier()
        mock_driver = MockLLMDriver(
            default_response="```python\ndef solve():\n    return 'resolved properly'\n```"
        )
        file_path = temp_repo / "solution.py"
        conflict_content = (
            "import sys\n"
            "\n"
            "<<<<<<< HEAD\n"
            "def solve():\n"
            "    return 'ours'\n"
            "=======\n"
            "def solve():\n"
            "    return 'theirs'\n"
            ">>>>>>> incoming\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    print(solve())\n"
        )
        file_path.write_text(conflict_content, encoding="utf-8")

        resolver = ConflictResolver()
        result = resolver.resolve_file(
            file_path=str(file_path),
            llm_driver=mock_driver,
            verifier=verifier,
            auto_stage=True,
        )

        assert result.success is True
        assert result.total_conflicts == 1
        assert result.resolved_conflicts == 1
        assert result.staged is True

        # Check file content on disk
        updated_content = file_path.read_text(encoding="utf-8")
        assert "<<<<<<<" not in updated_content
        assert "resolved properly" in updated_content
        # Check AST validity
        ast.parse(updated_content)

    def test_resolve_file_no_conflicts(self, temp_repo):
        file_path = temp_repo / "clean.py"
        file_path.write_text("x = 10\n", encoding="utf-8")

        resolver = ConflictResolver()
        result = resolver.resolve_file(
            file_path=str(file_path),
            llm_driver=MockLLMDriver(),
            auto_stage=False,
        )
        assert result.success is True
        assert result.total_conflicts == 0

    def test_resolve_file_non_existent(self):
        resolver = ConflictResolver()
        result = resolver.resolve_file(
            file_path="/tmp/does_not_exist_987654.py",
            llm_driver=MockLLMDriver(),
        )
        assert result.success is False
        assert "not found" in (result.error_message or "").lower()

    def test_find_and_resolve_all_conflicts(self, temp_repo):
        verifier = Verifier()
        mock_driver = MockLLMDriver(
            default_response="```python\nVAL = 'resolved'\n```"
        )
        f1 = temp_repo / "f1.py"
        f1.write_text("<<<<<<< HEAD\nVAL = 'A'\n=======\nVAL = 'B'\n>>>>>>> b\n", encoding="utf-8")

        f2 = temp_repo / "f2.py"
        f2.write_text("<<<<<<< HEAD\nVAL = '1'\n=======\nVAL = '2'\n>>>>>>> b\n", encoding="utf-8")

        resolver = ConflictResolver()
        conflicts = resolver.find_conflicts(repo_path=str(temp_repo))
        assert len(conflicts) == 2

        summary = resolver.resolve_all_conflicts(
            repo_path=str(temp_repo),
            llm_driver=mock_driver,
            verifier=verifier,
            auto_stage=True,
        )

        assert summary.success is True
        assert summary.total_files == 2
        assert summary.resolved_files == 2
        assert summary.failed_files == 0
