"""feature.py - Codebase feature inspection and evidence collection tool."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Union
import ast


@dataclass
class EvidenceMatch:
    category: str  # "source", "test", "symbol"
    path: str
    line: int
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "path": self.path,
            "line": self.line,
            "evidence": self.evidence,
        }


@dataclass
class FeatureEvidence:
    query: str
    source_matches: List[EvidenceMatch] = field(default_factory=list)
    test_matches: List[EvidenceMatch] = field(default_factory=list)
    symbol_matches: List[EvidenceMatch] = field(default_factory=list)
    proven: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "proven": self.proven,
            "source_matches": [m.to_dict() for m in self.source_matches],
            "test_matches": [m.to_dict() for m in self.test_matches],
            "symbol_matches": [m.to_dict() for m in self.symbol_matches],
        }


def inspect_feature(query: str, root_dir: Union[str, Path] = ".") -> FeatureEvidence:
    """Collect read-only source and test evidence for a feature query in workspace."""
    root = Path(root_dir).resolve()
    query_terms = [t.lower() for t in query.split() if t.strip()]

    source_matches: List[EvidenceMatch] = []
    test_matches: List[EvidenceMatch] = []
    symbol_matches: List[EvidenceMatch] = []

    if not root.exists():
        return FeatureEvidence(query=query, proven=False)

    for py_file in root.rglob("*.py"):
        rel_path = str(py_file.relative_to(root)) if root in py_file.parents else str(py_file)
        if any(part.startswith(".") or part in ("__pycache__", "venv", ".venv", "build", "dist") for part in py_file.parts):
            continue

        is_test_file = "test" in py_file.name.lower() or "tests" in rel_path.lower().split("/")

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            # Text line matching
            for idx, line in enumerate(lines, 1):
                line_lower = line.lower()
                if all(term in line_lower for term in query_terms):
                    match = EvidenceMatch(
                        category="test" if is_test_file else "source",
                        path=rel_path,
                        line=idx,
                        evidence=line.strip(),
                    )
                    if is_test_file:
                        test_matches.append(match)
                    else:
                        source_matches.append(match)

            # AST symbol matching
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    node_name_lower = node.name.lower()
                    if any(term in node_name_lower for term in query_terms):
                        symbol_matches.append(
                            EvidenceMatch(
                                category="symbol",
                                path=rel_path,
                                line=node.lineno,
                                evidence=f"{node.__class__.__name__}: {node.name}",
                            )
                        )
        except Exception:
            continue

    proven = len(source_matches) > 0 or len(symbol_matches) > 0
    return FeatureEvidence(
        query=query,
        source_matches=source_matches,
        test_matches=test_matches,
        symbol_matches=symbol_matches,
        proven=proven,
    )
