"""
test_verifier.py - Unit and Integration tests for Ground-Truth Verifier Guard
"""

import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from k_cli.git.verifier import (
    CodeExtractor,
    VerificationResult,
    Verifier,
    extract_error_line,
    extract_stack_trace,
    parse_ast,
    strip_fluff,
    verify,
)


def test_parse_ast_valid():
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    success, err, line = parse_ast(code)
    assert success is True
    assert err is None
    assert line is None


def test_parse_ast_syntax_error():
    code = "def add(a, b)\n    return a + b"
    success, err, line = parse_ast(code)
    assert success is False
    assert err is not None
    assert "SyntaxError" in err
    assert line == 1


def test_verify_python_execution_passing():
    code = "def add(a, b):\n    return a + b"
    test_code = "from solution import add\ndef test_add():\n    assert add(2, 3) == 5"
    res = verify(code, language="python", test_code=test_code)
    assert res.success is True
    assert res.verification_type == "pytest"
    assert res.language == "python"


def test_verify_python_execution_failing():
    code = "def add(a, b):\n    return a - b"
    test_code = "from solution import add\ndef test_add():\n    assert add(2, 3) == 5"
    res = verify(code, language="python", test_code=test_code)
    assert res.success is False
    assert res.verification_type == "pytest"
    assert res.line_number is not None
    assert res.error_trace != ""


def test_verify_bash_syntax_valid():
    code = "#!/bin/bash\nif [ 1 -eq 1 ]; then\n    echo 'ok'\nfi"
    res = verify(code, language="bash")
    assert res.success is True
    assert res.language == "bash"
    assert res.verification_type == "syntax"


def test_verify_bash_syntax_invalid():
    code = "#!/bin/bash\nif [ 1 -eq 1 ]; then\n    echo 'ok'"
    res = verify(code, language="bash")
    assert res.success is False
    assert res.language == "bash"
    assert res.line_number is not None


def test_verify_cpp_syntax_valid():
    code = "#include <iostream>\nint main() {\n    std::cout << \"Hello\" << std::endl;\n    return 0;\n}"
    res = verify(code, language="cpp")
    assert res.success is True
    assert res.language == "cpp"


def test_verify_cpp_syntax_invalid():
    code = "#include <iostream>\nint main() {\n    std::cout << \"Hello\" << std::endl\n    return 0;\n}"
    res = verify(code, language="cpp")
    assert res.success is False
    assert res.language == "cpp"
    assert res.line_number is not None


def test_extract_error_line_python():
    trace = "test_solution.py:15: in test_add\n    assert add(2, 3) == 5\nsolution.py:3: in add\n    return a - b\nE   AssertionError"
    line = extract_error_line(trace, "python")
    assert line == 3


def test_extract_error_line_python_stdlib_filtering():
    trace = (
        'File "/usr/lib/python3.12/json/__init__.py", line 339, in loads\n'
        'File "solution.py", line 12, in parse\n'
        'ValueError: bad format'
    )
    line = extract_error_line(trace, "python")
    assert line == 12


def test_extract_error_line_stdlib_exception_message():
    tb = (
        'Traceback (most recent call last):\n'
        '  File "solution.py", line 25, in parse_config\n'
        '    return json.loads(raw_data)\n'
        '  File "/usr/lib/python3.12/json/__init__.py", line 339, in loads\n'
        '    return _default_decoder.decode(s)\n'
        '  File "/usr/lib/python3.12/json/decoder.py", line 355, in raw_decode\n'
        '    raise JSONDecodeError("Expecting value", s, err.value) from None\n'
        'json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)\n'
    )
    assert extract_error_line(tb, "python") == 25


def test_extract_error_line_cpp_fatal_error():
    trace = "main.cpp:5:10: fatal error: non_existent.h: No such file or directory"
    line = extract_error_line(trace, "cpp")
    assert line == 5


def test_extract_error_line_bash():
    trace = "script.sh: line 4: syntax error near unexpected token 'fi'"
    line = extract_error_line(trace, "bash")
    assert line == 4


def test_extract_stack_trace():
    raw_err = "\x1b[31mAssertionError: 2 != 3\x1b[0m"
    clean = extract_stack_trace(raw_err)
    assert clean == "AssertionError: 2 != 3"


def test_code_extractor_unformatted_raw_code():
    lang, code = CodeExtractor.extract_primary_code("echo 'hello world'", default_lang="bash")
    assert lang == "bash"
    assert code == "echo 'hello world'"

    lang_cpp, code_cpp = CodeExtractor.extract_primary_code("int main(){ return 0; }", default_lang="cpp")
    assert lang_cpp == "cpp"
    assert code_cpp == "int main(){ return 0; }"


def test_strip_fluff():
    md_text = "Here is the solution:\n```python\ndef foo():\n    pass\n```\nHope this helps!"
    assert strip_fluff(md_text) == "def foo():\n    pass"

    raw_convo = "Here is the code:\ndef bar():\n    return 42"
    assert strip_fluff(raw_convo) == "def bar():\n    return 42"


def test_verification_result_to_dict():
    res = VerificationResult(
        success=True,
        error_trace="",
        code="print(1)",
        line_number=None,
        language="python",
        stdout="1\n",
        stderr="",
        verification_type="execution",
        rolled_back=False,
    )
    d = res.to_dict()
    assert d["success"] is True
    assert d["code"] == "print(1)"
    assert d["language"] == "python"
    assert d["verification_type"] == "execution"
    assert d["rolled_back"] is False


def test_detect_test_framework_pytest(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework, TestFramework
    # pytest.ini
    p1 = tmp_path / "py_proj1"
    p1.mkdir()
    (p1 / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    assert detect_test_framework(p1) == TestFramework.PYTEST.value

    # pyproject.toml
    p2 = tmp_path / "py_proj2"
    p2.mkdir()
    (p2 / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    assert detect_test_framework(p2) == TestFramework.PYTEST.value

    # tests directory
    p3 = tmp_path / "py_proj3"
    p3.mkdir()
    t_dir = p3 / "tests"
    t_dir.mkdir()
    (t_dir / "test_example.py").write_text("def test_one(): pass\n", encoding="utf-8")
    assert detect_test_framework(p3) == TestFramework.PYTEST.value


def test_detect_test_framework_cargo(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework, TestFramework
    p = tmp_path / "rust_proj"
    p.mkdir()
    (p / "Cargo.toml").write_text('[package]\nname = "test"\n', encoding="utf-8")
    assert detect_test_framework(p) == TestFramework.CARGO.value


def test_detect_test_framework_npm(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework, TestFramework
    p = tmp_path / "node_proj"
    p.mkdir()
    (p / "package.json").write_text('{"name": "test", "scripts": {"test": "jest"}}\n', encoding="utf-8")
    assert detect_test_framework(p) == TestFramework.NPM.value


def test_detect_test_framework_go(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework, TestFramework
    p = tmp_path / "go_proj"
    p.mkdir()
    (p / "go.mod").write_text("module example.com/test\n", encoding="utf-8")
    assert detect_test_framework(p) == TestFramework.GO.value


def test_detect_test_framework_make(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework, TestFramework
    p = tmp_path / "make_proj"
    p.mkdir()
    (p / "Makefile").write_text("test:\n\techo ok\n", encoding="utf-8")
    assert detect_test_framework(p) == TestFramework.MAKE.value


def test_detect_test_framework_none(tmp_path: Path):
    from k_cli.git.verifier import detect_test_framework
    p = tmp_path / "empty_proj"
    p.mkdir()
    assert detect_test_framework(p) is None


def test_run_project_tests_pytest_pass(tmp_path: Path):
    from k_cli.git.verifier import run_project_tests
    proj = tmp_path / "pytest_pass"
    proj.mkdir()
    (proj / "conftest.py").write_text("", encoding="utf-8")
    (proj / "test_math.py").write_text("def test_add(): assert 1 + 1 == 2\n", encoding="utf-8")

    res = run_project_tests(project_dir=proj)
    assert res.success is True
    assert res.verification_type == "pytest"


def test_run_project_tests_pytest_fail(tmp_path: Path):
    from k_cli.git.verifier import run_project_tests
    proj = tmp_path / "pytest_fail"
    proj.mkdir()
    (proj / "conftest.py").write_text("", encoding="utf-8")
    (proj / "test_math.py").write_text("def test_add(): assert 1 + 1 == 3\n", encoding="utf-8")

    res = run_project_tests(project_dir=proj)
    assert res.success is False
    assert res.line_number is not None
    assert "assert 1 + 1 == 3" in res.error_trace or "AssertionError" in res.error_trace


def test_verify_post_patch_auto_rollback_on_ast_error(tmp_path: Path):
    import subprocess
    from k_cli.git.git_guard import GitGuard
    from k_cli.git.verifier import verify_post_patch

    repo = tmp_path / "ast_rollback_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo, check=True, capture_output=True)

    src = repo / "main.py"
    src.write_text("def valid_code(): return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    guard = GitGuard(repo_dir=str(repo))
    ckpt_id = guard.create_checkpoint()

    # Introduce invalid AST syntax
    src.write_text("def broken_code(:\n", encoding="utf-8")

    res = verify_post_patch(project_dir=repo, git_guard=guard, checkpoint_id=ckpt_id, auto_rollback=True)
    assert res.success is False
    assert res.rolled_back is True
    assert "SyntaxError" in res.error_trace
    # Check that file was rolled back to valid state
    assert src.read_text(encoding="utf-8") == "def valid_code(): return 1\n"


def test_verify_post_patch_auto_rollback_on_test_failure(tmp_path: Path):
    import subprocess
    from k_cli.git.git_guard import GitGuard
    from k_cli.git.verifier import verify_post_patch

    repo = tmp_path / "test_rollback_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=repo, check=True, capture_output=True)

    (repo / "conftest.py").write_text("", encoding="utf-8")
    src = repo / "calculator.py"
    src.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    test_f = repo / "test_calculator.py"
    test_f.write_text("from calculator import add\ndef test_add(): assert add(2, 2) == 4\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    guard = GitGuard(repo_dir=str(repo))
    ckpt_id = guard.create_checkpoint()

    # Modify calculator to break test
    src.write_text("def add(a, b): return a * b + 10\n", encoding="utf-8")

    res = verify_post_patch(project_dir=repo, git_guard=guard, checkpoint_id=ckpt_id, auto_rollback=True)
    assert res.success is False
    assert res.rolled_back is True
    # Verify that working tree is restored to working state
    assert src.read_text(encoding="utf-8") == "def add(a, b): return a + b\n"


def test_extract_framework_line_numbers():
    from k_cli.git.verifier import extract_error_line

    # Rust / Cargo
    rust_trace = "error[E0425]: cannot find value `x` in this scope\n  --> src/main.rs:17:5\n   |"
    assert extract_error_line(rust_trace, "rust") == 17

    # Go
    go_trace = "--- FAIL: TestAdd (0.00s)\n    calc_test.go:42: expected 4, got 5"
    assert extract_error_line(go_trace, "go") == 42

    # JavaScript / Node
    js_trace = "AssertionError: expected 2 to equal 3\n    at Object.<anonymous> (test/app.test.js:88:12)"
    assert extract_error_line(js_trace, "javascript") == 88

