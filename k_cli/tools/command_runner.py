"""
command_runner.py - Local Machine Command Execution Engine for K-CLI
Project Bankai v1.0.0 — Built for AWS "Agents for Humans" Hackathon
Empowers K-CLI with Google Antigravity-grade local shell execution capabilities.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("k_cli.tools.command_runner")


@dataclass
class CommandExecutionResult:
    """Represents the outcome of a locally executed command."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    cwd: str
    success: bool = field(init=False)

    def __post_init__(self):
        self.success = (self.exit_code == 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_sec": round(self.duration_sec, 3),
            "cwd": self.cwd,
        }

    def summary(self) -> str:
        status_symbol = "✔" if self.success else "✖"
        lines = [
            f"{status_symbol} Command: `{self.command}` (Exit Code: {self.exit_code}, Duration: {self.duration_sec:.2f}s)",
        ]
        if self.stdout.strip():
            lines.append(f"--- STDOUT ---\n{self.stdout.strip()}")
        if self.stderr.strip():
            lines.append(f"--- STDERR ---\n{self.stderr.strip()}")
        return "\n".join(lines)


class LocalCommandExecutor:
    """
    Google Antigravity-grade local shell command executor.
    Executes commands on the developer's local machine with working directory management,
    stdout/stderr capture, and timeout safeguards.
    """

    def __init__(self, default_cwd: Optional[str] = None):
        self.default_cwd = str(Path(default_cwd or os.getcwd()).resolve())

    def _prepare_env(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        exec_env = os.environ.copy()
        venv_bin = os.path.join(sys.prefix, "bin")
        if os.path.exists(venv_bin):
            current_path = exec_env.get("PATH", "")
            if venv_bin not in current_path:
                exec_env["PATH"] = f"{venv_bin}:{current_path}"
        exec_env["PYTHONPATH"] = "/home/k/K-Cli-for-Devs"
        if env:
            exec_env.update(env)
        return exec_env

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
        sandbox: bool = False,
        sandbox_config: Optional[Any] = None,
    ) -> CommandExecutionResult:
        """
        Executes a shell command synchronously on the local machine with optional sandbox isolation.

        Args:
            command: The command line string to execute.
            cwd: Working directory (defaults to executor default_cwd).
            timeout: Maximum execution time in seconds (default 60).
            env: Custom environment variables dict.
            sandbox: If True, executes inside sovereign Bubblewrap/POSIX sandbox container.
            sandbox_config: Custom SandboxConfig.

        Returns:
            CommandExecutionResult containing exit code, stdout, stderr, and duration.
        """
        target_cwd = str(Path(cwd or self.default_cwd).resolve())
        exec_env = self._prepare_env(env)

        if sandbox:
            from k_cli.core.sandbox import global_sandbox_engine, SandboxConfig
            cfg = sandbox_config or SandboxConfig(timeout_sec=float(timeout))
            s_res = global_sandbox_engine.execute(
                command,
                cwd=target_cwd,
                config=cfg,
                timeout=float(timeout),
                env=exec_env,
            )
            return CommandExecutionResult(
                command=command,
                exit_code=s_res.exit_code,
                stdout=s_res.stdout,
                stderr=s_res.stderr,
                duration_sec=s_res.duration_sec,
                cwd=target_cwd,
            )

        start_time = time.time()
        logger.info(f"Executing local command: {command} in {target_cwd}")

        try:
            # Use bash on POSIX systems or cmd on Windows
            shell_executable = "/bin/bash" if os.name == "posix" and os.path.exists("/bin/bash") else None
            proc = subprocess.run(
                command,
                shell=True,
                cwd=target_cwd,
                env=exec_env,
                executable=shell_executable,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=timeout,
            )
            duration = time.time() - start_time
            return CommandExecutionResult(
                command=command,
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_sec=duration,
                cwd=target_cwd,
            )
        except subprocess.TimeoutExpired as te:
            duration = time.time() - start_time
            stdout = te.stdout if isinstance(te.stdout, str) else (te.stdout.decode("utf-8", "replace") if te.stdout else "")
            stderr = te.stderr if isinstance(te.stderr, str) else (te.stderr.decode("utf-8", "replace") if te.stderr else "")
            return CommandExecutionResult(
                command=command,
                exit_code=-1,
                stdout=stdout,
                stderr=f"{stderr}\n[Error] Command timed out after {timeout} seconds.",
                duration_sec=duration,
                cwd=target_cwd,
            )
        except Exception as exc:
            duration = time.time() - start_time
            return CommandExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"[Error] Failed to launch command: {exc}",
                duration_sec=duration,
                cwd=target_cwd,
            )

    async def execute_async(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandExecutionResult:
        """
        Asynchronously executes a shell command using asyncio.subprocess.
        """
        target_cwd = str(Path(cwd or self.default_cwd).resolve())
        exec_env = self._prepare_env(env)

        start_time = time.time()
        logger.info(f"Executing async local command: {command} in {target_cwd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=target_cwd,
                env=exec_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                executable="/bin/bash" if os.name == "posix" and os.path.exists("/bin/bash") else None,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(timeout)
                )
                duration = time.time() - start_time
                stdout_str = stdout_data.decode("utf-8", "replace") if stdout_data else ""
                stderr_str = stderr_data.decode("utf-8", "replace") if stderr_data else ""
                return CommandExecutionResult(
                    command=command,
                    exit_code=proc.returncode if proc.returncode is not None else 0,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    duration_sec=duration,
                    cwd=target_cwd,
                )
            except asyncio.TimeoutError:
                duration = time.time() - start_time
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                return CommandExecutionResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr=f"[Error] Command timed out after {timeout} seconds.",
                    duration_sec=duration,
                    cwd=target_cwd,
                )
        except Exception as exc:
            duration = time.time() - start_time
            return CommandExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"[Error] Failed to execute async command: {exc}",
                duration_sec=duration,
                cwd=target_cwd,
            )

    async def stream_output(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> AsyncIterator[str]:
        """
        Streams command stdout/stderr line-by-line as it executes.
        """
        target_cwd = str(Path(cwd or self.default_cwd).resolve())
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=target_cwd,
            env=exec_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            executable="/bin/bash" if os.name == "posix" and os.path.exists("/bin/bash") else None,
        )

        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", "replace")

        await proc.wait()


# Global default executor singleton
global_command_executor = LocalCommandExecutor()
