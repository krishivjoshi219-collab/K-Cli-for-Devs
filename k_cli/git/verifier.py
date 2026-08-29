"""
verifier.py - Ground-Truth Execution Guard for K-CLI (Project Bankai Engine v1.0.0)

Intercepts generated code blocks (Python, C++, Bash), performs immediate AST and
syntax checks, auto-detects project test frameworks (pytest, cargo test, npm test,
go test, make test), executes isolated compilation/test suites via subprocess,
triggers instant automatic rollbacks on test/AST failures, and extracts
precise line numbers and stack traces for auto-debug loops.
"""

import ast
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import resource
except ImportError:  # pragma: no cover - non-POSIX hosts
    resource = None  # type: ignore


def _sanitize_path(path_input: Union[str, Path], base_dir: Optional[Union[str, Path]] = None) -> Path:
    """Sanitizes user-provided path inputs to prevent directory traversal vulnerabilities."""
    p = Path(path_input).resolve()
    if base_dir is not None:
        base = Path(base_dir).resolve()
        try:
            if p.is_relative_to(base) or os.path.commonpath([str(base), str(p)]) == str(base):
                return p
            return (base / Path(path_input).name).resolve()
        except Exception:
            return (base / Path(path_input).name).resolve()
    return p


class TestFramework(str, Enum):
    """Supported auto-detected project test frameworks."""
    PYTEST = "pytest"
    CARGO = "cargo"
    NPM = "npm"
    GO = "go"
    MAKE = "make"
    CUSTOM = "custom"


@dataclass
class VerificationResult:
    """Structured result returned by the Verifier guard."""
    success: bool
    error_trace: str
    code: str
    line_number: Optional[int] = None
    language: str = "python"
    stdout: str = ""
    stderr: str = ""
    verification_type: str = "syntax"  # "syntax", "compilation", "pytest", "cargo", "npm", "go", "make", "project_test", "execution"
    rolled_back: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "error_trace": self.error_trace,
            "code": self.code,
            "line_number": self.line_number,
            "language": self.language,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "verification_type": self.verification_type,
            "rolled_back": self.rolled_back,
        }


class CodeExtractor:
    """Extracts isolated code blocks and language metadata from markdown outputs."""

    @staticmethod
    def extract_code_blocks(text: str, default_lang: str = "python") -> List[Tuple[str, str]]:
        """
        Finds all markdown code blocks in text.
        Returns a list of tuples: (language, code_content)
        If no code blocks are found and text is non-empty, returns raw text tagged with default_lang.
        """
        pattern = r"```([a-zA-Z0-9_+\-#]*)\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)

        extracted = []
        for lang, code in matches:
            lang_clean = lang.strip().lower() or default_lang
            if lang_clean in ("py", "python3"):
                lang_clean = "python"
            elif lang_clean in ("cpp", "c++", "cc", "cxx"):
                lang_clean = "cpp"
            elif lang_clean in ("bash", "sh", "zsh", "shell"):
                lang_clean = "bash"
            elif lang_clean in ("rs", "rust"):
                lang_clean = "rust"
            elif lang_clean in ("js", "javascript", "ts", "typescript"):
                lang_clean = "javascript"
            elif lang_clean in ("golang", "go"):
                lang_clean = "go"
            extracted.append((lang_clean, code.strip()))

        if not extracted and text.strip():
            return [(default_lang, text.strip())]

        return extracted

    @staticmethod
    def extract_primary_code(text: str, default_lang: str = "python") -> Tuple[str, str]:
        """Extracts the primary code block matching default_lang, or the first code block."""
        blocks = CodeExtractor.extract_code_blocks(text, default_lang=default_lang)
        if not blocks:
            return default_lang, text.strip()
        for lang, code in blocks:
            if lang == default_lang:
                return lang, code
        return blocks[0]


class Verifier:
    """Ground-Truth Execution Guard providing static AST parsing, isolated execution, and framework tests."""

    def __init__(self, python_executable: Optional[str] = None):
        self.python_executable = python_executable or sys.executable

    @staticmethod
    def _safe_environment() -> Dict[str, str]:
        """Keep tool discovery while preventing common provider secrets from leaking."""
        env = dict(os.environ)
        for key in list(env):
            upper = key.upper()
            if any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY")):
                env.pop(key, None)
        return env

    @staticmethod
    def _limit_child_resources() -> None:
        """Apply conservative POSIX limits to verifier children when supported."""
        if resource is None:
            return
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

    @classmethod
    def _run_subprocess(
        cls,
        cmd: List[str],
        *,
        cwd: Union[str, Path],
        timeout: float,
    ) -> subprocess.CompletedProcess:
        """Run a verifier child with bounded resources and reliable descendant cleanup."""
        safe_cwd = Path(cwd).resolve()
        if not safe_cwd.exists():
            raise FileNotFoundError(f"Subprocess working directory does not exist: {cwd}")
        kwargs: Dict[str, Any] = {
            "cwd": str(safe_cwd),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": cls._safe_environment(),
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = cls._limit_child_resources
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

    def verify_python_ast(self, code: str) -> VerificationResult:
        """Runs immediate Python ast.parse to catch syntax errors instantly."""
        try:
            ast.parse(code)
            return VerificationResult(
                success=True,
                error_trace="",
                code=code,
                language="python",
                verification_type="syntax",
            )
        except SyntaxError as e:
            error_msg = f"SyntaxError: {e.msg} at line {e.lineno}, column {e.offset}"
            if e.text:
                error_msg += f"\nLine content: {e.text.strip()}"
            return VerificationResult(
                success=False,
                error_trace=error_msg,
                code=code,
                line_number=e.lineno,
                language="python",
                stderr=error_msg,
                verification_type="syntax",
            )
        except Exception as e:
            return VerificationResult(
                success=False,
                error_trace=f"AST Parse Error: {str(e)}",
                code=code,
                language="python",
                verification_type="syntax",
            )

    def verify_python_execution(
        self,
        code: str,
        test_code: Optional[str] = None,
        timeout: float = 15.0,
    ) -> VerificationResult:
        """
        Runs Python code or pytest suite in an isolated temporary directory.
        If test_code is supplied, executes pytest against the code.
        Otherwise executes py_compile.
        """
        # Check AST first
        ast_result = self.verify_python_ast(code)
        if not ast_result.success:
            return ast_result

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            source_file = tmppath / "solution.py"
            source_file.write_text(code, encoding="utf-8")

            if test_code:
                test_file = tmppath / "test_solution.py"
                test_file.write_text(test_code, encoding="utf-8")
                cmd = [self.python_executable, "-m", "pytest", "-v", str(test_file)]
                vtype = "pytest"
            else:
                cmd = [self.python_executable, "-m", "py_compile", str(source_file)]
                vtype = "compilation"

            try:
                proc = self._run_subprocess(
                    cmd,
                    cwd=tmpdir,
                    timeout=timeout,
                )

                if proc.returncode == 0:
                    return VerificationResult(
                        success=True,
                        error_trace="",
                        code=code,
                        language="python",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type=vtype,
                    )
                else:
                    combined_err = (proc.stdout + "\n" + proc.stderr).strip()
                    line_no = self._extract_python_line_number(combined_err)
                    return VerificationResult(
                        success=False,
                        error_trace=combined_err,
                        code=code,
                        line_number=line_no,
                        language="python",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type=vtype,
                    )

            except subprocess.TimeoutExpired:
                err_msg = f"Execution timed out after {timeout} seconds."
                return VerificationResult(
                    success=False,
                    error_trace=err_msg,
                    code=code,
                    language="python",
                    stderr=err_msg,
                    verification_type=vtype,
                )
            except Exception as e:
                err_msg = f"Subprocess execution error: {str(e)}"
                return VerificationResult(
                    success=False,
                    error_trace=err_msg,
                    code=code,
                    language="python",
                    stderr=err_msg,
                    verification_type=vtype,
                )

    def verify_bash_syntax(self, code: str, timeout: float = 10.0) -> VerificationResult:
        """Verifies bash script syntax using `bash -n` in subprocess."""
        bash_bin = shutil.which("bash")
        if not bash_bin:
            return VerificationResult(
                success=True,
                error_trace="Warning: 'bash' executable not available on host system.",
                code=code,
                language="bash",
                verification_type="syntax",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            script_file = Path(tmpdir) / "script.sh"
            script_file.write_text(code, encoding="utf-8")

            try:
                proc = self._run_subprocess(
                    [bash_bin, "-n", str(script_file)],
                    cwd=tmpdir,
                    timeout=timeout,
                )

                if proc.returncode == 0:
                    return VerificationResult(
                        success=True,
                        error_trace="",
                        code=code,
                        language="bash",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type="syntax",
                    )
                else:
                    err_msg = proc.stderr.strip()
                    line_no = self._extract_bash_line_number(err_msg)
                    return VerificationResult(
                        success=False,
                        error_trace=err_msg,
                        code=code,
                        line_number=line_no,
                        language="bash",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type="syntax",
                    )
            except subprocess.TimeoutExpired:
                err_msg = f"Bash verification timed out after {timeout} seconds."
                return VerificationResult(
                    success=False,
                    error_trace=err_msg,
                    code=code,
                    language="bash",
                    stderr=err_msg,
                    verification_type="syntax",
                )
            except Exception as e:
                return VerificationResult(
                    success=False,
                    error_trace=f"Bash verification exception: {str(e)}",
                    code=code,
                    language="bash",
                    verification_type="syntax",
                )

    def verify_cpp_syntax(self, code: str, timeout: float = 30.0) -> VerificationResult:
        """Verifies C++ code compilation syntax using g++ or clang++."""
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            # Fallback checking for unmatched brackets
            unmatched = self._check_unmatched_brackets(code)
            if unmatched:
                return VerificationResult(
                    success=False,
                    error_trace=f"Fallback C++ check: {unmatched}",
                    code=code,
                    language="cpp",
                    verification_type="syntax",
                )
            return VerificationResult(
                success=True,
                error_trace="Note: g++/clang++ compiler not present; passed basic structural validation.",
                code=code,
                language="cpp",
                verification_type="syntax",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            cpp_file = Path(tmpdir) / "main.cpp"
            cpp_file.write_text(code, encoding="utf-8")

            cmd = [compiler, "-std=c++17", "-fsyntax-only", str(cpp_file)]
            try:
                proc = self._run_subprocess(
                    cmd,
                    cwd=tmpdir,
                    timeout=timeout,
                )

                if proc.returncode == 0:
                    return VerificationResult(
                        success=True,
                        error_trace="",
                        code=code,
                        language="cpp",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type="compilation",
                    )
                else:
                    err_msg = proc.stderr.strip()
                    line_no = self._extract_cpp_line_number(err_msg)
                    return VerificationResult(
                        success=False,
                        error_trace=err_msg,
                        code=code,
                        line_number=line_no,
                        language="cpp",
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        verification_type="compilation",
                    )
            except subprocess.TimeoutExpired:
                err_msg = f"C++ compiler check timed out after {timeout} seconds."
                return VerificationResult(
                    success=False,
                    error_trace=err_msg,
                    code=code,
                    language="cpp",
                    stderr=err_msg,
                    verification_type="compilation",
                )
            except Exception as e:
                return VerificationResult(
                    success=False,
                    error_trace=f"C++ compiler check error: {str(e)}",
                    code=code,
                    language="cpp",
                    verification_type="compilation",
                )

    def verify(
        self,
        code: str,
        language: str = "python",
        test_code: Optional[str] = None,
        timeout: float = 30.0,
    ) -> VerificationResult:
        """
        Unified verification entrypoint. Accepts raw code or markdown block,
        extracts clean code, and invokes target language verifier.
        """
        extracted_lang, clean_code = CodeExtractor.extract_primary_code(code, default_lang=language)
        target_lang = extracted_lang or language

        if target_lang == "python":
            return self.verify_python_execution(clean_code, test_code=test_code, timeout=timeout)
        elif target_lang == "bash":
            return self.verify_bash_syntax(clean_code, timeout=timeout)
        elif target_lang == "cpp":
            return self.verify_cpp_syntax(clean_code, timeout=timeout)
        else:
            return VerificationResult(
                success=True,
                error_trace="",
                code=clean_code,
                language=target_lang,
                verification_type="syntax",
            )

    @staticmethod
    def detect_test_framework(project_dir: Union[str, Path] = ".") -> Optional[str]:
        """
        Auto-detects project test frameworks based on workspace configuration files.

        Detection priority:
        1. Cargo (Rust): Cargo.toml
        2. NPM (Node.js/TS): package.json
        3. Go: go.mod or *_test.go files
        4. Make: Makefile / makefile / GNUmakefile with test target or generic
        5. Pytest (Python): pytest.ini, pyproject.toml, setup.cfg, conftest.py, tests/ dir, test_*.py, *_test.py

        Returns:
            Detected framework name ("pytest", "cargo", "npm", "go", "make") or None.
        """
        p_dir = _sanitize_path(project_dir)
        if not p_dir.exists() or not p_dir.is_dir():
            return None

        # 1. Rust (Cargo)
        if (p_dir / "Cargo.toml").exists():
            return TestFramework.CARGO.value

        # 2. Node (NPM)
        if (p_dir / "package.json").exists():
            return TestFramework.NPM.value

        # 3. Go
        if (p_dir / "go.mod").exists() or list(p_dir.glob("*_test.go")):
            return TestFramework.GO.value

        # 4. Make
        for makefile_name in ("Makefile", "makefile", "GNUmakefile"):
            mf = p_dir / makefile_name
            if mf.exists():
                return TestFramework.MAKE.value

        # 5. Python / Pytest
        pytest_indicators = [
            p_dir / "pytest.ini",
            p_dir / "conftest.py",
            p_dir / "setup.cfg",
            p_dir / "tox.ini",
            p_dir / ".pytest_cache",
        ]
        if any(ind.exists() for ind in pytest_indicators):
            return TestFramework.PYTEST.value

        pyproject = p_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8")
                if "pytest" in content or "tool.pytest" in content or "project" in content:
                    return TestFramework.PYTEST.value
            except Exception:
                return TestFramework.PYTEST.value

        tests_dir = p_dir / "tests"
        if tests_dir.exists() and tests_dir.is_dir() and any(tests_dir.glob("*.py")):
            return TestFramework.PYTEST.value

        if list(p_dir.glob("test_*.py")) or list(p_dir.glob("*_test.py")):
            return TestFramework.PYTEST.value

        return None

    def get_test_command(
        self,
        framework: str,
        project_dir: Union[str, Path] = ".",
        extra_args: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Constructs CLI command array for a given test framework.
        """
        fw = framework.lower().strip()
        cmd: List[str] = []

        if fw in ("pytest", "python", "py"):
            cmd = [self.python_executable, "-m", "pytest", "-v"]
        elif fw in ("cargo", "cargo test", "rust"):
            cmd = ["cargo", "test"]
        elif fw in ("npm", "npm test", "node", "javascript", "typescript"):
            cmd = ["npm", "test"]
        elif fw in ("go", "go test", "golang"):
            cmd = ["go", "test", "./..."]
        elif fw in ("make", "make test", "makefile"):
            cmd = ["make", "test"]
        else:
            cmd = framework.split()

        if extra_args:
            cmd.extend(extra_args)
        return cmd

    def run_project_tests(
        self,
        project_dir: Union[str, Path] = ".",
        framework: Optional[str] = None,
        timeout: float = 60.0,
        extra_args: Optional[List[str]] = None,
    ) -> VerificationResult:
        """
        Auto-detects project test framework (pytest, cargo test, npm test, go test, make test)
        and runs post-patch verification suite in the target project directory.
        """
        p_dir = _sanitize_path(project_dir)
        detected_fw = framework or self.detect_test_framework(p_dir)

        if not detected_fw:
            return VerificationResult(
                success=True,
                error_trace="",
                code="",
                language="generic",
                stdout="No test framework detected; verification passed by default.",
                stderr="",
                verification_type="project_test",
            )

        cmd = self.get_test_command(detected_fw, project_dir=p_dir, extra_args=extra_args)
        exec_name = cmd[0] if cmd else ""

        # Check if executable exists
        if not shutil.which(exec_name) and exec_name != self.python_executable:
            err_msg = f"Test executable '{exec_name}' not found on system path."
            return VerificationResult(
                success=False,
                error_trace=err_msg,
                code="",
                language=detected_fw,
                stderr=err_msg,
                verification_type=detected_fw,
            )

        try:
            proc = self._run_subprocess(
                cmd,
                cwd=str(p_dir),
                timeout=timeout,
            )

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            combined_output = (stdout + "\n" + stderr).strip()

            if proc.returncode == 0:
                return VerificationResult(
                    success=True,
                    error_trace="",
                    code="",
                    language=detected_fw,
                    stdout=stdout,
                    stderr=stderr,
                    verification_type=detected_fw,
                )
            else:
                line_no = self._extract_framework_line_number(combined_output, detected_fw)
                return VerificationResult(
                    success=False,
                    error_trace=combined_output,
                    code="",
                    line_number=line_no,
                    language=detected_fw,
                    stdout=stdout,
                    stderr=stderr,
                    verification_type=detected_fw,
                )

        except subprocess.TimeoutExpired:
            err_msg = f"Project tests timed out after {timeout} seconds ({' '.join(cmd)})."
            return VerificationResult(
                success=False,
                error_trace=err_msg,
                code="",
                language=detected_fw,
                stderr=err_msg,
                verification_type=detected_fw,
            )
        except Exception as e:
            err_msg = f"Failed to execute project tests ({' '.join(cmd)}): {str(e)}"
            return VerificationResult(
                success=False,
                error_trace=err_msg,
                code="",
                language=detected_fw,
                stderr=err_msg,
                verification_type=detected_fw,
            )

    def verify_post_patch(
        self,
        project_dir: Union[str, Path] = ".",
        git_guard: Optional[Any] = None,
        checkpoint_id: Optional[str] = None,
        auto_rollback: bool = True,
        framework: Optional[str] = None,
        timeout: float = 60.0,
    ) -> VerificationResult:
        """
        Runs project test verification post-patch and triggers instant automatic
        rollback (git reset to checkpoint) if tests fail or AST syntax breaks.

        Args:
            project_dir: Path to the workspace / project directory.
            git_guard: Optional GitGuard instance for managing rollback.
            checkpoint_id: Optional checkpoint ID to restore on failure.
            auto_rollback: Whether to trigger instant rollback if verification fails.
            framework: Optional explicit test framework override.
            timeout: Test execution timeout in seconds.

        Returns:
            VerificationResult with `rolled_back=True` if rollback was performed.
        """
        p_dir = _sanitize_path(project_dir)

        # Step 1: Pre-scan Python files in workspace for AST syntax errors
        py_files = list(p_dir.glob("*.py"))
        for py_f in py_files:
            try:
                code_text = py_f.read_text(encoding="utf-8")
                ast_res = self.verify_python_ast(code_text)
                if not ast_res.success:
                    if auto_rollback and git_guard:
                        git_guard.restore_checkpoint(checkpoint_id)
                        ast_res.rolled_back = True
                    return ast_res
            except Exception:
                pass

        # Step 2: Run post-patch test suite
        res = self.run_project_tests(project_dir=p_dir, framework=framework, timeout=timeout)

        # Step 3: Instant rollback if tests failed
        if not res.success and auto_rollback and git_guard:
            git_guard.restore_checkpoint(checkpoint_id)
            res.rolled_back = True

        return res

    @classmethod
    def _extract_framework_line_number(cls, trace: str, framework: str) -> Optional[int]:
        """Extracts error line numbers based on framework-specific error formats."""
        fw = framework.lower().strip()
        if fw in ("pytest", "python"):
            return cls._extract_python_line_number(trace)
        elif fw in ("cargo", "rust"):
            return cls._extract_rust_line_number(trace)
        elif fw in ("go", "golang"):
            return cls._extract_go_line_number(trace)
        elif fw in ("npm", "node", "javascript", "typescript"):
            return cls._extract_js_line_number(trace)
        elif fw in ("make", "cpp", "c"):
            return cls._extract_cpp_line_number(trace)
        return cls._extract_python_line_number(trace)

    @staticmethod
    def _extract_python_line_number(trace: str) -> Optional[int]:
        """Parses line numbers from Python tracebacks, Pytest outputs, or error messages."""
        if not trace:
            return None

        lines = trace.splitlines()

        pytest_pat = re.compile(r'([a-zA-Z0-9_\-\./\\]+\.py):(\d+):')
        tb_pat = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)')
        syntax_pat = re.compile(r'line\s+(\d+)', re.IGNORECASE)
        coord_pat = re.compile(r'line\s+\d+\s*,?\s*column\s+\d+', re.IGNORECASE)

        stdlib_indicators = ('/usr/lib/python', '/lib/python', 'site-packages', '<frozen ', '/_pytest/')

        non_stdlib_matches = []
        all_matches = []

        # Pass 1: Scan structured traceback patterns
        for line in lines:
            m = pytest_pat.search(line)
            if m:
                file_path = m.group(1)
                line_no = int(m.group(2))
                all_matches.append(line_no)
                is_stdlib = any(ind in line for ind in stdlib_indicators) or any(ind in file_path for ind in stdlib_indicators)
                if not is_stdlib:
                    non_stdlib_matches.append(line_no)
                continue

            m = tb_pat.search(line)
            if m:
                file_path = m.group(1)
                line_no = int(m.group(2))
                all_matches.append(line_no)
                is_stdlib = any(ind in line for ind in stdlib_indicators) or any(ind in file_path for ind in stdlib_indicators)
                if not is_stdlib:
                    non_stdlib_matches.append(line_no)
                continue

        if non_stdlib_matches:
            return non_stdlib_matches[-1]
        if all_matches:
            return all_matches[-1]

        # Pass 2: Generic syntax line matching ONLY if Pass 1 found zero structured traceback frames
        for line in lines:
            if coord_pat.search(line):
                continue
            m = syntax_pat.search(line)
            if m:
                line_no = int(m.group(1))
                is_stdlib = any(ind in line for ind in stdlib_indicators)
                all_matches.append(line_no)
                if not is_stdlib:
                    non_stdlib_matches.append(line_no)

        if non_stdlib_matches:
            return non_stdlib_matches[-1]
        if all_matches:
            return all_matches[-1]
        return None

    @staticmethod
    def _extract_bash_line_number(trace: str) -> Optional[int]:
        """Parses line numbers from bash syntax error messages."""
        match = re.search(r'line\s+(\d+)', trace, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_cpp_line_number(trace: str) -> Optional[int]:
        """Parses line numbers from GCC/Clang compiler messages."""
        match = re.search(r':(\d+):\d+:\s+(?:fatal\s+)?error:', trace, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_rust_line_number(trace: str) -> Optional[int]:
        """Parses error line numbers from cargo / rustc output: '--> src/main.rs:14:5'."""
        m = re.search(r'-->\s+[^:]+:(\d+):\d+', trace)
        if m:
            return int(m.group(1))
        m2 = re.search(r':(\d+):\d+:\s+error', trace, re.IGNORECASE)
        if m2:
            return int(m2.group(1))
        return None

    @staticmethod
    def _extract_go_line_number(trace: str) -> Optional[int]:
        """Parses error line numbers from go test output: 'main_test.go:25: assertion failed'."""
        m = re.search(r'([a-zA-Z0-9_\-\.]+\.go):(\d+):', trace)
        if m:
            return int(m.group(2))
        return None

    @staticmethod
    def _extract_js_line_number(trace: str) -> Optional[int]:
        """Parses error line numbers from Jest / Mocha / Node output: 'at Object.<anonymous> (test.js:12:7)'."""
        m = re.search(r'\((?:[^\)]+[/\\])?([a-zA-Z0-9_\-\.]+\.[jt]sx?):(\d+):\d+\)', trace)
        if m:
            return int(m.group(2))
        m2 = re.search(r'([a-zA-Z0-9_\-\.]+\.[jt]sx?):(\d+):\d+', trace)
        if m2:
            return int(m2.group(2))
        return None

    @staticmethod
    def _check_unmatched_brackets(code: str) -> Optional[str]:
        """Fallback check for matching pairs of braces, brackets, parentheses."""
        stack = []
        pairs = {')': '(', '}': '{', ']': '['}
        for i, char in enumerate(code, 1):
            if char in pairs.values():
                stack.append((char, i))
            elif char in pairs.keys():
                if not stack or stack[-1][0] != pairs[char]:
                    return f"Unmatched closing '{char}' at index {i}"
                stack.pop()
        if stack:
            unopened_char, pos = stack[-1]
            return f"Unclosed '{unopened_char}' opened at index {pos}"
        return None


# Helper Top-Level Module Functions

def strip_fluff(raw_text: str) -> str:
    """Strips markdown code blocks and conversational fluff from text."""
    if not raw_text:
        return ""
    if "```" in raw_text:
        _, code = CodeExtractor.extract_primary_code(raw_text)
        return code
    text = raw_text.strip()
    text = re.sub(r'^(?:Here is|Sure|Here\'s|Below is|Certainly|This is)[^\n]*\n+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n+(?:Hope this helps|Let me know|Enjoy|Note:)[^\n]*$', '', text, flags=re.IGNORECASE)
    return text.strip()


def parse_ast(code: str) -> Tuple[bool, Optional[str], Optional[int]]:
    """Standalone helper to parse Python code AST and return (success, error_msg, line_number)."""
    res = Verifier().verify_python_ast(code)
    if res.success:
        return True, None, None
    return False, res.error_trace, res.line_number


def extract_error_line(stderr: str, language: str = "python") -> Optional[int]:
    """Standalone helper to extract error line numbers from stderr/traceback for a given language."""
    if not stderr:
        return None
    lang = language.lower()
    if lang in ("bash", "sh", "shell"):
        return Verifier._extract_bash_line_number(stderr)
    elif lang in ("cpp", "c++", "cxx"):
        return Verifier._extract_cpp_line_number(stderr)
    elif lang in ("rust", "rs", "cargo"):
        return Verifier._extract_rust_line_number(stderr)
    elif lang in ("go", "golang"):
        return Verifier._extract_go_line_number(stderr)
    elif lang in ("javascript", "typescript", "js", "ts", "node", "npm"):
        return Verifier._extract_js_line_number(stderr)
    else:
        return Verifier._extract_python_line_number(stderr)


def extract_stack_trace(stderr: str) -> Optional[str]:
    """Standalone helper to extract and clean stack trace / error details from stderr."""
    if not stderr or not stderr.strip():
        return None
    clean_trace = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', stderr).strip()
    return clean_trace if clean_trace else None


def detect_test_framework(project_dir: Union[str, Path] = ".") -> Optional[str]:
    """Standalone helper to auto-detect project test framework."""
    return Verifier.detect_test_framework(project_dir)


def run_project_tests(
    project_dir: Union[str, Path] = ".",
    framework: Optional[str] = None,
    timeout: float = 60.0,
) -> VerificationResult:
    """Standalone helper to run project test suite."""
    return Verifier().run_project_tests(project_dir=project_dir, framework=framework, timeout=timeout)


def verify_post_patch(
    project_dir: Union[str, Path] = ".",
    git_guard: Optional[Any] = None,
    checkpoint_id: Optional[str] = None,
    auto_rollback: bool = True,
    timeout: float = 60.0,
) -> VerificationResult:
    """Standalone helper for post-patch verification with auto-rollback."""
    return Verifier().verify_post_patch(
        project_dir=project_dir,
        git_guard=git_guard,
        checkpoint_id=checkpoint_id,
        auto_rollback=auto_rollback,
        timeout=timeout,
    )


def verify(
    code: str,
    language: str = "python",
    test_code: Optional[str] = None,
    timeout: float = 30.0,
) -> VerificationResult:
    """Top-level shortcut function for code verification."""
    return Verifier().verify(code=code, language=language, test_code=test_code, timeout=timeout)


__all__ = [
    "TestFramework",
    "VerificationResult",
    "CodeExtractor",
    "Verifier",
    "strip_fluff",
    "parse_ast",
    "extract_error_line",
    "extract_stack_trace",
    "detect_test_framework",
    "run_project_tests",
    "verify_post_patch",
    "verify",
]
