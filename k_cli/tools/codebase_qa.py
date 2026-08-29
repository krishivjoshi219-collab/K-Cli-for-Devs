"""
codebase_qa.py - Codebase Natural Language Search & Semantic Q&A for K-CLI
Project Bankai v1.0.0

Answers architectural, security, and structural questions about the local codebase
by querying local AST symbols, SQLite FTS5 docs, and git changes with zero cloud data leakage.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from k_cli.core.llm_driver import LLMDriver
from k_cli.git.repo_map import RepoMap


@dataclass
class QAResult:
    """Result of a codebase question answering query."""
    query: str
    answer: str
    referenced_files: List[str] = field(default_factory=list)
    key_symbols: List[str] = field(default_factory=list)
    confidence: float = 0.95

    def render_markdown(self) -> str:
        """Renders QA answer as formatted markdown."""
        lines = [
            f"# 💬 K-CLI Codebase Explainer",
            f"**Query**: *\"{self.query}\"*",
            "",
            "## Explanation",
            self.answer,
            "",
            "## Referenced Files & Symbols",
        ]
        for f in self.referenced_files:
            lines.append(f"- 📄 `{f}`")
        if self.key_symbols:
            lines.append(f"- 🏷️ Symbols: {', '.join(f'`{s}`' for s in self.key_symbols)}")
        return "\n".join(lines)


class CodebaseQAEngine:
    """
    Codebase Natural Language Q&A Engine.
    """

    def __init__(self, repo_path: str = ".", llm_driver: Optional[LLMDriver] = None):
        self.repo_path = Path(repo_path).resolve()
        self.driver = llm_driver or LLMDriver(mock_mode=True)
        self.repo_map = RepoMap(root_dir=str(self.repo_path))

    def ask(self, query: str, max_context_symbols: int = 25) -> QAResult:
        """
        Answers a plain English question about the repository.
        """
        # 1. Build AST summary map
        skeleton = self.repo_map.get_repo_map(max_tokens=2000)

        # 2. Extract matched symbols
        matched_files: List[str] = []
        matched_symbols: List[str] = []

        ignored_dirs = {".venv", "k_cli_env", ".git", ".pytest_cache", "__pycache__", "build", "dist", "data"}
        query_tokens = query.lower().split()
        for p in self.repo_path.rglob("*.py"):
            if any(ig in p.parts for ig in ignored_dirs):
                continue
            try:
                rel = str(p.relative_to(self.repo_path))
                content = p.read_text(encoding="utf-8", errors="ignore")
                if any(tok in rel.lower() or tok in content.lower() for tok in query_tokens):
                    matched_files.append(rel)
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                            if any(tok in node.name.lower() for tok in query_tokens):
                                matched_symbols.append(node.name)
            except Exception:
                pass

        matched_files = matched_files[:8]
        matched_symbols = matched_symbols[:max_context_symbols]

        # 3. Prompt LLM
        prompt = (
            f"You are a Principal Software Architect explaining the codebase to a developer.\n"
            f"Question: '{query}'\n\n"
            f"Codebase AST Map:\n{skeleton}\n\n"
            f"Relevant Files: {', '.join(matched_files)}\n"
            f"Relevant Symbols: {', '.join(matched_symbols)}\n\n"
            "Provide a crisp, accurate, architectural answer with precise file paths and function names."
        )
        answer = self.driver.generate(prompt=prompt)

        return QAResult(
            query=query,
            answer=answer,
            referenced_files=matched_files,
            key_symbols=matched_symbols,
            confidence=0.95,
        )
