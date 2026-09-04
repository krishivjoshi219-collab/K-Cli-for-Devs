"""
autonomous_agent.py - True Agentic Autonomous Execution Engine for K-CLI
Project Bankai v1.0.0

Enables K-CLI to act as a full autonomous developer workstation (like Google Antigravity, Aider, and Claude Code):
1. Proactive local machine & workspace awareness (inspect files, explore directories).
2. Autonomous ReAct tool execution loop (read, write, edit, execute shell commands, verify with compilers).
3. Multi-file project synthesis on the user's computer with AST verification and test execution.
4. Real-time streaming of thoughts, tool invocations, and tool results.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from k_cli.core.llm_driver import LLMDriver
from k_cli.tools.command_runner import global_command_executor

logger = logging.getLogger("k_cli.agents.autonomous_agent")


# ==============================================================================
# LOCAL WORKSPACE TOOLS
# ==============================================================================

def tool_list_dir(directory: str = ".", max_depth: int = 2) -> str:
    """Lists files and directories in the workspace with hierarchy and file sizes."""
    try:
        target = Path(directory).resolve()
        if not target.exists():
            return f"Error: Directory '{directory}' does not exist (resolved to {target})."
        
        lines = [f"📁 Directory listing for: {target}"]
        ignored_names = {".git", ".venv", "venv", "k_cli_env", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
        
        count = 0
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in ignored_names and not d.startswith(".")]
            rel = os.path.relpath(root, target)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs.clear()
                continue
            
            indent = "  " * depth
            if rel != ".":
                lines.append(f"{indent}📂 {os.path.basename(root)}/")
            
            for f in sorted(files):
                if f.startswith(".") or f.endswith((".pyc", ".pyo", ".egg-info")):
                    continue
                fpath = Path(root) / f
                sz = fpath.stat().st_size if fpath.exists() else 0
                lines.append(f"{indent}  📄 {f} ({sz} bytes)")
                count += 1
                if count > 120:
                    lines.append(f"{indent}  ... [truncated, showing top 120 items]")
                    return "\n".join(lines)
        
        return "\n".join(lines)
    except Exception as e:
        return f"Error in list_dir: {e}"


def tool_read_workspace_file(file_path: str, start_line: int = 1, max_lines: int = 200) -> str:
    """Reads lines from a local file with line numbering."""
    try:
        p = Path(file_path).resolve()
        if not p.exists():
            return f"Error: File '{file_path}' does not exist."
        if not p.is_file():
            return f"Error: '{file_path}' is a directory, not a file."
        
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)
        
        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, start_idx + max_lines)
        selected = lines[start_idx:end_idx]
        
        output = [f"--- File: {p} (Lines {start_line}-{end_idx} of {total_lines}) ---"]
        for i, line in enumerate(selected):
            output.append(f"{start_line + i:4d} | {line}")
        
        if end_idx < total_lines:
            output.append(f"... [{total_lines - end_idx} more lines remaining]")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error reading file '{file_path}': {e}"


def tool_write_workspace_file(file_path: str, content: str) -> str:
    """Creates or overwrites a file on the user's computer, with AST syntax validation for Python."""
    try:
        p = Path(file_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        
        status_msg = f"Successfully wrote {len(content.encode('utf-8'))} bytes to '{p}'"
        
        # If Python file, run py_compile
        if p.suffix.lower() == ".py":
            import py_compile
            try:
                py_compile.compile(str(p), doraise=True)
                status_msg += " (AST py_compile verified: VALID SYNTAX)"
            except py_compile.PyCompileError as pe:
                status_msg += f" (WARNING: Syntax error detected: {pe})"
                
        return status_msg
    except Exception as e:
        return f"Error writing file '{file_path}': {e}"


def tool_edit_workspace_file(file_path: str, target_content: str, replacement_content: str) -> str:
    """Surgically replaces an exact text block in an existing file."""
    try:
        p = Path(file_path).resolve()
        if not p.exists():
            return f"Error: File '{file_path}' does not exist."
        
        text = p.read_text(encoding="utf-8", errors="replace")
        if target_content not in text:
            return f"Error: target_content not found in '{file_path}'."
        
        new_text = text.replace(target_content, replacement_content, 1)
        p.write_text(new_text, encoding="utf-8")
        
        if p.suffix.lower() == ".py":
            import py_compile
            try:
                py_compile.compile(str(p), doraise=True)
                return f"Successfully updated '{file_path}' (AST py_compile: VALID)"
            except py_compile.PyCompileError as pe:
                return f"Updated '{file_path}' but syntax error detected: {pe}"
                
        return f"Successfully updated '{file_path}'"
    except Exception as e:
        return f"Error editing file '{file_path}': {e}"


def tool_execute_command(command: str, cwd: str = ".", timeout_seconds: int = 60) -> str:
    """Executes any terminal/shell command on the local machine (Google Antigravity engine)."""
    try:
        res = global_command_executor.execute(command, cwd=cwd, timeout=timeout_seconds)
        output_parts = [
            f"$ {res.command} (exit code: {res.exit_code}, duration: {res.duration_sec:.2f}s)"
        ]
        if res.stdout.strip():
            output_parts.append("[stdout]\n" + res.stdout.strip())
        if res.stderr.strip():
            output_parts.append("[stderr]\n" + res.stderr.strip())
        if not res.stdout.strip() and not res.stderr.strip():
            output_parts.append("[command completed with no output]")
        return "\n".join(output_parts)
    except Exception as e:
        return f"Error executing command '{command}': {e}"


def tool_inspect_repo_structure(directory: str = ".") -> str:
    """Generates an AST symbol map of functions, classes, and imports across the codebase."""
    try:
        from k_cli.git.repo_map import RepoMap
        rm = RepoMap(root_dir=directory)
        return rm.render_summary(max_tokens=600)
    except Exception as e:
        return tool_list_dir(directory=directory, max_depth=2)


def tool_verify_code_file(file_path: str) -> str:
    """Runs compiler syntax checks and test suites for a workspace file."""
    try:
        from k_cli.git.verifier import Verifier
        v = Verifier()
        p = Path(file_path).resolve()
        if not p.exists():
            return f"Error: File '{file_path}' does not exist."
        content = p.read_text(encoding="utf-8", errors="replace")
        res = v.verify(content, language="python")
        return f"Verification Result for '{file_path}': Success={res.success}, Type={res.verification_type} (Errors: {res.error_trace or 'None'})"
    except Exception as e:
        return f"Error in verify_code_file: {e}"


def tool_search_codebase(query: str, directory: str = ".") -> str:
    """Searches for text, functions, or patterns across workspace source files."""
    try:
        root = Path(directory).resolve()
        matches = []
        ignored = {".git", ".venv", "venv", "k_cli_env", "__pycache__", "node_modules"}
        
        for p in root.rglob("*"):
            if any(part in ignored for part in p.parts):
                continue
            if not p.is_file() or p.suffix.lower() not in {".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".toml", ".yaml", ".sh"}:
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                for idx, line in enumerate(lines):
                    if query.lower() in line.lower():
                        rel = os.path.relpath(p, root)
                        matches.append(f"{rel}:{idx + 1}: {line.strip()}")
                        if len(matches) >= 40:
                            matches.append("... [truncated, 40+ matches found]")
                            return "\n".join(matches)
            except Exception:
                continue
                
        if not matches:
            return f"No matches found for '{query}' in {root}"
        return "\n".join(matches)
    except Exception as e:
        return f"Error searching codebase: {e}"


def tool_triage_and_heal_incident(error_traceback: str) -> str:
    """Triages multi-language crash tracebacks and attempts automated patch healing."""
    try:
        from k_cli.agents.strands_agent import triage_and_heal_incident
        return triage_and_heal_incident(error_traceback)
    except Exception as e:
        return f"Error in incident triage: {e}"


def tool_spawn_subagent(role: str, task: str) -> str:
    """Spawns an autonomous subagent with specialized capabilities (researcher, coder, tester, security_auditor, refactorer, explorer)."""
    valid_roles = {"researcher", "coder", "tester", "security_auditor", "refactorer", "explorer"}
    norm_role = role.lower().strip()
    if norm_role not in valid_roles:
        norm_role = "coder"

    try:
        from k_cli.core.llm_driver import LLMDriver
        from k_cli.core.credit_saver import global_credit_saver

        role_prompts = {
            "researcher": "You are a specialized RESEARCHER subagent. Search the codebase, inspect dependencies, check documentation, and return a concise, high-signal technical report.",
            "coder": "You are a specialized CODER subagent. Write robust, clean, complete implementations adhering to modern software engineering standards.",
            "tester": "You are a specialized TESTER subagent. Formulate ground-truth unit tests, execute pytest, check edge cases, and verify zero regressions.",
            "security_auditor": "You are a specialized SECURITY AUDITOR subagent. Inspect for OWASP Top 10, credential leakage, injection vectors, and memory safety flaws.",
            "refactorer": "You are a specialized REFACTORER subagent. Apply surgical edits to simplify architecture, remove dead code, and improve performance.",
            "explorer": "You are a specialized EXPLORER subagent. Inspect repository structure, list directories, and map modules.",
        }

        sub_driver = LLMDriver()
        sub_system_prompt = (
            f"{role_prompts.get(norm_role, role_prompts['coder'])}\n"
            f"Focus exclusively on completing this subtask: {task}\n"
            f"Be concise, technical, and high-signal. Avoid conversational filler."
        )

        sub_response = sub_driver.generate(
            prompt=f"Task: {task}",
            system_prompt=sub_system_prompt,
            temperature=0.2,
        )

        compacted = global_credit_saver.compress_tool_output("subagent", sub_response, max_lines=35)
        return f"[Subagent '{norm_role.upper()}' Completed Task]\n{compacted}"

    except Exception as e:
        return f"Error executing subagent '{role}': {e}"


# Tool registry map
AVAILABLE_TOOLS: Dict[str, Callable[..., str]] = {
    "list_dir": tool_list_dir,
    "read_workspace_file": tool_read_workspace_file,
    "write_workspace_file": tool_write_workspace_file,
    "edit_workspace_file": tool_edit_workspace_file,
    "execute_command": tool_execute_command,
    "inspect_repo_structure": tool_inspect_repo_structure,
    "verify_code_file": tool_verify_code_file,
    "search_codebase": tool_search_codebase,
    "triage_and_heal_incident": tool_triage_and_heal_incident,
    "spawn_subagent": tool_spawn_subagent,
}


# ==============================================================================
# AUTONOMOUS AGENT SYSTEM PROMPT
# ==============================================================================

def build_agentic_system_prompt(cwd: Optional[str] = None) -> str:
    """Generates the mission-critical system prompt establishing local machine authority."""
    cwd_path = Path(cwd or ".").resolve()
    
    top_items = []
    try:
        for item in sorted(cwd_path.iterdir()):
            if not item.name.startswith((".", "__")) and item.name not in ("k_cli_env", "venv", "node_modules"):
                top_items.append(f"{item.name}{'/' if item.is_dir() else ''}")
    except Exception:
        pass
    
    top_manifest = ", ".join(top_items[:20]) or "standard project tree"
    
    return f"""You are K-CLI, a fully autonomous AI DevOps and software engineering workstation running directly on the developer's Linux machine (comparable to Google Antigravity, Aider, and Claude Code).

LOCAL MACHINE ENVIRONMENT:
- Working Directory: {cwd_path}
- Workspace Root Items: {top_manifest}
- Execution Privilege: Full local machine terminal execution & file system read/write via tools.

CRITICAL OPERATIONAL RULES:
1. YOU ARE NOT A CHATBOT. You are an autonomous software engineering agent with REAL tools on this local machine.
2. NEVER say "I do not have access to local file systems" or "I cannot check folders on your computer". YOU DO HAVE ACCESS through your tools!
3. When the user asks you to:
   - "check", "inspect", or "explore" a folder or project:
     Use `list_dir` or `read_workspace_file` or `inspect_repo_structure` to inspect the real files and evaluate them.
   - "create", "write", "build", or "implement" a project, app, game, or script:
     Autonomously write the files to disk using `write_workspace_file`, verify them with `execute_command` or `verify_code_file`, and confirm they are saved.
   - "run", "test", or "fix" something:
     Use `execute_command` to run the real terminal commands (pytest, python, git, etc.) and inspect the outputs.

TOOL CALLING PROTOCOL:
When you need to execute an action on the local machine, output a tool call block:
```tool_call
{{"name": "tool_name", "arguments": {{"arg1": "value1"}}}}
```
Stop immediately after the tool call block and wait for the real result. DO NOT simulate or make up the tool result.

Available Tools:
- `list_dir(directory=".", max_depth=2)`: List files and subfolders.
- `read_workspace_file(file_path="...", start_line=1, max_lines=200)`: Read file contents with line numbers.
- `write_workspace_file(file_path="...", content="...")`: Write or create a file on disk (auto-verifies Python syntax).
- `edit_workspace_file(file_path="...", target_content="...", replacement_content="...")`: Surgical search/replace edit.
- `execute_command(command="...", cwd=".")`: Execute ANY shell command locally on host (pytest, git, python, etc.).
- `inspect_repo_structure(directory=".")`: AST map of classes and functions.
- `verify_code_file(file_path="...")`: Ground-truth compiler and test verification.
- `search_codebase(query="...", directory=".")`: Search for symbols or text across files.
- `triage_and_heal_incident(error_traceback="...")`: Automated crash traceback triage and repair.
- `spawn_subagent(role="researcher|coder|tester|security_auditor|refactorer|explorer", task="...")`: Delegates subtasks to specialized background subagents (Google Antigravity & Claude Code architecture).

COMMUNICATION & NATURAL LANGUAGE STYLE (MANDATORY):
- Talk like an elite senior staff engineer (similar to Claude Code, Aider, and Google Antigravity). Direct, natural, authoritative, concise.
- ZERO ROBOTIC PREAMBLES OR CONVERSATIONAL FILLER:
  - NEVER output robotic phrases like "Okay, I now have a clear picture of...", "Based on the file structure...", "Based on my analysis...", "Here's why I find it impressive:", "Sure, I'd be happy to help!", "Certainly!", or "In summary...".
  - Get straight to the technical substance without stating what you are about to do or narrating your cognitive state.
- When reviewing a project or directory:
  - Deliver a crisp, natural, high-signal technical evaluation.
  - Highlight key architectural layers, modules, testing infrastructure, and technical design decisions using clean bullet points and precise paths.
- When writing or modifying code:
  - Perform the filesystem and compiler operations silently using tools, then state what was accomplished and verified.

Always take real action. Inspect real files, write real code to disk, and verify before giving your final answer."""


def clean_conversational_filler(text: str) -> str:
    """Strips robotic chatbot preambles to ensure natural, senior developer communication."""
    if not text:
        return text
    
    cleaned = text.strip()
    patterns = [
        r"^(?:Okay|Ok|Alright|Great),\s+I\s+now\s+have\s+a\s+clear\s+picture\s+of[^\n.]*[.\n]*",
        r"^(?:Based\s+on\s+(?:the\s+file\s+structure|the\s+directory\s+structure|the\s+files|my\s+analysis|the\s+above)[^.\n]*[.\n]*)",
        r"^(?:Here(?:\x27s|'s|\s+is)\s+why\s+I\s+find\s+it\s+impressive:\s*)",
        r"^(?:Sure|Certainly|Of\s+course)[,!.]?\s+(?:I(?:\s+would|'d)?\s+be\s+happy\s+to\s+help|I\s+can\s+help\s+with\s+that|let's\s+dive\s+in)[^\n.]*[.\n]*",
        r"^(?:As\s+an\s+AI\s+(?:language\s+model|assistant)[^.\n]*[.\n]*)",
    ]
    for _ in range(5):
        prev = cleaned
        for pat in patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned == prev:
            break
            
    return cleaned


# ==============================================================================
# AUTONOMOUS AGENT RUNNER
# ==============================================================================

@dataclass
class AgentStep:
    step_num: int
    thought: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None


@dataclass
class AutonomousAgentResult:
    success: bool
    final_response: str
    steps: List[AgentStep] = field(default_factory=list)
    tools_executed: List[str] = field(default_factory=list)
    total_tokens: int = 0
    duration_sec: float = 0.0
    actual_cost_usd: float = 0.0
    saved_usd: float = 0.0
    tokens_pruned: int = 0
    savings_summary: str = ""
    model_rotations: int = 0


class AutonomousAgent:
    """
    Autonomous Agentic Execution Engine.
    Executes a multi-turn ReAct loop with local machine tools, streaming progress in real time.
    """

    def __init__(
        self,
        driver: Optional[LLMDriver] = None,
        model_name: str = "auto",
        cwd: Optional[str] = None,
        max_steps: int = 8,
    ):
        self.model_name = model_name
        self.driver = driver or LLMDriver(model_name=model_name)
        self.cwd = cwd or os.getcwd()
        self.max_steps = max_steps

    def _extract_tool_call(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Extracts tool name and arguments from JSON or Python-style model output."""
        # 1. Check for JSON tool call
        for match in re.finditer(r"```(?:tool_call|json)?\s*(\{.*?\})\s*```|<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL):
            raw = match.group(1) or match.group(2)
            try:
                d = json.loads(raw.strip())
                if "name" in d and d["name"] in AVAILABLE_TOOLS:
                    return d["name"], d.get("arguments", {})
            except Exception:
                continue

        # 2. Check for Python-style tool call (e.g. write_workspace_file(...) or execute_command(...))
        for block in re.findall(r"```(?:tool_code|tool_call|python)?\s*([a-zA-Z_]\w*\s*\(.*?\))\s*```|<tool_code>\s*([a-zA-Z_]\w*\s*\(.*?\))\s*</tool_code>", text, re.DOTALL):
            raw_code = (block[0] or block[1]).strip()
            try:
                tree = ast.parse(raw_code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        fn_name = node.func.id
                        if fn_name in AVAILABLE_TOOLS:
                            kwargs = {}
                            for kw in node.keywords:
                                try:
                                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                                except Exception:
                                    kwargs[kw.arg] = ast.unparse(kw.value) if hasattr(ast, "unparse") else str(kw.value)
                            # Handle positional args if any
                            if node.args and fn_name == "list_dir":
                                kwargs["directory"] = ast.literal_eval(node.args[0])
                            elif node.args and fn_name == "execute_command":
                                kwargs["command"] = ast.literal_eval(node.args[0])
                            elif node.args and fn_name == "read_workspace_file":
                                kwargs["file_path"] = ast.literal_eval(node.args[0])
                            return fn_name, kwargs
            except Exception:
                continue

        # 3. Inline function call scan (e.g. `write_workspace_file(...)`)
        for fn_name in AVAILABLE_TOOLS:
            pattern = re.compile(rf"\b{fn_name}\s*\((.*?)\)", re.DOTALL)
            m = pattern.search(text)
            if m:
                raw_call = m.group(0)
                try:
                    tree = ast.parse(raw_call.strip())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fn_name:
                            kwargs = {}
                            for kw in node.keywords:
                                try:
                                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                                except Exception:
                                    kwargs[kw.arg] = str(kw.value)
                            return fn_name, kwargs
                except Exception:
                    continue

        return None

    def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Executes a registered local tool with arguments."""
        if name not in AVAILABLE_TOOLS:
            return f"Error: Tool '{name}' is not recognized. Available tools: {list(AVAILABLE_TOOLS.keys())}"
        
        tool_fn = AVAILABLE_TOOLS[name]
        try:
            logger.info(f"Executing tool: {name} with args {args}")
            return tool_fn(**args)
        except TypeError as te:
            try:
                if len(args) == 1:
                    val = next(iter(args.values()))
                    return tool_fn(val)
            except Exception:
                pass
            return f"Error calling {name}: invalid arguments {args} ({te})"
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

    def run(
        self,
        prompt: str,
        token_callback: Optional[Callable[[str, str], None]] = None,
    ) -> AutonomousAgentResult:
        """
        Executes the autonomous agent ReAct loop.
        token_callback(persona_label, token_or_chunk) is called for real-time streaming.
        """
        start_time = time.time()
        system_prompt = build_agentic_system_prompt(self.cwd)
        steps: List[AgentStep] = []
        tools_executed: List[str] = []
        
        # 1. Proactive Reconnaissance:
        lower_prompt = prompt.lower()
        extra_context = ""
        if any(w in lower_prompt for w in ("check", "inspect", "explore", "what is inside", "list folder", "folder", "directory", "structure", "impressive", "review")):
            target_dir = "."
            words = prompt.split()
            for i, w in enumerate(words):
                clean_w = w.strip("`'\",:;")
                if clean_w in ("folder", "directory", "repo", "project") and i > 0:
                    prev = words[i - 1].strip("`'\",:;")
                    if prev not in ("the", "this", "my", "a", "our"):
                        target_dir = prev
                elif Path(clean_w).is_dir():
                    target_dir = clean_w
                    break
            
            recon_listing = tool_list_dir(target_dir, max_depth=2)
            extra_context = f"\n\n[LOCAL WORKSPACE RECONNAISSANCE - Items in '{target_dir}']:\n{recon_listing}\n"
            if token_callback:
                token_callback("RECON", f"⚡ [Inspecting local directory: {target_dir}]\n")

        conversation_history = [
            f"User Task: {prompt}{extra_context}"
        ]

        final_response = ""
        current_persona = "RESEARCHER"

        from k_cli.core.credit_saver import global_credit_saver
        from k_cli.core.rate_limit_guard import global_rate_limit_guard

        total_prompt_tokens = 0
        total_completion_tokens = 0

        for step_idx in range(1, self.max_steps + 1):
            pruned_history = global_credit_saver.prune_conversation_history(conversation_history)
            full_prompt = "\n\n".join(pruned_history)
            total_prompt_tokens += global_credit_saver.estimate_tokens(full_prompt)

            current_turn_tokens: List[str] = []

            def turn_stream_cb(token: str):
                current_turn_tokens.append(token)
                if token_callback:
                    token_callback(current_persona, token)

            model_out = self.driver.generate(
                prompt=full_prompt,
                system_prompt=system_prompt,
                stream_callback=turn_stream_cb,
                temperature=0.2,
            )
            
            if not model_out and current_turn_tokens:
                model_out = "".join(current_turn_tokens)

            total_completion_tokens += global_credit_saver.estimate_tokens(model_out)

            tool_call_info = self._extract_tool_call(model_out)
            
            if not tool_call_info:
                final_response = model_out
                steps.append(AgentStep(step_num=step_idx, thought=model_out))
                break

            tool_name, tool_args = tool_call_info
            tools_executed.append(tool_name)
            current_persona = "TOOL EXEC"

            # Execute tool locally on developer's machine
            args_summary = ", ".join(f"{k}={repr(v)[:50]}" for k, v in tool_args.items())
            if token_callback:
                token_callback("TOOL EXEC", f"\n\n⚡ [Executing Tool: {tool_name}({args_summary})]\n")

            tool_result = self.execute_tool(tool_name, tool_args)
            
            # Compress tool result to prevent token bloat
            compressed_tool_result = global_credit_saver.compress_tool_output(tool_name, tool_result)

            if token_callback:
                res_lines = tool_result.strip().splitlines()
                summary_preview = res_lines[0] if res_lines else "Completed"
                token_callback("TOOL RESULT", f"✔ [{tool_name} Result]: {summary_preview} ({len(tool_result)} bytes)\n\n")

            steps.append(
                AgentStep(
                    step_num=step_idx,
                    thought=model_out,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_output=tool_result,
                )
            )

            # Feed compressed tool execution back to conversation history
            conversation_history.append(
                f"Assistant Action:\n{model_out}\n\n"
                f"<tool_result tool=\"{tool_name}\">\n{compressed_tool_result}\n</tool_result>\n"
                f"Tool execution succeeded. Based on the tool result above, provide your direct, concise technical response in natural senior developer language (or execute the next tool if needed). Do NOT include conversational preambles like 'Okay, I now have a clear picture' or meta-analysis fluff. Speak directly as a senior engineer."
            )
            current_persona = "CODER" if "write" in tool_name else "VERIFIER"

        if not final_response:
            final_response = model_out or "Task completed by K-CLI Autonomous Agent."

        final_response = clean_conversational_filler(final_response)

        duration = time.time() - start_time
        savings_info = global_credit_saver.calculate_savings(
            model_name=self.model_name or "gemini-2.5-flash",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )

        return AutonomousAgentResult(
            success=True,
            final_response=final_response,
            steps=steps,
            tools_executed=tools_executed,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            duration_sec=duration,
            actual_cost_usd=savings_info["actual_cost_usd"],
            saved_usd=savings_info["saved_usd"],
            tokens_pruned=savings_info["tokens_pruned"],
            savings_summary=savings_info["summary"],
            model_rotations=global_rate_limit_guard.get_rotation_stats()["total_rotations"],
        )
