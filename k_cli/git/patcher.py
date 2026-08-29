"""
patcher.py - SEARCH/REPLACE Surgical Patch Engine for K-CLI

Provides unified search/replace block parsing, exact and indentation-tolerant
fuzzy matching, AST-based multi-line structural matching, transactional multi-file
batching with all-or-nothing rollback, and clean CLI diff preview rendering.
"""

from __future__ import annotations

import ast
import difflib
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


@dataclass
class FilePatch:
    """Represents a single search/replace block associated with an optional file path."""
    file_path: Optional[str]
    search_block: str
    replace_block: str


@dataclass
class PatchResult:
    """Result of a single patch application."""
    success: bool
    patched_code: str
    error_message: str = ""
    diff: str = ""


@dataclass
class BatchPatchResult:
    """Result of a transactional multi-file batch patch application."""
    success: bool
    modified_files: List[str] = field(default_factory=list)
    error_message: str = ""
    diff_summary: str = ""


class Patcher:
    """
    Surgical patch engine that parses SEARCH/REPLACE blocks, applies exact or
    fuzzy/AST-matched edits to strings or files, validates Python AST syntax before
    disk writes, manages transactional multi-file batches with rollback, and renders
    clean CLI diff previews.
    """

    # Regex to extract standard SEARCH / REPLACE blocks:
    # <<<<<<< SEARCH [optional file / info]
    # ... search block ...
    # =======
    # ... replace block ...
    # >>>>>>> [REPLACE] [optional info]
    SEARCH_REPLACE_PATTERN = re.compile(
        r"^[ \t]*<{7}(?![<])(?:[ \t]*SEARCH(?::?[ \t]+[^\r\n]*)?|[ \t]*)[ \t]*\r?\n"
        r"([\s\S]*?)\r?\n"
        r"^[ \t]*={7}(?![=])[ \t]*\r?\n"
        r"([\s\S]*?)\r?\n"
        r"^[ \t]*>{7}(?![>])(?:[ \t]*REPLACE(?::?[ \t]+[^\r\n]*)?|[ \t]*[^\r\n]*)",
        re.MULTILINE,
    )

    # ANSI Color constants for diff terminal rendering
    ANSI_RESET = "\033[0m"
    ANSI_BOLD = "\033[1m"
    ANSI_CYAN = "\033[36m"
    ANSI_GREEN = "\033[32m"
    ANSI_RED = "\033[31m"
    ANSI_DIM = "\033[2m"
    ANSI_MAGENTA = "\033[35m"

    # =========================================================================
    # 1. Parsing SEARCH/REPLACE Blocks
    # =========================================================================

    @classmethod
    def _clean_filepath_token(cls, raw: str) -> Optional[str]:
        """Cleans and validates a potential file path token extracted from patch text."""
        if not raw:
            return None
        cleaned = raw.strip()
        # Remove common markdown, header prefixes, and quote enclosures
        cleaned = re.sub(r"^(?:#+|\*+|`+|---|--- a/|\+\+\+ b/|(?:File|FILE|file):\s*)", "", cleaned).strip()
        cleaned = cleaned.strip("`'\"*#:-> \t")
        if cleaned.startswith("a/") or cleaned.startswith("b/"):
            cleaned = cleaned[2:]
        if (
            cleaned
            and ("." in cleaned or "/" in cleaned or "\\" in cleaned)
            and " " not in cleaned
            and len(cleaned) < 250
        ):
            return cleaned
        return None

    @classmethod
    def parse_search_replace_blocks(cls, text: str) -> List[Tuple[str, str]]:
        """
        Parses `<<<<<<< SEARCH ... ======= ... >>>>>>> [REPLACE]` blocks from text.

        Handles multiple blocks, trailing whitespace on marker lines, varying indentation,
        and standard `>>>>>>> REPLACE` variants. Malformed blocks without matching dividers
        or end markers are ignored safely.

        Args:
            text: Raw patch text or LLM response containing one or more blocks.

        Returns:
            List of (search_block, replace_block) tuples.
        """
        if not text:
            return []

        blocks: List[Tuple[str, str]] = []
        for match in cls.SEARCH_REPLACE_PATTERN.finditer(text):
            search_part = match.group(1)
            replace_part = match.group(2)
            blocks.append((search_part, replace_part))

        return blocks

    @classmethod
    def parse_multi_file_patches(cls, text: str) -> List[Tuple[Optional[str], str, str]]:
        """
        Parses SEARCH/REPLACE blocks along with their associated target file paths.

        Supports file paths specified on marker lines (e.g. `<<<<<<< SEARCH: file.py`),
        markdown headers immediately preceding blocks (e.g. `### `file.py``),
        or unified diff style headers (e.g. `--- a/file.py`).

        Args:
            text: Raw patch text containing one or more file blocks.

        Returns:
            List of (file_path_or_none, search_block, replace_block) tuples.
        """
        if not text:
            return []

        results: List[Tuple[Optional[str], str, str]] = []

        for match in cls.SEARCH_REPLACE_PATTERN.finditer(text):
            search_part = match.group(1)
            replace_part = match.group(2)

            # 1. Check opening marker line for inline filename
            matched_str = match.group(0)
            first_line = matched_str.split("\n", 1)[0]
            file_path: Optional[str] = None

            m_inline = re.search(r"<{7}\s*SEARCH(?::|\s)\s*([^\r\n]+)", first_line)
            if m_inline:
                candidate = cls._clean_filepath_token(m_inline.group(1))
                if candidate and not candidate.startswith("<") and not candidate.startswith("="):
                    file_path = candidate

            # 2. Check preceding lines if not found on marker line
            if not file_path:
                preceding_text = text[: match.start()]
                prec_lines = [line.strip() for line in preceding_text.split("\n") if line.strip()]
                if prec_lines:
                    last_line = prec_lines[-1]
                    candidate = cls._clean_filepath_token(last_line)
                    if candidate:
                        file_path = candidate

            results.append((file_path, search_part, replace_part))

        return results

    # =========================================================================
    # 2. Patch Application with Indentation & AST Fuzzy Tolerance
    # =========================================================================

    @classmethod
    def apply_patch(
        cls,
        original_code: str,
        search_block: str,
        replace_block: str,
        fuzzy: bool = True,
    ) -> Tuple[bool, str, str]:
        """
        Applies a single search/replace patch to code.

        Supports exact matching as well as indentation-tolerant, newline-tolerant,
        whitespace-normalized, and AST structural fuzzy matching.

        Args:
            original_code: The original source code string.
            search_block: The block of code to search for and replace.
            replace_block: The replacement block of code.
            fuzzy: Whether to allow fuzzy matching if exact matching fails.

        Returns:
            Tuple of (success: bool, patched_code: str, error_message: str).
        """
        if not search_block:
            return False, original_code, "Search block cannot be empty"

        # 1. Exact match
        if search_block in original_code:
            patched = original_code.replace(search_block, replace_block, 1)
            return True, patched, ""

        if not fuzzy:
            return False, original_code, "Search block not found in original code (exact mode)"

        # 2. Fuzzy match strategies
        # Normalize CRLF / LF line endings for search & original
        orig_is_crlf = "\r\n" in original_code
        norm_orig = original_code.replace("\r\n", "\n")
        norm_search = search_block.replace("\r\n", "\n")
        norm_replace = replace_block.replace("\r\n", "\n")

        # Strategy A: Line-ending normalized exact match
        if norm_search in norm_orig:
            patched_norm = norm_orig.replace(norm_search, norm_replace, 1)
            if orig_is_crlf:
                patched_norm = patched_norm.replace("\n", "\r\n")
            return True, patched_norm, ""

        orig_lines = norm_orig.split("\n")
        search_lines = norm_search.split("\n")

        # If last line of search block is empty due to trailing newline, drop it if search has multiple lines
        if len(search_lines) > 1 and search_lines[-1] == "":
            search_lines = search_lines[:-1]

        # Strategy B: Trailing whitespace tolerance on each line
        res = cls._match_trailing_ws(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy C: Indentation shift tolerance (uniform delta)
        res = cls._match_indentation_shift(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy D: Relative indentation tolerance (non-uniform or proportional shift)
        res = cls._match_relative_indentation(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy E: Whitespace-normalized token sequence matching
        res = cls._match_whitespace_normalized(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy F: Python AST structural multi-line matching
        res = cls._match_ast_multiline(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy G: Interspersed blank lines tolerance
        res = cls._match_blank_lines_tolerance(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy H: Normalized stripped line sequence match
        res = cls._match_stripped_lines(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        # Strategy I: Fuzzy similarity window match
        res = cls._match_fuzzy_similarity(orig_lines, search_lines, norm_replace, orig_is_crlf)
        if res is not None:
            return True, res, ""

        return False, original_code, "Search block not found in original code"

    @classmethod
    def _match_trailing_ws(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches when line content matches after rstrip() on each line."""
        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        for i in range(n_orig - n_search + 1):
            match = True
            for k in range(n_search):
                if orig_lines[i + k].rstrip() != search_lines[k].rstrip():
                    match = False
                    break
            if match:
                replace_lines = replace_block.split("\n")
                new_lines = orig_lines[:i] + replace_lines + orig_lines[i + n_search :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_indentation_shift(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches when code structure matches with uniform indentation shift."""
        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        for i in range(n_orig - n_search + 1):
            delta: Optional[int] = None
            match = True
            for k in range(n_search):
                s_line = search_lines[k]
                o_line = orig_lines[i + k]

                if not s_line.strip() and not o_line.strip():
                    continue

                if s_line.strip() != o_line.strip():
                    match = False
                    break

                s_indent = len(s_line) - len(s_line.lstrip())
                o_indent = len(o_line) - len(o_line.lstrip())
                curr_delta = o_indent - s_indent

                if delta is None:
                    delta = curr_delta
                elif delta != curr_delta:
                    match = False
                    break

            if match and delta is not None:
                replace_lines = replace_block.split("\n")
                shifted_replace_lines: List[str] = []
                for r_line in replace_lines:
                    if not r_line.strip():
                        shifted_replace_lines.append(r_line)
                    elif delta > 0:
                        shifted_replace_lines.append(" " * delta + r_line)
                    elif delta < 0:
                        strip_count = min(-delta, len(r_line) - len(r_line.lstrip()))
                        shifted_replace_lines.append(r_line[strip_count:])
                    else:
                        shifted_replace_lines.append(r_line)

                new_lines = orig_lines[:i] + shifted_replace_lines + orig_lines[i + n_search :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_relative_indentation(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches when stripped lines match and adjusts replacement by relative indentation."""
        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        # Find first non-empty search line indent
        first_nonempty_search = next((l for l in search_lines if l.strip()), None)
        if not first_nonempty_search:
            return None
        search_base_indent = len(first_nonempty_search) - len(first_nonempty_search.lstrip())

        for i in range(n_orig - n_search + 1):
            match = True
            for k in range(n_search):
                s_line = search_lines[k]
                o_line = orig_lines[i + k]
                if s_line.strip() != o_line.strip():
                    match = False
                    break
            if match:
                first_orig_line = next((l for l in orig_lines[i : i + n_search] if l.strip()), orig_lines[i])
                orig_base_indent = len(first_orig_line) - len(first_orig_line.lstrip())
                delta = orig_base_indent - search_base_indent

                replace_lines = replace_block.split("\n")
                shifted_replace_lines: List[str] = []
                for r_line in replace_lines:
                    if not r_line.strip():
                        shifted_replace_lines.append("")
                    elif delta > 0:
                        shifted_replace_lines.append(" " * delta + r_line)
                    elif delta < 0:
                        strip_count = min(-delta, len(r_line) - len(r_line.lstrip()))
                        shifted_replace_lines.append(r_line[strip_count:])
                    else:
                        shifted_replace_lines.append(r_line)

                new_lines = orig_lines[:i] + shifted_replace_lines + orig_lines[i + n_search :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_whitespace_normalized(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches when internal consecutive whitespace / quotes are normalized."""
        def _norm_line(s: str) -> str:
            # Collapse multiple spaces and normalize quotes
            cleaned = re.sub(r"[ \t]+", " ", s.strip())
            cleaned = cleaned.replace('"', "'")
            return cleaned

        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        norm_search_lines = [_norm_line(l) for l in search_lines]

        for i in range(n_orig - n_search + 1):
            match = True
            for k in range(n_search):
                if _norm_line(orig_lines[i + k]) != norm_search_lines[k]:
                    match = False
                    break
            if match:
                first_orig_line = next((l for l in orig_lines[i : i + n_search] if l.strip()), orig_lines[i])
                orig_base_indent = len(first_orig_line) - len(first_orig_line.lstrip())

                first_search_line = next((l for l in search_lines if l.strip()), search_lines[0])
                search_base_indent = len(first_search_line) - len(first_search_line.lstrip())
                delta = orig_base_indent - search_base_indent

                replace_lines = replace_block.split("\n")
                shifted_replace_lines: List[str] = []
                for r_line in replace_lines:
                    if not r_line.strip():
                        shifted_replace_lines.append("")
                    elif delta > 0:
                        shifted_replace_lines.append(" " * delta + r_line)
                    elif delta < 0:
                        strip_count = min(-delta, len(r_line) - len(r_line.lstrip()))
                        shifted_replace_lines.append(r_line[strip_count:])
                    else:
                        shifted_replace_lines.append(r_line)

                new_lines = orig_lines[:i] + shifted_replace_lines + orig_lines[i + n_search :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _get_ast_body_lists(cls, node: ast.AST) -> List[List[ast.AST]]:
        """Recursively collects all statement lists (body, orelse, finalbody, etc.) from an AST."""
        lists: List[List[ast.AST]] = []
        for _, value in ast.iter_fields(node):
            if isinstance(value, list) and value and isinstance(value[0], ast.AST):
                lists.append(value)
                for item in value:
                    lists.extend(cls._get_ast_body_lists(item))
            elif isinstance(value, ast.AST):
                lists.extend(cls._get_ast_body_lists(value))
        return lists

    @classmethod
    def _ast_structures_match(cls, node1: ast.AST, node2: ast.AST) -> bool:
        """Compares two AST nodes for structural equivalence ignoring attributes and formatting."""
        if type(node1) is not type(node2):
            return False
        if isinstance(node1, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node1.name != getattr(node2, "name", None):
                return False
        elif isinstance(node1, ast.Name):
            if node1.id != getattr(node2, "id", None):
                return False
        elif isinstance(node1, ast.Attribute):
            if node1.attr != getattr(node2, "attr", None):
                return False

        dump1 = ast.dump(node1, include_attributes=False)
        dump2 = ast.dump(node2, include_attributes=False)
        return dump1 == dump2

    @classmethod
    def _match_ast_multiline(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches search block against Python AST structure and replaces target statements."""
        orig_code = "\n".join(orig_lines)
        try:
            orig_ast = ast.parse(orig_code)
        except Exception:
            return None

        search_code = "\n".join(search_lines)
        search_ast: Optional[ast.AST] = None
        try:
            search_ast = ast.parse(search_code)
        except Exception:
            try:
                search_ast = ast.parse(textwrap.dedent(search_code))
            except Exception:
                try:
                    wrapped = "def _dummy():\n" + textwrap.indent(textwrap.dedent(search_code), "    ")
                    dummy_ast = ast.parse(wrapped)
                    search_ast = dummy_ast.body[0]
                except Exception:
                    return None

        if search_ast is None:
            return None

        if isinstance(search_ast, ast.Module):
            search_targets = search_ast.body
        elif isinstance(search_ast, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(search_ast, "name", "") == "_dummy":
            search_targets = search_ast.body
        else:
            search_targets = [search_ast]

        if not search_targets:
            return None

        all_body_lists = cls._get_ast_body_lists(orig_ast)
        if orig_ast.body not in all_body_lists:
            all_body_lists.insert(0, orig_ast.body)

        n_targets = len(search_targets)
        for body_list in all_body_lists:
            if len(body_list) < n_targets:
                continue
            for i in range(len(body_list) - n_targets + 1):
                cand_slice = body_list[i : i + n_targets]
                matched = True
                for k in range(n_targets):
                    if not cls._ast_structures_match(cand_slice[k], search_targets[k]):
                        matched = False
                        break
                if matched:
                    first_node = cand_slice[0]
                    last_node = cand_slice[-1]
                    start_lineno = first_node.lineno  # 1-indexed
                    end_lineno = getattr(last_node, "end_lineno", last_node.lineno)

                    orig_target_line = orig_lines[start_lineno - 1]
                    target_base_indent = len(orig_target_line) - len(orig_target_line.lstrip())

                    search_first_nonempty = next((l for l in search_lines if l.strip()), search_lines[0])
                    search_base_indent = len(search_first_nonempty) - len(search_first_nonempty.lstrip())
                    delta = target_base_indent - search_base_indent

                    replace_lines = replace_block.split("\n")
                    shifted_replace_lines: List[str] = []
                    for r_line in replace_lines:
                        if not r_line.strip():
                            shifted_replace_lines.append("")
                        elif delta > 0:
                            shifted_replace_lines.append(" " * delta + r_line)
                        elif delta < 0:
                            strip_count = min(-delta, len(r_line) - len(r_line.lstrip()))
                            shifted_replace_lines.append(r_line[strip_count:])
                        else:
                            shifted_replace_lines.append(r_line)

                    new_lines = orig_lines[: start_lineno - 1] + shifted_replace_lines + orig_lines[end_lineno:]
                    joined = "\n".join(new_lines)
                    return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_blank_lines_tolerance(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches search lines against original lines allowing extra blank lines in between."""
        non_empty_search = [(idx, s.strip()) for idx, s in enumerate(search_lines) if s.strip()]
        if not non_empty_search:
            return None

        n_orig = len(orig_lines)
        for start_i in range(n_orig):
            if orig_lines[start_i].strip() != non_empty_search[0][1]:
                continue

            curr_orig = start_i
            matched_all = True
            for _, s_text in non_empty_search[1:]:
                curr_orig += 1
                while curr_orig < n_orig and not orig_lines[curr_orig].strip():
                    curr_orig += 1
                if curr_orig >= n_orig or orig_lines[curr_orig].strip() != s_text:
                    matched_all = False
                    break

            if matched_all:
                replace_lines = replace_block.split("\n")
                new_lines = orig_lines[:start_i] + replace_lines + orig_lines[curr_orig + 1 :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_stripped_lines(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Matches when stripped non-empty lines are identical."""
        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        for i in range(n_orig - n_search + 1):
            match = True
            for k in range(n_search):
                if orig_lines[i + k].strip() != search_lines[k].strip():
                    match = False
                    break
            if match:
                replace_lines = replace_block.split("\n")
                new_lines = orig_lines[:i] + replace_lines + orig_lines[i + n_search :]
                joined = "\n".join(new_lines)
                return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    @classmethod
    def _match_fuzzy_similarity(
        cls,
        orig_lines: List[str],
        search_lines: List[str],
        replace_block: str,
        orig_is_crlf: bool,
    ) -> Optional[str]:
        """Fuzzy line-sequence similarity matching using SequenceMatcher."""
        n_search = len(search_lines)
        n_orig = len(orig_lines)
        if n_search == 0 or n_search > n_orig:
            return None

        clean_search = "\n".join([l.strip() for l in search_lines if l.strip()])
        if not clean_search:
            return None

        best_ratio = 0.0
        best_index = -1
        best_len = n_search

        for window_len in (n_search, max(1, n_search - 1), n_search + 1):
            if window_len > n_orig:
                continue
            for i in range(n_orig - window_len + 1):
                candidate_lines = orig_lines[i : i + window_len]
                clean_cand = "\n".join([l.strip() for l in candidate_lines if l.strip()])
                ratio = difflib.SequenceMatcher(None, clean_search, clean_cand).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_index = i
                    best_len = window_len

        # Require high similarity threshold (>= 0.88) to prevent false edits
        if best_ratio >= 0.88 and best_index >= 0:
            first_orig = next((l for l in orig_lines[best_index : best_index + best_len] if l.strip()), orig_lines[best_index])
            orig_base_indent = len(first_orig) - len(first_orig.lstrip())

            first_search = next((l for l in search_lines if l.strip()), search_lines[0])
            search_base_indent = len(first_search) - len(first_search.lstrip())
            delta = orig_base_indent - search_base_indent

            replace_lines = replace_block.split("\n")
            shifted_replace_lines: List[str] = []
            for r_line in replace_lines:
                if not r_line.strip():
                    shifted_replace_lines.append("")
                elif delta > 0:
                    shifted_replace_lines.append(" " * delta + r_line)
                elif delta < 0:
                    strip_count = min(-delta, len(r_line) - len(r_line.lstrip()))
                    shifted_replace_lines.append(r_line[strip_count:])
                else:
                    shifted_replace_lines.append(r_line)

            new_lines = orig_lines[:best_index] + shifted_replace_lines + orig_lines[best_index + best_len :]
            joined = "\n".join(new_lines)
            return joined.replace("\n", "\r\n") if orig_is_crlf else joined

        return None

    # =========================================================================
    # 3. File Patching and Transactional Multi-File Batching
    # =========================================================================

    @classmethod
    def apply_file_patches(
        cls,
        file_path: str,
        patch_text: str,
        validate_ast: bool = True,
    ) -> Tuple[bool, str]:
        """
        Parses SEARCH/REPLACE blocks and applies them sequentially to a single file.

        Validates Python syntax with `ast.parse` before writing to disk if the file is `.py`.
        Maintains atomic safety: if any block fails to match or AST validation fails,
        the target file on disk remains completely untouched.

        Args:
            file_path: Target file path on disk.
            patch_text: Raw text containing one or more SEARCH/REPLACE blocks.
            validate_ast: Whether to perform pre-write AST parsing for .py files.

        Returns:
            Tuple of (success: bool, error_message: str).
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return False, f"Target file not found: {file_path}"

        try:
            original_code = path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Failed to read file {file_path}: {e}"

        blocks = cls.parse_search_replace_blocks(patch_text)
        if not blocks:
            return False, "No valid SEARCH/REPLACE blocks found in patch"

        current_code = original_code
        for idx, (search_block, replace_block) in enumerate(blocks, start=1):
            success, patched_code, err = cls.apply_patch(
                current_code,
                search_block,
                replace_block,
                fuzzy=True,
            )
            if not success:
                return False, f"Block {idx} failed to apply: {err}"
            current_code = patched_code

        # AST syntax validation for Python files
        if validate_ast and path.suffix.lower() == ".py":
            try:
                ast.parse(current_code, filename=str(file_path))
            except SyntaxError as e:
                return (
                    False,
                    f"AST SyntaxError validation failed on line {e.lineno}: {e.msg} - File unchanged",
                )
            except Exception as e:
                return False, f"AST validation error: {e} - File unchanged"

        # Atomically write updated code to file
        try:
            path.write_text(current_code, encoding="utf-8")
            return True, ""
        except Exception as e:
            return False, f"Failed to write patched file {file_path}: {e}"

    @classmethod
    def _resolve_multi_file_target(cls, base: Path, file_path: Union[str, Path]) -> Tuple[Optional[Path], str]:
        """Resolve a patch target while keeping it inside the declared workspace."""
        raw_path = Path(file_path)
        if raw_path.is_absolute():
            return None, f"Absolute patch paths are not allowed: {file_path}"
        target_path = (base.resolve() / raw_path).resolve()
        try:
            target_path.relative_to(base.resolve())
        except ValueError:
            return None, f"Patch target escapes base directory: {file_path}"
        return target_path, ""

    @classmethod
    def apply_multi_file_patches(
        cls,
        patches: Union[str, Dict[str, Union[str, List[Tuple[str, str]]]], Sequence[Union[Tuple[Optional[str], str, str], Tuple[str, str], FilePatch]], Sequence[Dict[str, Any]]],
        base_dir: Optional[Union[str, Path]] = None,
        validate_ast: bool = True,
    ) -> Tuple[bool, List[str], str]:
        """
        Applies a batch of patches across multiple files with transactional rollback.

        If any block in any file fails to match, or any Python file fails AST syntax
        validation, the entire batch transaction is aborted and zero files are modified
        on disk (all files are restored to their exact original contents).

        Args:
            patches: Either:
                - Raw multi-file patch text containing file headers and blocks.
                - Dict mapping file paths to patch strings or lists of (search, replace) tuples.
                - List of (file_path, search_block, replace_block) tuples or FilePatch objects.
            base_dir: Base directory to resolve relative file paths against (defaults to cwd).
            validate_ast: Whether to perform pre-write AST validation on .py files.

        Returns:
            Tuple of (success: bool, modified_files: List[str], error_message: str).
        """
        base = Path(base_dir) if base_dir else Path.cwd()
        file_to_blocks: Dict[Path, List[Tuple[str, str]]] = {}

        # 1. Normalize input into file_to_blocks mapping
        if isinstance(patches, str):
            parsed_mf = cls.parse_multi_file_patches(patches)
            if not parsed_mf:
                return False, [], "No valid SEARCH/REPLACE blocks found in patch text"

            for fp, s_part, r_part in parsed_mf:
                if not fp:
                    return False, [], "Multi-file patch contains blocks without target file paths"
                target_path, path_error = cls._resolve_multi_file_target(base, fp)
                if target_path is None:
                    return False, [], path_error
                file_to_blocks.setdefault(target_path, []).append((s_part, r_part))

        elif isinstance(patches, dict):
            for fp, val in patches.items():
                target_path, path_error = cls._resolve_multi_file_target(base, fp)
                if target_path is None:
                    return False, [], path_error
                if isinstance(val, str):
                    b_list = cls.parse_search_replace_blocks(val)
                elif isinstance(val, list):
                    b_list = val
                else:
                    return False, [], f"Invalid patch format for file: {fp}"
                file_to_blocks[target_path] = b_list

        elif isinstance(patches, (list, tuple)):
            for item in patches:
                if isinstance(item, FilePatch):
                    if not item.file_path:
                        return False, [], "FilePatch item missing file_path"
                    target_path, path_error = cls._resolve_multi_file_target(base, item.file_path)
                    if target_path is None:
                        return False, [], path_error
                    file_to_blocks.setdefault(target_path, []).append((item.search_block, item.replace_block))
                elif isinstance(item, dict):
                    fp = item.get("file_path") or item.get("file") or item.get("path")
                    if not fp:
                        return False, [], "Dictionary patch item missing file path"
                    target_path, path_error = cls._resolve_multi_file_target(base, fp)
                    if target_path is None:
                        return False, [], path_error
                    s_part = item.get("search_block") or item.get("search") or ""
                    r_part = item.get("replace_block") or item.get("replace") or ""
                    file_to_blocks.setdefault(target_path, []).append((s_part, r_part))
                elif isinstance(item, (list, tuple)):
                    if len(item) == 3:
                        fp, s_part, r_part = item
                        if not fp:
                            return False, [], "Patch tuple missing file path"
                        target_path, path_error = cls._resolve_multi_file_target(base, fp)
                        if target_path is None:
                            return False, [], path_error
                        file_to_blocks.setdefault(target_path, []).append((s_part, r_part))
                    elif len(item) == 2:
                        fp, patch_val = item
                        target_path, path_error = cls._resolve_multi_file_target(base, fp)
                        if target_path is None:
                            return False, [], path_error
                        if isinstance(patch_val, str):
                            b_list = cls.parse_search_replace_blocks(patch_val)
                        else:
                            b_list = patch_val
                        file_to_blocks[target_path] = b_list
                    else:
                        return False, [], f"Invalid patch tuple length: {len(item)}"
                else:
                    return False, [], f"Unsupported patch item type: {type(item)}"
        else:
            return False, [], f"Unsupported patches type: {type(patches)}"

        if not file_to_blocks:
            return False, [], "No valid patches or target files provided"

        # 2. In-memory execution stage (Zero disk writes)
        original_contents: Dict[Path, Optional[str]] = {}
        patched_contents: Dict[Path, str] = {}

        for target_path, blocks in file_to_blocks.items():
            if not target_path.exists():
                # Allow new file creation if first block has empty search
                if blocks and not blocks[0][0]:
                    orig_code = ""
                    original_contents[target_path] = None
                else:
                    return False, [], f"Target file not found: {target_path}"
            else:
                try:
                    orig_code = target_path.read_text(encoding="utf-8")
                except Exception as e:
                    return False, [], f"Failed to read target file {target_path}: {e}"
                original_contents[target_path] = orig_code

            curr_code = orig_code
            for idx, (search_block, replace_block) in enumerate(blocks, start=1):
                if not search_block and not curr_code:
                    curr_code = replace_block
                else:
                    success, next_code, err = cls.apply_patch(
                        curr_code,
                        search_block,
                        replace_block,
                        fuzzy=True,
                    )
                    if not success:
                        return False, [], f"Patch block {idx} failed for {target_path.name}: {err} - Transaction aborted"
                    curr_code = next_code

            # AST Syntax validation for Python files
            if validate_ast and target_path.suffix.lower() == ".py" and curr_code.strip():
                try:
                    ast.parse(curr_code, filename=str(target_path))
                except SyntaxError as e:
                    return (
                        False,
                        [],
                        f"AST SyntaxError in {target_path.name} on line {e.lineno}: {e.msg} - All changes rolled back",
                    )
                except Exception as e:
                    return (
                        False,
                        [],
                        f"AST validation error in {target_path.name}: {e} - All changes rolled back",
                    )

            patched_contents[target_path] = curr_code

        # 3. Transactional commit stage with automatic rollback on I/O error
        written_files: List[Path] = []
        modified_file_paths: List[str] = []

        try:
            for target_path, new_code in patched_contents.items():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(new_code, encoding="utf-8")
                written_files.append(target_path)
                modified_file_paths.append(str(target_path))

            return True, modified_file_paths, ""

        except Exception as e:
            # Transactional Rollback: Restore all written files to their exact initial state
            for written_path in written_files:
                orig = original_contents.get(written_path)
                if orig is None:
                    if written_path.exists():
                        written_path.unlink(missing_ok=True)
                else:
                    written_path.write_text(orig, encoding="utf-8")

            return False, [], f"Transactional write error: {e} - All changes rolled back"

    @classmethod
    def apply_batch_patches(
        cls,
        patches: Union[str, Dict[str, Union[str, List[Tuple[str, str]]]], Sequence[Any]],
        base_dir: Optional[Union[str, Path]] = None,
        validate_ast: bool = True,
    ) -> Tuple[bool, List[str], str]:
        """Convenience alias for `apply_multi_file_patches`."""
        return cls.apply_multi_file_patches(patches, base_dir=base_dir, validate_ast=validate_ast)

    # =========================================================================
    # 4. Clean Diff Generation & CLI Preview Rendering
    # =========================================================================

    @classmethod
    def generate_diff(
        cls,
        original_code: str,
        patched_code: str,
        file_path: str = "file",
    ) -> str:
        """
        Generates standard unified diff format between original and patched code.

        Args:
            original_code: Original code string.
            patched_code: Patched code string.
            file_path: Target filename label for headers.

        Returns:
            Unified diff string.
        """
        orig_lines = original_code.splitlines(keepends=True)
        patched_lines = patched_code.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            patched_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
        return "\n".join([line.rstrip("\r\n") for line in diff])

    @classmethod
    def get_diff_stats(cls, diff_text: str) -> Tuple[int, int]:
        """
        Computes the number of additions and deletions in a unified diff.

        Args:
            diff_text: Unified diff text.

        Returns:
            Tuple of (additions_count: int, deletions_count: int).
        """
        additions = 0
        deletions = 0
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                additions += 1
            elif line.startswith("-"):
                deletions += 1
        return additions, deletions

    @classmethod
    def render_diff(
        cls,
        diff_text: str,
        colorize: bool = True,
    ) -> str:
        """
        Renders a unified diff with clean terminal ANSI color highlighting.

        Args:
            diff_text: Raw unified diff string.
            colorize: Whether to include ANSI escape color sequences.

        Returns:
            Formatted diff string ready for terminal printing.
        """
        if not diff_text.strip():
            return ""
        if not colorize:
            return diff_text

        rendered_lines: List[str] = []
        for line in diff_text.splitlines():
            if line.startswith("---") or line.startswith("+++"):
                rendered_lines.append(f"{cls.ANSI_BOLD}{cls.ANSI_CYAN}{line}{cls.ANSI_RESET}")
            elif line.startswith("@@"):
                rendered_lines.append(f"{cls.ANSI_CYAN}{line}{cls.ANSI_RESET}")
            elif line.startswith("+"):
                rendered_lines.append(f"{cls.ANSI_GREEN}{line}{cls.ANSI_RESET}")
            elif line.startswith("-"):
                rendered_lines.append(f"{cls.ANSI_RED}{line}{cls.ANSI_RESET}")
            else:
                rendered_lines.append(f"{cls.ANSI_DIM}{line}{cls.ANSI_RESET}")

        return "\n".join(rendered_lines)

    @classmethod
    def render_diff_preview(
        cls,
        original_code: str,
        patched_code: str,
        file_path: str = "file",
        colorize: bool = True,
    ) -> str:
        """
        Generates and renders a clean diff preview for a single file edit.

        Args:
            original_code: Original code string.
            patched_code: Patched code string.
            file_path: File path label.
            colorize: Whether to colorize output.

        Returns:
            Rendered diff string or '[No changes]' message.
        """
        diff = cls.generate_diff(original_code, patched_code, file_path=file_path)
        if not diff.strip():
            return "[No changes]"
        return cls.render_diff(diff, colorize=colorize)

    @classmethod
    def render_batch_diff_preview(
        cls,
        file_diffs: Dict[str, Tuple[str, str]],
        colorize: bool = True,
    ) -> str:
        """
        Renders a clean summary and detailed diff preview for a batch of multi-file edits.

        Args:
            file_diffs: Dictionary mapping file_path -> (original_code, patched_code).
            colorize: Whether to colorize output.

        Returns:
            Formatted multi-file diff summary and file-by-file preview string.
        """
        if not file_diffs:
            return "[No changes]"

        total_added = 0
        total_deleted = 0
        file_sections: List[str] = []

        for file_path, (orig, patched) in file_diffs.items():
            diff = cls.generate_diff(orig, patched, file_path=file_path)
            if not diff.strip():
                continue
            adds, dels = cls.get_diff_stats(diff)
            total_added += adds
            total_deleted += dels
            file_sections.append(cls.render_diff(diff, colorize=colorize))

        if not file_sections:
            return "[No changes detected]"

        summary_title = f"=== Diff Preview: {len(file_sections)} file(s) changed (+{total_added}, -{total_deleted} lines) ==="
        if colorize:
            summary_title = f"{cls.ANSI_BOLD}{cls.ANSI_MAGENTA}{summary_title}{cls.ANSI_RESET}"

        divider = "=" * 60
        return f"{summary_title}\n" + f"\n{divider}\n".join(file_sections)

    @classmethod
    def get_rich_diff(
        cls,
        original_code: str,
        patched_code: str,
        file_path: str = "file",
    ) -> Any:
        """
        Returns a rich Syntax or Panel object for terminal rendering if `rich` is installed.

        Args:
            original_code: Original code string.
            patched_code: Patched code string.
            file_path: File path label.

        Returns:
            Rich renderable or colored diff string.
        """
        diff = cls.generate_diff(original_code, patched_code, file_path=file_path)
        try:
            from rich.syntax import Syntax
            return Syntax(diff, "diff", theme="monokai", line_numbers=True)
        except Exception:
            return cls.render_diff(diff, colorize=True)
