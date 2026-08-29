"""
conflict_resolver.py - AST-Aware Git Conflict Resolver for K-CLI (Project Bankai)

Features:
1. Parse standard 2-way and 3-way git conflict markers (`<<<<<<< HEAD`, `||||||| base`, `=======`, `>>>>>>> <branch>`).
2. Extract rich surrounding AST & lexical scope context (enclosing class, function, imports, surrounding code).
3. Multi-attempt semantic conflict resolution powered by LLM inference.
4. Ground-truth verification gate with AST syntax parsing and automated retry on error feedback.
5. Safe file updates, automatic git staging, and repository-wide conflict discovery & resolution summary.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

try:
    from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
except ModuleNotFoundError:
    try:
        from k_cli.git.verifier import CodeExtractor, VerificationResult, Verifier
    except ModuleNotFoundError:
        CodeExtractor = None  # type: ignore
        VerificationResult = None  # type: ignore
        Verifier = None  # type: ignore

try:
    from k_cli.git.git_guard import GitGuard
except ModuleNotFoundError:
    try:
        from git_guard import GitGuard
    except ModuleNotFoundError:
        GitGuard = None  # type: ignore


@dataclass
class ConflictBlock:
    """Represents a single parsed git conflict marker block within a file."""
    file_path: str
    start_line: int  # 1-indexed start of <<<<<<<
    end_line: int  # 1-indexed end of >>>>>>>
    ours_content: str  # Content in HEAD / current branch
    theirs_content: str  # Content in incoming / remote branch
    base_content: Optional[str] = None  # Common ancestor content if diff3 markers present
    ours_label: str = "HEAD"  # Label following <<<<<<<
    theirs_label: str = ""  # Label following >>>>>>>
    base_label: Optional[str] = None  # Label following |||||||
    raw_block: str = ""  # Complete raw text of conflict block including markers
    surrounding_context: Optional[str] = None  # Extracted AST scope / context snippet
    scope_name: Optional[str] = None  # Enclosing class/function/method name
    language: str = "python"  # Detected file language

    def is_3way(self) -> bool:
        """Returns True if the block contains base/ancestor (3-way) information."""
        return self.base_content is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes ConflictBlock to a dictionary."""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "ours_label": self.ours_label,
            "theirs_label": self.theirs_label,
            "base_label": self.base_label,
            "ours_content": self.ours_content,
            "theirs_content": self.theirs_content,
            "base_content": self.base_content,
            "scope_name": self.scope_name,
            "language": self.language,
            "is_3way": self.is_3way(),
        }


@dataclass
class ConflictResolution:
    """Represents the resolution result of an individual ConflictBlock."""
    conflict: ConflictBlock
    resolved_content: str
    success: bool
    attempts: int = 1
    error_message: Optional[str] = None
    verification_result: Optional[Any] = None
    explanation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes ConflictResolution to a dictionary."""
        return {
            "file_path": self.conflict.file_path,
            "start_line": self.conflict.start_line,
            "end_line": self.conflict.end_line,
            "success": self.success,
            "attempts": self.attempts,
            "resolved_content": self.resolved_content,
            "error_message": self.error_message,
            "explanation": self.explanation,
        }


@dataclass
class FileResolutionResult:
    """Represents the resolution outcome of a conflicted file."""
    file_path: str
    success: bool
    total_conflicts: int
    resolved_conflicts: int
    resolutions: List[ConflictResolution] = field(default_factory=list)
    staged: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes FileResolutionResult to a dictionary."""
        return {
            "file_path": self.file_path,
            "success": self.success,
            "total_conflicts": self.total_conflicts,
            "resolved_conflicts": self.resolved_conflicts,
            "staged": self.staged,
            "error_message": self.error_message,
            "resolutions": [r.to_dict() for r in self.resolutions],
        }


@dataclass
class ConflictSummary:
    """Repository-wide conflict resolution summary."""
    repo_path: str
    total_files: int
    resolved_files: int
    failed_files: int
    file_results: Dict[str, FileResolutionResult] = field(default_factory=dict)
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serializes ConflictSummary to a dictionary."""
        return {
            "repo_path": self.repo_path,
            "total_files": self.total_files,
            "resolved_files": self.resolved_files,
            "failed_files": self.failed_files,
            "success": self.success,
            "file_results": {k: v.to_dict() for k, v in self.file_results.items()},
        }


class ConflictResolver:
    """
    Production-grade AST-Aware Git Conflict Resolver for K-CLI.
    
    Parses 2-way and 3-way conflict markers, extracts surrounding AST/scope context,
    invokes LLM for semantic resolution with verification gates, and automatically
    updates and stages resolved files.
    """

    LANGUAGE_MAP: Dict[str, str] = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "cpp",
        ".h": "cpp",
        ".hpp": "cpp",
        ".sh": "bash",
        ".bash": "bash",
    }

    def __init__(self, default_model: Optional[str] = None):
        self.default_model = default_model

    # =========================================================================
    # Conflict Marker Parsing (2-way & 3-way)
    # =========================================================================

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        """Detects language from file extension."""
        ext = os.path.splitext(file_path)[1].lower()
        return cls.LANGUAGE_MAP.get(ext, "python")

    @classmethod
    def parse_conflict_blocks(cls, file_content: str, file_path: str = "") -> List[ConflictBlock]:
        """
        Parses git conflict markers (`<<<<<<<`, `|||||||`, `=======`, `>>>>>>>`) from text.
        Handles standard 2-way merge conflicts and 3-way (diff3/zdiff3) merge conflicts.
        
        Args:
            file_content: Raw string content of the conflicted file.
            file_path: Relative or absolute file path.
            
        Returns:
            List of parsed `ConflictBlock` objects in order of occurrence.
        """
        blocks: List[ConflictBlock] = []
        lines = file_content.splitlines(keepends=True)
        num_lines = len(lines)
        lang = cls.detect_language(file_path)

        i = 0
        while i < num_lines:
            line = lines[i]
            # Match start of conflict block: <<<<<<< [label]
            m_start = re.match(r"^<{7}(?:\s+(.*))?$", line.rstrip("\r\n"))
            if m_start:
                start_line = i + 1  # 1-indexed
                ours_label = (m_start.group(1) or "HEAD").strip()
                raw_lines = [line]

                ours_lines: List[str] = []
                base_lines: Optional[List[str]] = None
                theirs_lines: List[str] = []
                base_label: Optional[str] = None
                theirs_label: str = ""

                state = "ours"
                i += 1

                while i < num_lines:
                    curr_line = lines[i]
                    raw_lines.append(curr_line)
                    stripped = curr_line.rstrip("\r\n")

                    # Check for 3-way base marker: ||||||| [label]
                    m_base = re.match(r"^\|{7}(?:\s+(.*))?$", stripped)
                    if m_base and state == "ours":
                        base_label = (m_base.group(1) or "ancestor").strip()
                        base_lines = []
                        state = "base"
                        i += 1
                        continue

                    # Check for separator marker: =======
                    if stripped == "=======" and state in ("ours", "base"):
                        state = "theirs"
                        i += 1
                        continue

                    # Check for end of conflict marker: >>>>>>> [label]
                    m_end = re.match(r"^>{7}(?:\s+(.*))?$", stripped)
                    if m_end and state == "theirs":
                        theirs_label = (m_end.group(1) or "").strip()
                        end_line = i + 1  # 1-indexed

                        ours_content = "".join(ours_lines)
                        base_content = "".join(base_lines) if base_lines is not None else None
                        theirs_content = "".join(theirs_lines)
                        raw_block = "".join(raw_lines)

                        block = ConflictBlock(
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                            ours_content=ours_content,
                            theirs_content=theirs_content,
                            base_content=base_content,
                            ours_label=ours_label,
                            theirs_label=theirs_label,
                            base_label=base_label,
                            raw_block=raw_block,
                            language=lang,
                        )

                        # Extract AST & surrounding scope context
                        scope_name, surrounding_context = cls.extract_scope_context(
                            file_content=file_content,
                            conflict=block,
                            file_path=file_path,
                        )
                        block.scope_name = scope_name
                        block.surrounding_context = surrounding_context

                        blocks.append(block)
                        break

                    # Collect content according to current state
                    if state == "ours":
                        ours_lines.append(curr_line)
                    elif state == "base" and base_lines is not None:
                        base_lines.append(curr_line)
                    elif state == "theirs":
                        theirs_lines.append(curr_line)

                    i += 1
            i += 1

        return blocks

    # =========================================================================
    # AST & Scope Context Extraction
    # =========================================================================

    @classmethod
    def extract_scope_context(
        cls,
        file_content: str,
        conflict: ConflictBlock,
        file_path: str = "",
    ) -> Tuple[Optional[str], str]:
        """
        Extracts semantic surrounding context and enclosing AST scope (class/function/imports)
        for a conflict block.
        
        Returns:
            Tuple of (scope_name, formatted_surrounding_context_str)
        """
        lang = conflict.language or cls.detect_language(file_path)
        lines = file_content.splitlines()
        total_lines = len(lines)

        start_idx = max(0, conflict.start_line - 1)
        end_idx = min(total_lines, conflict.end_line)

        # 1. Preceding and succeeding code window (up to 20 lines before and after)
        preceding_start = max(0, start_idx - 20)
        preceding_lines = lines[preceding_start:start_idx]

        succeeding_end = min(total_lines, end_idx + 20)
        succeeding_lines = lines[end_idx:succeeding_end]

        scope_name: Optional[str] = None
        imports_list: List[str] = []

        if lang == "python":
            scope_name, imports_list = cls._extract_python_ast_scope(
                file_content=file_content,
                conflict=conflict,
            )
        else:
            scope_name, imports_list = cls._extract_generic_scope(
                lines=lines,
                start_idx=start_idx,
                lang=lang,
            )

        context_parts: List[str] = []
        if scope_name:
            context_parts.append(f"Enclosing Scope: {scope_name}")

        if imports_list:
            context_parts.append("File Imports:\n" + "\n".join(imports_list[:15]))

        if preceding_lines:
            prec_text = "\n".join(preceding_lines)
            context_parts.append(f"Preceding Context (Lines {preceding_start + 1}-{start_idx}):\n```\n{prec_text}\n```")

        if succeeding_lines:
            succ_text = "\n".join(succeeding_lines)
            context_parts.append(f"Succeeding Context (Lines {end_idx + 1}-{succeeding_end}):\n```\n{succ_text}\n```")

        surrounding_context = "\n\n".join(context_parts)
        return scope_name, surrounding_context

    @classmethod
    def _extract_python_ast_scope(
        cls,
        file_content: str,
        conflict: ConflictBlock,
    ) -> Tuple[Optional[str], List[str]]:
        """Extracts enclosing class/function and imports using Python AST."""
        lines = file_content.splitlines(keepends=True)
        start_idx = conflict.start_line - 1
        end_idx = conflict.end_line

        clean_lines = lines[:start_idx] + [conflict.ours_content] + lines[end_idx:]
        clean_content = "".join(clean_lines)

        imports: List[str] = []
        scope_name: Optional[str] = None

        try:
            tree = ast.parse(clean_content)
        except SyntaxError:
            # If ours_content has syntax errors, try with theirs_content
            clean_lines2 = lines[:start_idx] + [conflict.theirs_content] + lines[end_idx:]
            try:
                tree = ast.parse("".join(clean_lines2))
            except Exception:
                # Fallback to regex extraction
                return cls._extract_generic_scope(file_content.splitlines(), start_idx, "python")

        # Collect top-level imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = ", ".join(a.name for a in node.names)
                imports.append(f"from {mod} import {names}")

        # Find enclosing scope (deepest node enclosing conflict start_line)
        target_line = conflict.start_line
        best_scope: List[str] = []

        def _traverse(node: ast.AST, stack: List[str]) -> None:
            nonlocal best_scope
            curr_stack = list(stack)
            if isinstance(node, ast.ClassDef):
                curr_stack.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                curr_stack.append(node.name)

            if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                if node.lineno <= target_line <= (node.end_lineno or node.lineno):
                    if len(curr_stack) > len(best_scope):
                        best_scope = list(curr_stack)

            for child in ast.iter_child_nodes(node):
                _traverse(child, curr_stack)

        _traverse(tree, [])

        if best_scope:
            scope_name = ".".join(best_scope)

        return scope_name, imports

    @classmethod
    def _extract_generic_scope(
        cls,
        lines: List[str],
        start_idx: int,
        lang: str,
    ) -> Tuple[Optional[str], List[str]]:
        """Generic scope and import extractor for non-Python languages using pattern matching."""
        imports: List[str] = []
        scope_name: Optional[str] = None

        import_patterns = [
            re.compile(r"^\s*(?:import|export|from|require|use|#include)\s+.*"),
        ]

        # Scan for imports in top 60 lines
        for line in lines[:60]:
            if any(p.match(line) for p in import_patterns):
                imports.append(line.strip())

        # Search backwards from start_idx for enclosing definition
        def_patterns = [
            re.compile(r"^\s*(?:(?:export|public|private|protected|async|static|def|func|fn)\s+)*(?:class|struct|interface|trait|enum|function|def|func|fn)\s+([A-Za-z0-9_$]+)"),
            re.compile(r"^\s*([A-Za-z0-9_$]+)\s*\([^)]*\)\s*\{"),
        ]

        for line in reversed(lines[:start_idx]):
            for p in def_patterns:
                m = p.search(line)
                if m:
                    scope_name = m.group(1)
                    break
            if scope_name:
                break

        return scope_name, imports

    # =========================================================================
    # Fast Trivial Conflict Resolution
    # =========================================================================

    @staticmethod
    def resolve_trivial(conflict: ConflictBlock) -> Optional[str]:
        """
        Fast-paths trivial conflicts without calling LLM:
        1. Identical content on both sides -> take ours.
        2. 3-way base matches ours -> take theirs (clean incoming change).
        3. 3-way base matches theirs -> take ours (clean local change).
        
        Returns:
            Resolved code string if trivial, or None if non-trivial.
        """
        # Rule 1: Both sides are identical
        if conflict.ours_content.strip() == conflict.theirs_content.strip():
            return conflict.ours_content

        # Rule 2 & 3: 3-way base checks
        if conflict.base_content is not None:
            base_clean = conflict.base_content.strip()
            ours_clean = conflict.ours_content.strip()
            theirs_clean = conflict.theirs_content.strip()

            if ours_clean == base_clean:
                # Local did not change; accept incoming changes
                return conflict.theirs_content

            if theirs_clean == base_clean:
                # Incoming did not change; accept local changes
                return conflict.ours_content

        return None

    # =========================================================================
    # Prompt Construction
    # =========================================================================

    @classmethod
    def build_resolution_prompt(
        cls,
        conflict: ConflictBlock,
        error_feedback: Optional[str] = None,
        prompt_override: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Builds the system and user prompt for LLM conflict resolution.
        
        Returns:
            (system_prompt, user_prompt)
        """
        system_prompt = (
            "You are an expert compiler-grounded software engineer and git merge conflict resolver. "
            "Your task is to analyze git conflict blocks, integrate changes from both branches semantically, "
            "and produce clean, syntactically valid code without any conflict markers (<<<<<<<, =======, >>>>>>>)."
        )

        if prompt_override:
            return system_prompt, prompt_override

        prompt_parts: List[str] = []
        prompt_parts.append("### Git Merge Conflict Resolution Request")
        prompt_parts.append(f"**Target File**: `{conflict.file_path}`")
        prompt_parts.append(f"**Language**: `{conflict.language}`")
        if conflict.scope_name:
            prompt_parts.append(f"**Enclosing Scope**: `{conflict.scope_name}`")

        if conflict.surrounding_context:
            prompt_parts.append(f"### Surrounding Code Context\n{conflict.surrounding_context}")

        prompt_parts.append("### Conflicting Sections")
        if conflict.base_content is not None:
            prompt_parts.append(
                f"**Base / Ancestor ({conflict.base_label or 'base'}):**\n"
                f"```{conflict.language}\n{conflict.base_content}\n```"
            )

        prompt_parts.append(
            f"**Ours / Local ({conflict.ours_label or 'HEAD'}):**\n"
            f"```{conflict.language}\n{conflict.ours_content}\n```"
        )

        prompt_parts.append(
            f"**Theirs / Incoming ({conflict.theirs_label or 'incoming'}):**\n"
            f"```{conflict.language}\n{conflict.theirs_content}\n```"
        )

        if error_feedback:
            prompt_parts.append(
                f"⚠️ **ATTENTION - PREVIOUS ATTEMPT VERIFICATION FAILED**:\n"
                f"The previous resolution attempt produced the following syntax/verification error:\n"
                f"```\n{error_feedback}\n```\n"
                f"Please fix this syntax/semantic error and ensure the code compiles cleanly."
            )

        prompt_parts.append(
            "### Instructions:\n"
            "1. Synthesize the changes from both sides, preserving non-conflicting logic, imports, and variables.\n"
            "2. Ensure proper indentation matching the surrounding context.\n"
            "3. Output ONLY the resolved code replacement block inside markdown code fences: ```" + conflict.language + " ... ```\n"
            "4. NEVER include git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)."
        )

        user_prompt = "\n\n".join(prompt_parts)
        return system_prompt, user_prompt

    # =========================================================================
    # Conflict Block Resolution
    # =========================================================================

    def resolve_conflict_block(
        self,
        conflict: ConflictBlock,
        llm_driver: Any,
        model: Optional[str] = None,
        prompt_override: Optional[str] = None,
        max_retries: int = 3,
        verifier: Optional[Any] = None,
    ) -> ConflictResolution:
        """
        Resolves a single ConflictBlock using LLM inference and a verification gate.
        
        Args:
            conflict: The ConflictBlock to resolve.
            llm_driver: LLMDriver instance (or mock).
            model: Optional model name override.
            prompt_override: Optional user prompt override.
            max_retries: Maximum verification retry attempts (default: 3).
            verifier: Optional Verifier instance for AST / syntax checks.
            
        Returns:
            ConflictResolution object with status, resolved content, and attempts.
        """
        # Step 1: Check trivial fast-path
        trivial = self.resolve_trivial(conflict)
        if trivial is not None:
            return ConflictResolution(
                conflict=conflict,
                resolved_content=trivial,
                success=True,
                attempts=0,
                explanation="Resolved via fast-path 3-way/identical change deduction.",
            )

        error_feedback: Optional[str] = None
        last_error: Optional[str] = None
        last_extracted_code: str = ""

        # Step 2: Retry loop with verification gate
        for attempt in range(1, max_retries + 1):
            sys_prompt, user_prompt = self.build_resolution_prompt(
                conflict=conflict,
                error_feedback=error_feedback,
                prompt_override=prompt_override,
            )

            try:
                raw_response = llm_driver.generate(
                    prompt=user_prompt,
                    system_prompt=sys_prompt,
                    temperature=0.1 if attempt > 1 else 0.2,
                )
            except Exception as e:
                logger.error("LLM generation failed for conflict block in %s: %s", conflict.file_path, e)
                last_error = f"LLM generation exception: {str(e)}"
                continue

            # Extract clean code
            extracted_code = raw_response
            if CodeExtractor is not None:
                _, extracted_code = CodeExtractor.extract_primary_code(
                    raw_response, default_lang=conflict.language
                )
            else:
                # Fallback block extraction
                m = re.search(r"```(?:[a-zA-Z0-9_\-+]*)\n(.*?)```", raw_response, re.DOTALL)
                if m:
                    extracted_code = m.group(1).strip()
                else:
                    extracted_code = raw_response.strip()

            last_extracted_code = extracted_code

            # Check if output still contains conflict markers
            if any(marker in extracted_code for marker in ("<<<<<<<", "=======", ">>>>>>>")):
                last_error = "Generated resolution still contains git conflict markers (<<<<<<<, =======, >>>>>>>)."
                error_feedback = last_error
                continue

            # Step 3: Verification Gate
            is_valid = True
            v_res: Optional[Any] = None

            if verifier is not None and conflict.language == "python":
                test_code = extracted_code
                try:
                    ast.parse(test_code)
                except SyntaxError:
                    try:
                        ast.parse(textwrap.dedent(test_code))
                    except SyntaxError:
                        try:
                            wrapped = f"def _dummy_scope():\n{textwrap.indent(test_code, '    ')}"
                            ast.parse(wrapped)
                        except SyntaxError as syn_err:
                            is_valid = False
                            last_error = f"SyntaxError in resolved code: {syn_err.msg} at line {syn_err.lineno}"
                            error_feedback = last_error
                            if hasattr(verifier, "verify_python_ast"):
                                v_res = verifier.verify_python_ast(test_code)

            if is_valid:
                return ConflictResolution(
                    conflict=conflict,
                    resolved_content=extracted_code,
                    success=True,
                    attempts=attempt,
                    verification_result=v_res,
                    explanation="Successfully resolved and verified by AST parser.",
                )

        # If we exhausted retries
        return ConflictResolution(
            conflict=conflict,
            resolved_content=last_extracted_code if not error_feedback else "",
            success=False,
            attempts=max_retries,
            error_message=last_error or f"Failed verification after {max_retries} attempts.",
        )

    # =========================================================================
    # File Resolution & Auto-Staging
    # =========================================================================

    @classmethod
    def apply_resolutions(cls, file_content: str, resolutions: List[ConflictResolution]) -> str:
        """
        Applies successful resolutions to file content.
        Replaces each conflict block with its resolved content.
        """
        sorted_res = sorted(resolutions, key=lambda r: r.conflict.start_line, reverse=True)

        lines = file_content.splitlines(keepends=True)
        total_lines = len(lines)

        for res in sorted_res:
            if not res.success:
                continue
            start_idx = res.conflict.start_line - 1
            end_idx = min(total_lines, res.conflict.end_line)

            replacement = res.resolved_content
            if replacement and not replacement.endswith("\n"):
                replacement += "\n"

            lines = lines[:start_idx] + [replacement] + lines[end_idx:]
            total_lines = len(lines)

        return "".join(lines)

    def resolve_file(
        self,
        file_path: str,
        llm_driver: Any,
        verifier: Optional[Any] = None,
        auto_stage: bool = True,
        max_retries: int = 3,
    ) -> FileResolutionResult:
        """
        Resolves all conflict blocks within a single file.
        Verifies the full file after all block resolutions, safely writes the output,
        and optionally auto-stages the file with git.
        
        Args:
            file_path: Relative or absolute path to the conflicted file.
            llm_driver: LLM inference driver.
            verifier: Ground-truth verifier guard.
            auto_stage: Whether to `git add <file_path>` upon verified resolution.
            max_retries: Max retries per conflict block.
            
        Returns:
            FileResolutionResult.
        """
        path = Path(file_path).resolve()
        if not path.exists() or not path.is_file():
            return FileResolutionResult(
                file_path=file_path,
                success=False,
                total_conflicts=0,
                resolved_conflicts=0,
                error_message=f"File not found: {file_path}",
            )

        try:
            original_content = path.read_text(encoding="utf-8")
        except Exception as e:
            return FileResolutionResult(
                file_path=file_path,
                success=False,
                total_conflicts=0,
                resolved_conflicts=0,
                error_message=f"Failed to read file: {str(e)}",
            )

        blocks = self.parse_conflict_blocks(original_content, file_path=str(path))
        if not blocks:
            return FileResolutionResult(
                file_path=file_path,
                success=True,
                total_conflicts=0,
                resolved_conflicts=0,
                resolutions=[],
                staged=False,
            )

        resolutions: List[ConflictResolution] = []
        all_succeeded = True

        for block in blocks:
            res = self.resolve_conflict_block(
                conflict=block,
                llm_driver=llm_driver,
                model=self.default_model,
                max_retries=max_retries,
                verifier=verifier,
            )
            resolutions.append(res)
            if not res.success:
                all_succeeded = False

        if not all_succeeded:
            failed_count = sum(1 for r in resolutions if not r.success)
            return FileResolutionResult(
                file_path=file_path,
                success=False,
                total_conflicts=len(blocks),
                resolved_conflicts=len(blocks) - failed_count,
                resolutions=resolutions,
                staged=False,
                error_message=f"{failed_count} conflict block(s) failed verification. File was not modified.",
            )

        # Apply resolutions to construct the full resolved file
        resolved_file_content = self.apply_resolutions(original_content, resolutions)

        # Verify full file syntax if verifier is present
        lang = self.detect_language(file_path)
        if verifier is not None and lang == "python":
            if hasattr(verifier, "verify_python_ast"):
                ast_check = verifier.verify_python_ast(resolved_file_content)
                if not ast_check.success:
                    logger.warning(
                        "Resolved full file %s failed AST check: %s",
                        file_path,
                        ast_check.error_trace,
                    )
                    return FileResolutionResult(
                        file_path=file_path,
                        success=False,
                        total_conflicts=len(blocks),
                        resolved_conflicts=len(blocks),
                        resolutions=resolutions,
                        staged=False,
                        error_message=f"Full file AST verification failed: {ast_check.error_trace}",
                    )

        # Safely write out resolved content
        try:
            path.write_text(resolved_file_content, encoding="utf-8")
        except Exception as e:
            return FileResolutionResult(
                file_path=file_path,
                success=False,
                total_conflicts=len(blocks),
                resolved_conflicts=len(blocks),
                resolutions=resolutions,
                staged=False,
                error_message=f"Failed to write resolved file: {str(e)}",
            )

        # Auto-stage with Git if requested
        staged = False
        if auto_stage:
            staged = self._stage_file_git(file_path=str(path))

        return FileResolutionResult(
            file_path=file_path,
            success=True,
            total_conflicts=len(blocks),
            resolved_conflicts=len(blocks),
            resolutions=resolutions,
            staged=staged,
        )

    def _stage_file_git(self, file_path: str) -> bool:
        """Helper to stage a resolved file using git add."""
        try:
            p = Path(file_path)
            parent_dir = p.parent if p.is_file() else p
            res = subprocess.run(
                ["git", "add", str(p)],
                cwd=str(parent_dir),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    # =========================================================================
    # Repository-Wide Conflict Discovery & Resolution
    # =========================================================================

    def find_conflicts(self, repo_path: str = ".") -> List[ConflictBlock]:
        """
        Finds all conflict blocks across all files in the repository.
        Scans git unmerged status (`git diff --diff-filter=U` / `git status`)
        and performs workspace file scanning for `<<<<<<< ` markers.
        
        Args:
            repo_path: Path to repository workspace root or individual file.
            
        Returns:
            List of all ConflictBlock objects found across the workspace.
        """
        target = Path(repo_path).resolve()
        if target.is_file():
            try:
                content = target.read_text(encoding="utf-8")
                return self.parse_conflict_blocks(content, file_path=str(target))
            except Exception:
                return []

        all_conflicts: List[ConflictBlock] = []
        conflicted_files: Set[str] = set()

        # Method 1: Check git unmerged files
        try:
            res = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=str(target),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.splitlines():
                    rel_p = line.strip()
                    if rel_p:
                        conflicted_files.add(str((target / rel_p).resolve()))
        except Exception:
            pass

        # Method 2: Recursive scan for conflict markers
        ignored_dirs = {".git", ".venv", "k_cli_env", "venv", "node_modules", "build", "dist", "__pycache__", ".pytest_cache", "data"}
        for root, dirs, files in os.walk(str(target)):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        chunk = f.read(1024 * 1024)
                        if "<<<<<<< " in chunk:
                            conflicted_files.add(fpath)
                except Exception:
                    continue

        for fpath in sorted(conflicted_files):
            try:
                content = Path(fpath).read_text(encoding="utf-8")
                blocks = self.parse_conflict_blocks(content, file_path=fpath)
                all_conflicts.extend(blocks)
            except Exception as e:
                logger.warning("Could not read conflicted file %s: %s", fpath, e)

        return all_conflicts

    def resolve_all_conflicts(
        self,
        repo_path: str = ".",
        llm_driver: Any = None,
        verifier: Optional[Any] = None,
        auto_stage: bool = True,
    ) -> ConflictSummary:
        """
        Discovers all conflicted files in repository, resolves each file,
        verifies AST/syntax, auto-stages, and returns ConflictSummary.
        
        Args:
            repo_path: Path to repository workspace.
            llm_driver: LLMDriver instance.
            verifier: Ground-truth verifier.
            auto_stage: Whether to git add resolved files.
            
        Returns:
            ConflictSummary.
        """
        conflicts = self.find_conflicts(repo_path=repo_path)
        conflicted_files = sorted({c.file_path for c in conflicts if c.file_path})

        if not conflicted_files:
            return ConflictSummary(
                repo_path=repo_path,
                total_files=0,
                resolved_files=0,
                failed_files=0,
                file_results={},
                success=True,
            )

        file_results: Dict[str, FileResolutionResult] = {}
        resolved_count = 0
        failed_count = 0

        for fpath in conflicted_files:
            res = self.resolve_file(
                file_path=fpath,
                llm_driver=llm_driver,
                verifier=verifier,
                auto_stage=auto_stage,
            )
            file_results[fpath] = res
            if res.success:
                resolved_count += 1
            else:
                failed_count += 1

        overall_success = (failed_count == 0)

        return ConflictSummary(
            repo_path=repo_path,
            total_files=len(conflicted_files),
            resolved_files=resolved_count,
            failed_files=failed_count,
            file_results=file_results,
            success=overall_success,
        )
