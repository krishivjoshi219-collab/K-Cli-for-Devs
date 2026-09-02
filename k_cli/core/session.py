"""
session.py - Interactive Multi-Turn Session & Command Hub for K-CLI (Project Bankai Engine v1.0.0)

Manages multi-turn conversation state, rolling token budgeting, active file context tracking,
slash command dispatching, DevDocs injection, AST repo map integration, surgical patch application,
and Git-guarded safety net operations.
"""

from __future__ import annotations

import os
import sys
import gc
import psutil
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple, Union

try:
    from k_cli.tools.doc_retriever import DocRetriever
    from k_cli.git.repo_map import RepoMap
    from k_cli.git.patcher import Patcher
    from k_cli.git.git_guard import GitGuard
    from k_cli.git.verifier import Verifier, CodeExtractor
    from k_cli.agents.orchestrator import Orchestrator, Persona, OrchestratorResult
    from k_cli.core.llm_driver import LLMDriver
    from k_cli.agents.persona import DomainPersona, PersonaProfile, PersonaRegistry
except (ModuleNotFoundError, ImportError):
    try:
        from doc_retriever import DocRetriever
        from repo_map import RepoMap
        from patcher import Patcher
        from git_guard import GitGuard
        from verifier import Verifier, CodeExtractor
        from orchestrator import Orchestrator, Persona, OrchestratorResult
        from k_cli.core.llm_driver import LLMDriver
        from persona import DomainPersona, PersonaProfile, PersonaRegistry
    except (ModuleNotFoundError, ImportError):
        from doc_retriever import DocRetriever
        from repo_map import RepoMap
        from patcher import Patcher
        from git_guard import GitGuard
        from verifier import Verifier, CodeExtractor
        from orchestrator import Orchestrator, Persona, OrchestratorResult
        from k_cli.core.llm_driver import LLMDriver
        PersonaProfile = Any  # type: ignore
        PersonaRegistry = None  # type: ignore
        DomainPersona = None  # type: ignore


class SessionManager:
    """
    Manages interactive multi-turn session state, active file context, rolling token budget,
    slash commands routing, and coordinates Knowledge, Modification, and Core Engine layers.
    """

    def __init__(
        self,
        workspace_dir: str = ".",
        model_name: Optional[str] = None,
        max_tokens: int = 4096,
        driver: Optional[LLMDriver] = None,
        verifier: Optional[Verifier] = None,
        doc_retriever: Optional[DocRetriever] = None,
        repo_map: Optional[RepoMap] = None,
        patcher: Optional[Patcher] = None,
        git_guard: Optional[GitGuard] = None,
        orchestrator: Optional[Orchestrator] = None,
        mock_mode: bool = False,
        persona: Optional[Union[str, PersonaProfile]] = None,
    ):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.model_name = model_name or "qwen2.5-coder:1.5b"
        self.max_tokens = max(1, max_tokens)
        mock_env = os.getenv("KCLI_MOCK_MODE", "").lower() in ("true", "1") or ("PYTEST_CURRENT_TEST" in os.environ and not os.getenv("K_CLI_REAL_LLM"))
        self.mock_mode = mock_mode or mock_env

        # Components
        self.driver = driver or LLMDriver(model_name=self.model_name, mock_mode=self.mock_mode)
        self.verifier = verifier or Verifier()
        self.doc_retriever = doc_retriever or DocRetriever()
        self.repo_map = repo_map or RepoMap(root_dir=str(self.workspace_dir))
        self.patcher = patcher or Patcher()
        self.git_guard = git_guard or GitGuard(repo_dir=str(self.workspace_dir))
        try:
            from k_cli.github.dedup_engine import DedupEngine
            dedup_eng = DedupEngine(repo_path=str(self.workspace_dir))
        except Exception:
            dedup_eng = None
        self.orchestrator = orchestrator or Orchestrator(driver=self.driver, verifier=self.verifier, dedup_engine=dedup_eng)

        # Context & History State
        self.context_files: List[str] = []
        self.history: List[Dict[str, Any]] = []
        self.last_result: Optional[Dict[str, Any]] = None
        self._last_snapshot: Optional[str] = None

        # Dynamic Persona Profile State
        self.active_persona_profile: Optional[PersonaProfile] = None
        if persona is not None:
            if isinstance(persona, PersonaProfile):
                self.active_persona_profile = persona
            elif PersonaRegistry:
                self.active_persona_profile = PersonaRegistry.get(persona) or PersonaRegistry.get_default()
        elif PersonaRegistry:
            self.active_persona_profile = PersonaRegistry.get_default()

        self.active_persona: str = self.active_persona_profile.title if self.active_persona_profile else "AUTO"
        if self.active_persona_profile and self.orchestrator:
            self.orchestrator.set_persona(self.active_persona_profile)

    def set_persona(self, persona_query: str) -> Tuple[bool, str]:
        """
        Switches active persona by name, alias, or pipeline phase.

        Args:
            persona_query: Query string or persona name (e.g. 'devops', 'surgical debugger', 'systems').

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        if not persona_query or not persona_query.strip():
            if PersonaRegistry:
                return True, PersonaRegistry.format_persona_table(self.active_persona_profile.id if self.active_persona_profile else None)
            return True, f"Active persona: [{self.active_persona}]"

        clean_query = persona_query.strip()

        # Check classic pipeline stage names first
        classic_stages = ["AUTO", "RESEARCHER", "ARCHITECT", "CODER", "CRITIC", "DEBUGGER", "DEFAULT"]
        query_upper = clean_query.upper()
        if query_upper in classic_stages:
            self.active_persona = query_upper
            if PersonaRegistry:
                self.active_persona_profile = PersonaRegistry.get(query_upper) or PersonaRegistry.get_default()
                if self.orchestrator:
                    self.orchestrator.set_persona(self.active_persona_profile)
            return True, f"Active persona set to [{self.active_persona}]."

        # Check PersonaRegistry for domain persona match
        if PersonaRegistry:
            matched_profile = PersonaRegistry.get(clean_query)
            if matched_profile is not None:
                self.active_persona_profile = matched_profile
                self.active_persona = matched_profile.title
                if self.orchestrator:
                    self.orchestrator.set_persona(matched_profile)
                return True, f"Switched active persona to [{matched_profile.title}] (/{matched_profile.id})."

        # If unknown, return helpful list of valid options
        if PersonaRegistry:
            table_msg = PersonaRegistry.format_persona_table(self.active_persona_profile.id if self.active_persona_profile else None)
            return False, f"Unknown persona '{persona_query}'.\n\n{table_msg}"

        return False, f"Unknown persona '{persona_query}'."

    def get_persona(self) -> str:
        """Returns the name of the currently active persona."""
        return self.active_persona

    def get_git_branch(self) -> str:
        """Returns the current active git branch name."""
        if hasattr(self.git_guard, "get_current_branch"):
            return self.git_guard.get_current_branch()
        return "main" if self.git_guard.is_git_repo() else "no-git"

    # --------------------------------------------------------------------------
    # File Context Management
    # --------------------------------------------------------------------------

    def add_file(self, file_path: str) -> bool:
        """
        Adds a file to the active session context.

        Args:
            file_path: Relative or absolute path to the file.

        Returns:
            True if file exists and was added (or is already present), False if file does not exist.
        """
        if not file_path:
            return False

        target_path = Path(file_path)
        if not target_path.is_absolute():
            target_path = self.workspace_dir / target_path

        if not target_path.exists() or not target_path.is_file():
            return False

        try:
            rel_path = str(target_path.relative_to(self.workspace_dir))
        except ValueError:
            rel_path = str(target_path.resolve())

        if rel_path not in self.context_files:
            self.context_files.append(rel_path)
        return True

    def remove_file(self, file_path: str) -> bool:
        """
        Removes a file from the active session context.

        Args:
            file_path: Relative or absolute path to the file.

        Returns:
            True if file was tracked and removed, False otherwise.
        """
        if not file_path:
            return False

        candidates = [file_path]
        target_path = Path(file_path)
        if not target_path.is_absolute():
            abs_p = self.workspace_dir / target_path
            try:
                candidates.append(str(abs_p.relative_to(self.workspace_dir)))
            except ValueError:
                pass
            candidates.append(str(abs_p.resolve()))
        else:
            try:
                candidates.append(str(target_path.relative_to(self.workspace_dir)))
            except ValueError:
                pass
            candidates.append(str(target_path.resolve()))

        for c in candidates:
            if c in self.context_files:
                self.context_files.remove(c)
                return True

        for f in list(self.context_files):
            if f == file_path or f.endswith("/" + file_path) or Path(f).name == file_path:
                self.context_files.remove(f)
                return True

        return False

    def get_context_files(self) -> List[str]:
        """Returns the list of currently tracked context files."""
        return list(self.context_files)

    # --------------------------------------------------------------------------
    # History & Memory Management
    # --------------------------------------------------------------------------

    def clear_history(self) -> None:
        """Clears conversation history turns."""
        self.history.clear()

    def reset_context(self) -> None:
        """Resets conversation history and context files."""
        self.history.clear()
        self.context_files.clear()

    def _estimate_tokens(self, text: str) -> int:
        """Estimates token count of a given string (approx 1 token per word)."""
        if not text:
            return 0
        return max(1, len(text.split()))

    def _calculate_current_tokens(self) -> int:
        """Calculates total estimated tokens in current history and context files."""
        total = 0
        for turn in self.history:
            total += self._estimate_tokens(turn.get("prompt", ""))
            total += self._estimate_tokens(turn.get("response", ""))
            total += self._estimate_tokens(turn.get("code", ""))

        for cf in self.context_files:
            fp = self.workspace_dir / cf
            if fp.exists() and fp.is_file():
                try:
                    total += self._estimate_tokens(fp.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return total

    def _prune_history_if_needed(self) -> None:
        """Prunes oldest history turns if total tokens exceed max_tokens budget."""
        while len(self.history) > 1 and self._calculate_current_tokens() > self.max_tokens:
            self.history.pop(0)

    @staticmethod
    def _get_current_ram_mb() -> float:
        """Returns current process memory consumption in Megabytes (RSS)."""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)

    def get_status(self) -> Dict[str, Any]:
        """
        Returns status dictionary with active model, context files, tokens, and RAM.
        """
        ram_mb = self._get_current_ram_mb()
        token_count = self._calculate_current_tokens()
        return {
            "model": self.model_name,
            "model_name": self.model_name,
            "persona": self.active_persona,
            "active_persona": self.active_persona,
            "git_branch": self.get_git_branch(),
            "context_files": list(self.context_files),
            "files": list(self.context_files),
            "turns": len(self.history),
            "history_len": len(self.history),
            "token_count": token_count,
            "tokens": token_count,
            "max_tokens": self.max_tokens,
            "ram_mb": ram_mb,
            "rss_mb": ram_mb,
            "is_git_repo": self.git_guard.is_git_repo(),
            "uncommitted_diff": bool(self.git_guard.get_diff().strip()) if self.git_guard.is_git_repo() else False,
        }

    def set_model(self, model_name: str) -> None:
        """Switches active model and re-initializes LLM driver."""
        self.model_name = model_name
        self.driver = LLMDriver(model_name=self.model_name, mock_mode=self.mock_mode)
        self.orchestrator = Orchestrator(driver=self.driver, verifier=self.verifier)

    def run_test(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """
        Runs ground-truth verification on a specified file, inline code, or workspace test.

        Returns:
            Tuple[bool, str]: (passed, result_summary)
        """
        if target:
            target_path = Path(target)
            if not target_path.is_absolute():
                target_path = self.workspace_dir / target_path
            if target_path.exists() and target_path.is_file():
                ext = target_path.suffix.lstrip(".").lower()
                lang = "python" if ext in ("py", "python") else "bash" if ext in ("sh", "bash") else "cpp" if ext in ("cpp", "cxx", "cc") else "python"
                code = target_path.read_text(encoding="utf-8")
                res = self.verifier.verify(code, language=lang)
                if res.success:
                    return True, f"✔ Target '{target}' passed ground-truth verification ({res.verification_type})."
                err = res.error_trace or "Verification failed."
                return False, f"✘ Target '{target}' failed verification at line {res.line_number or 'unknown'}:\n{err}"
            else:
                # Target is inline code
                res = self.verifier.verify(target, language="python")
                if res.success:
                    return True, f"✔ Inline code passed ground-truth verification ({res.verification_type})."
                err = res.error_trace or "Verification failed."
                return False, f"✘ Inline code failed verification at line {res.line_number or 'unknown'}:\n{err}"

        # If no target specified, verify tracked context files
        if self.context_files:
            failed = []
            for cf in self.context_files:
                tf = self.workspace_dir / cf
                if tf.exists() and tf.is_file():
                    res = self.verifier.verify(tf.read_text(encoding="utf-8"), language="python")
                    if not res.success:
                        failed.append(f"{cf}: {res.error_trace or 'verification failed'}")
            if not failed:
                return True, f"✔ All {len(self.context_files)} context file(s) passed verification."
            return False, f"✘ Verification failed for {len(failed)} file(s):\n" + "\n".join(failed)

        return True, "No specific target or context files provided to test."

    # --------------------------------------------------------------------------
    # Git Undo & Diff
    # --------------------------------------------------------------------------

    def undo_last_edit(self) -> Tuple[bool, str]:
        """
        Rolls back the last modification using GitGuard.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        if not self.git_guard.is_git_repo():
            return False, "Not inside a Git repository; cannot undo."

        diff = self.git_guard.get_diff()
        res_status = self.git_guard._run_git(["status", "--porcelain"])
        has_changes = bool(diff.strip() or (res_status.returncode == 0 and res_status.stdout.strip()))

        if not has_changes:
            return False, "No uncommitted changes to undo (working tree is clean)."

        success = self.git_guard.rollback()
        if success:
            return True, "Successfully rolled back uncommitted changes."
        return False, "Rollback failed."

    # --------------------------------------------------------------------------
    # Slash Commands Routing
    # --------------------------------------------------------------------------

    def handle_slash_command(self, command_str: str) -> Tuple[bool, str]:
        """
        Parses and handles slash commands.

        Commands supported:
          /add <file>      Add file to active session context
          /remove <file>   Remove file from active session context
          /undo            Roll back last uncommitted edit via Git
          /rollback [file] Roll back last uncommitted edit via Git (alias /undo)
          /diff            View uncommitted git diff in workspace
          /clear           Reset conversation history and context files
          /status          Display active model, context files, tokens, and RAM
          /model [name]    Switch active model or view current model
          /persona [name]  Switch active persona or view current persona
          /doc <query>     Search DevDocs offline documentation index
          /docs <query>    Search DevDocs offline documentation index (alias /doc)
          /test [target]   Run ground-truth verification on file/code
          /map             Display workspace AST symbol repository map
          /help            Show help message
          /exit, /quit     Exit session

        Returns:
            Tuple[bool, str]: (handled, output_message)
        """
        raw = command_str.strip()
        if not raw:
            return False, ""

        is_slash = raw.startswith("/")
        cmd_text = raw[1:].strip() if is_slash else raw
        parts = cmd_text.split(None, 1)
        if not parts:
            return False, ""

        cmd_name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Check command match
        if cmd_name in ("help", "?"):
            help_text = (
                "Available Slash Commands:\n"
                "  /model [name]    Switch active model (Bankai-7B, Bankai-14B, Gemini, Claude, Local Ollama)\n"
                "  /persona [name]  Switch active persona (RESEARCHER, ARCHITECT, CODER, CRITIC, DEBUGGER, AUTO)\n"
                "  /diff [mode]     View surgical / git diff (inline or side-by-side)\n"
                "  /rollback [file] Roll back last uncommitted edit via Git (alias /undo)\n"
                "  /help            Show this help message\n"
                "  /docs <query>    Search DevDocs offline documentation index (alias /doc)\n"
                "  /clear           Reset conversation history and context files\n"
                "  /test [file]     Run ground-truth compiler and pytest verification\n"
                "  /add <file>      Add file to active session context\n"
                "  /remove <file>   Remove file from active session context\n"
                "  /undo            Roll back last uncommitted edit via Git\n"
                "  /status          Display active model, context files, tokens, and RAM\n"
                "  /map             Display workspace AST symbol repository map\n"
                "  /exit, /quit     Exit interactive session"
            )
            return True, help_text

        elif cmd_name == "add":
            if not arg:
                return True, "Usage: /add <file_path>"
            if self.add_file(arg):
                return True, f"Added '{arg}' to active context."
            return True, f"Error: File '{arg}' not found."

        elif cmd_name in ("remove", "rm"):
            if not arg:
                return True, "Usage: /remove <file_path>"
            if self.remove_file(arg):
                return True, f"Removed '{arg}' from active context."
            return True, f"Error: File '{arg}' is not in active context."

        elif cmd_name in ("undo", "rollback"):
            if cmd_name == "rollback" and arg:
                if not self.git_guard.is_git_repo():
                    return True, "Not inside a Git repository; cannot rollback."
                success = self.git_guard.rollback(files=[arg])
                if success:
                    return True, f"Successfully rolled back uncommitted changes for '{arg}'."
                return True, f"Rollback failed for '{arg}'."
            success, msg = self.undo_last_edit()
            return True, msg

        elif cmd_name == "diff":
            if not self.git_guard.is_git_repo():
                return True, "Not inside a Git repository."
            diff_text = self.git_guard.get_diff()
            if not diff_text.strip():
                return True, "Working tree is clean; no uncommitted changes."
            return True, diff_text

        elif cmd_name in ("clear", "cls"):
            self.reset_context()
            return True, "Session history and context files cleared."

        elif cmd_name == "status":
            st = self.get_status()
            files_str = ", ".join(st["context_files"]) if st["context_files"] else "None"
            status_lines = [
                f"Active Model: {st['model']}",
                f"Active Persona: {st.get('persona', 'AUTO')}",
                f"Git Branch: {st.get('git_branch', 'no-git')}",
                f"Context Files: {files_str}",
                f"Conversation Turns: {st['turns']}",
                f"Estimated Tokens: {st['token_count']} / {st['max_tokens']}",
                f"Memory RSS: {st['ram_mb']:.2f} MB / 1024 MB",
                f"Git Repository: {'Yes' if st['is_git_repo'] else 'No'}",
            ]
            return True, "\n".join(status_lines)

        elif cmd_name == "model":
            if arg:
                self.set_model(arg)
                return True, f"Switched active model to '{arg}'."
            return True, f"Active model: '{self.model_name}'"

        elif cmd_name in ("persona", "role"):
            if not arg or arg.lower() in ("list", "show", "help"):
                if PersonaRegistry:
                    active_id = self.active_persona_profile.id if self.active_persona_profile else None
                    return True, PersonaRegistry.format_persona_table(active_id)
                return True, f"Active persona: [{self.active_persona}]"
            success, msg = self.set_persona(arg)
            return True, msg

        elif cmd_name in ("doc", "docs"):
            if not arg:
                return True, "Usage: /doc <query>" if cmd_name == "doc" else "Usage: /docs <query>"
            if self.doc_retriever:
                snippets = self.doc_retriever.format_context_snippets(arg, max_tokens=250)
                if not snippets.strip():
                    return True, f"No documentation found for '{arg}'."
                return True, snippets
            return True, "DocRetriever is not available."

        elif cmd_name in ("test", "verify"):
            passed, out_msg = self.run_test(arg if arg else None)
            return True, out_msg

        elif cmd_name == "map":
            if self.repo_map:
                map_str = self.repo_map.get_repo_map(max_tokens=400, focus_files=self.get_context_files())
                if not map_str.strip():
                    return True, "Repository map is empty."
                return True, map_str
            return True, "RepoMap is not available."

        elif cmd_name in ("subagents", "spawn", "team"):
            if not arg:
                return True, "Usage: /spawn <prompt> (or /subagents <prompt>)"
            try:
                from k_cli.agents.subagents import execute_subagents
            except ModuleNotFoundError:
                from subagents import execute_subagents
            res = execute_subagents(
                prompt=arg,
                context_files=self.get_context_files(),
                driver=self.driver,
                verifier=self.verifier,
                workspace_dir=self.workspace_dir,
                show_ui=True,
            )
            return True, f"Multi-Agent Run {'COMPLETED' if res.success else 'FAILED'}:\n{res.summary}"

        elif cmd_name in ("exit", "quit", "q"):
            return True, "EXIT"

        elif is_slash:
            return False, f"Unknown command '/{cmd_name}'. Type /help for available commands."

        return False, "Not a slash command."

    # --------------------------------------------------------------------------
    # Multi-Turn Execution & Streaming Pipeline
    # --------------------------------------------------------------------------

    def process_turn(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, Dict[str, Any]]:
        """
        Executes user prompt through full pipeline with streaming token output.

        Pipeline steps:
          1. Snapshot Git workspace checkpoint
          2. Retrieve relevant DevDocs snippets (< 250 tokens)
          3. Generate AST repository map (< 400 tokens)
          4. Inject active context file contents
          5. Call Orchestrator persona state machine with streaming
          6. Parse SEARCH/REPLACE surgical patch blocks
          7. Apply patches with AST verification
          8. Commit on success or rollback on AST/test failure
          9. Maintain rolling conversation token budget

        Yields:
            str: Generated tokens as they stream from LLM personas.

        Returns:
            Dict[str, Any]: Execution result summary.
        """
        cleaned_prompt = (prompt or "").strip()
        if not cleaned_prompt:
            res_dict = {
                "success": True,
                "output": "",
                "code": "",
                "attempts": 1,
                "ram_mb": self._get_current_ram_mb(),
                "history_len": len(self.history),
            }
            self.last_result = res_dict
            return res_dict

        # 1. Snapshot Git workspace
        if self.git_guard.is_git_repo():
            self._last_snapshot = self.git_guard.create_snapshot()

        # 2. Retrieve DevDocs context snippets
        doc_snippets = ""
        if self.doc_retriever:
            try:
                doc_snippets = self.doc_retriever.format_context_snippets(cleaned_prompt, max_tokens=250)
            except Exception:
                doc_snippets = ""

        # 3. Generate AST repository map
        repo_tree = ""
        if self.repo_map:
            try:
                repo_tree = self.repo_map.get_repo_map(max_tokens=400, focus_files=self.get_context_files())
            except Exception:
                repo_tree = ""

        # 4. Inject active context files
        context_files_text = ""
        for cf in self.context_files:
            fp = self.workspace_dir / cf
            if fp.exists() and fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8")
                    context_files_text += f"\nFile: {cf}\n```\n{content}\n```\n"
                except Exception:
                    pass

        # 5. Formulate enriched prompt
        prompt_sections = []
        if doc_snippets.strip():
            prompt_sections.append(f"DevDocs Reference Snippets:\n{doc_snippets.strip()}")
        if repo_tree.strip():
            prompt_sections.append(f"Workspace Repository Map:\n{repo_tree.strip()}")
        if context_files_text.strip():
            prompt_sections.append(f"Active Context Files:\n{context_files_text.strip()}")

        if self.history:
            history_lines = ["Recent Conversation History:"]
            for i, h in enumerate(self.history[-3:], 1):
                p_snip = h.get("prompt", "")[:120].replace("\n", " ")
                r_snip = h.get("response", "")[:120].replace("\n", " ")
                history_lines.append(f"User [{i}]: {p_snip}")
                history_lines.append(f"Assistant [{i}]: {r_snip}")
            prompt_sections.append("\n".join(history_lines))

        prompt_sections.append(f"User Task Request:\n{cleaned_prompt}")
        augmented_prompt = "\n\n".join(prompt_sections)

        # 6. Stream tokens from Orchestrator via worker thread
        token_q: queue.Queue = queue.Queue()
        pipeline_res: List[OrchestratorResult] = []
        pipeline_err: List[Exception] = []

        def _worker():
            try:
                def persona_cb(persona, tok: str):
                    token_q.put((persona, tok))
                    if stream_callback:
                        stream_callback(tok)

                orch_res = self.orchestrator.execute_pipeline(
                    user_prompt=augmented_prompt,
                    language="python",
                    token_stream_callback=persona_cb,
                    persona=self.active_persona_profile,
                )
                pipeline_res.append(orch_res)
            except Exception as exc:
                pipeline_err.append(exc)
            finally:
                token_q.put(None)

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        while True:
            item = token_q.get()
            if item is None:
                break
            _persona, token = item
            yield token

        worker_thread.join()

        if pipeline_err:
            final_code = ""
            success = False
            attempts = 1
            ram_mb = self._get_current_ram_mb()
        elif pipeline_res:
            res = pipeline_res[0]
            final_code = res.final_code
            success = res.success
            attempts = res.attempts
            ram_mb = res.ram_usage_mb
        else:
            final_code = ""
            success = False
            attempts = 1
            ram_mb = self._get_current_ram_mb()

        # 7. Check for SEARCH/REPLACE blocks and apply patches
        patch_blocks = self.patcher.parse_search_replace_blocks(final_code)
        patches_applied = False
        patch_error = ""

        if patch_blocks:
            # Apply to tracked context files
            target_files = [self.workspace_dir / f for f in self.context_files] if self.context_files else []
            if not target_files:
                # Find python files in workspace to test patch against
                target_files = list(self.workspace_dir.glob("*.py"))

            any_patch_succeeded = False
            for tf in target_files:
                if tf.is_file():
                    p_ok, p_err = self.patcher.apply_file_patches(str(tf), final_code, validate_ast=True)
                    if p_ok:
                        any_patch_succeeded = True
                    else:
                        patch_error = p_err

            if any_patch_succeeded:
                patches_applied = True
                success = True
                if self.git_guard.is_git_repo():
                    self.git_guard.commit_success(
                        f"feat: apply surgical patch for '{cleaned_prompt[:40]}'",
                        files=[str(tf.relative_to(self.workspace_dir)) for tf in target_files if tf.is_file()],
                    )
            else:
                # Rollback on patch failure
                if self.git_guard.is_git_repo():
                    self.git_guard.rollback()
                success = False

        # 8. Record history and enforce rolling token budget
        self.history.append({
            "prompt": cleaned_prompt,
            "response": final_code,
            "code": final_code,
            "success": success,
            "attempts": attempts,
            "patches_applied": patches_applied,
        })
        self._prune_history_if_needed()

        # Auto-persist session state to ~/.kcli/sessions/
        try:
            from k_cli.core.storage_manager import LocalStorageManager
            if not hasattr(self, "_session_id") or not self._session_id:
                self._session_id = f"session_{int(time.time())}"
            LocalStorageManager.save_session(
                session_id=self._session_id,
                workspace_dir=str(self.workspace_dir),
                active_model=self.model_name,
                active_persona=self.active_persona,
                context_files=self.context_files,
                history=self.history,
                git_branch=self.git_guard.get_current_branch() if hasattr(self.git_guard, "get_current_branch") else "main",
            )
        except Exception:
            pass

        res_dict = {
            "success": success,
            "output": final_code,
            "code": final_code,
            "attempts": attempts,
            "patches_applied": patches_applied,
            "patch_error": patch_error,
            "ram_mb": ram_mb,
            "history_len": len(self.history),
        }
        self.last_result = res_dict
        return res_dict

    @classmethod
    def load_latest(cls, workspace_dir: str = ".", mock_mode: bool = False) -> Optional[SessionManager]:
        """Restores the latest saved session from ~/.kcli/sessions/latest_session.json."""
        try:
            from k_cli.core.storage_manager import LocalStorageManager
            checkpoint = LocalStorageManager.load_latest_session()
            if not checkpoint:
                return None
            session = cls(
                workspace_dir=checkpoint.workspace_dir or workspace_dir,
                model_name=checkpoint.active_model,
                mock_mode=mock_mode,
            )
            session._session_id = checkpoint.session_id
            session.context_files = list(checkpoint.context_files)
            session.history = list(checkpoint.history)
            if checkpoint.active_persona:
                session.set_persona(checkpoint.active_persona)
            return session
        except Exception:
            return None

    def execute_turn(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous convenience wrapper to execute a turn and return the result dictionary.
        """
        gen = self.process_turn(prompt, stream_callback=stream_callback)
        # Drain generator to completion
        for _ in gen:
            pass
        return self.last_result or {}
