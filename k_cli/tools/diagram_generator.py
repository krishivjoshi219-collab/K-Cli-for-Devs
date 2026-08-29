"""
diagram_generator.py - Visual Architecture & Mermaid Diagram Generator for K-CLI

Features:
1. Multi-Language AST & Symbol Inspection:
   - Integrates with `repo_map.py` to inspect classes, functions, imports, and module dependencies.
   - Detects hierarchical layers (UI, Core Engine, Verification & Safety, Knowledge & Context).
2. Clean, Beautiful Mermaid Diagram Synthesis:
   - High-Level Architecture Flowchart (`flowchart TD` / `graph TD`) with styled subgraphs and nodes.
   - Core Sequence Diagrams (`sequenceDiagram`) tracing execution loops (Incident Triage & Auto-Heal, Verification Loop, Subagent Swarm DAG).
   - Component & Module Dependency Matrix Diagrams.
   - Class Hierarchy Diagrams (`classDiagram`) with methods and properties.
3. Terminal Output & Markdown File Injection:
   - Outputs directly to CLI/TUI terminal.
   - Injects or updates diagrams cleanly in `ARCHITECTURE.md`, `README.md`, or custom markdown documents using bounded comment markers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Safe import for RepoMap
try:
    from k_cli.git.repo_map import RepoMap
except (ModuleNotFoundError, ImportError):
    try:
        from repo_map import RepoMap
    except (ModuleNotFoundError, ImportError):
        RepoMap = None  # type: ignore


class DiagramType(str, Enum):
    """Supported diagram types."""
    FLOWCHART = "flowchart"
    SEQUENCE = "sequence"
    CLASS_DIAGRAM = "class_diagram"
    COMPONENT = "component"
    ALL = "all"


class DiagramGenerator:
    """
    AST-driven Mermaid architecture diagram generator and markdown injector.
    """

    MARKER_START = "<!-- K_CLI_ARCHITECTURE_START -->"
    MARKER_END = "<!-- K_CLI_ARCHITECTURE_END -->"

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self._repo_map = RepoMap(str(self.repo_path)) if RepoMap else None

    # =========================================================================
    # 1. Flowchart & Architecture Diagram Synthesis
    # =========================================================================

    def _sanitize_id(self, name: str) -> str:
        """Sanitizes module/file name to a valid Mermaid node identifier."""
        clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if clean and clean[0].isdigit():
            clean = f"node_{clean}"
        return clean or "node_root"

    def _classify_layer(self, rel_path: str) -> str:
        """Classifies a file or module into architectural layers."""
        fname = Path(rel_path).name.lower()
        if "test" in fname or "tests" in rel_path:
            return "Test Suite & Verification"
        elif any(token in fname for token in ("cli", "tui", "repl", "view", "viewer", "ui", "console")):
            return "UI & Workstation"
        elif any(token in fname for token in ("orchestrator", "llm", "driver", "model", "subagent", "persona", "mcp")):
            return "Core Engine & Agent Swarm"
        elif any(token in fname for token in ("verifier", "patcher", "guard", "security", "audit", "rollback")):
            return "Verification & Safety Net"
        elif any(token in fname for token in ("repo_map", "doc", "retriever", "rule", "workflow", "triage", "diagram", "dedup")):
            return "Knowledge & Visual Architecture"
        else:
            parent = Path(rel_path).parent.name
            return parent.capitalize() if parent and parent != "." else "General Modules"

    def generate_flowchart(
        self,
        repo_path: Optional[str] = None,
        focus_modules: Optional[List[str]] = None,
        max_nodes: int = 35,
        direction: str = "TD",
    ) -> str:
        """
        Generates a clean Mermaid flowchart diagram of repository architecture,
        grouping modules into styled subgraphs with symbol summaries and dependency edges.

        Args:
            repo_path: Optional workspace path.
            focus_modules: Optional list of modules to focus on.
            max_nodes: Maximum nodes to render in the diagram.
            direction: Graph direction ('TD', 'LR', 'TB').

        Returns:
            Mermaid flowchart markdown string.
        """
        r_path = Path(repo_path).resolve() if repo_path else self.repo_path
        rm = RepoMap(str(r_path)) if RepoMap else self._repo_map

        if not rm:
            return "```mermaid\ngraph TD\n  Root[\"Workspace\"]\n```"

        files = rm.scan_workspace_files()
        if not files:
            return "```mermaid\ngraph TD\n  Empty[\"Empty Workspace\"]\n```"

        dep_graph = rm.get_dependency_graph()

        # Filter and prioritize files
        rel_files: List[Tuple[str, str]] = []  # (abs_path, rel_path)
        for f in files:
            try:
                rel = str(Path(f).relative_to(r_path)).replace("\\", "/")
            except ValueError:
                rel = Path(f).name

            if focus_modules:
                if any(m in rel for m in focus_modules):
                    rel_files.append((f, rel))
            else:
                # Skip deeply nested tests or cache if exceeding max_nodes
                if not rel.startswith("tests/") and not rel.startswith("k_cli_env/"):
                    rel_files.append((f, rel))

        if len(rel_files) > max_nodes:
            rel_files = rel_files[:max_nodes]

        # Group by layer
        layer_groups: Dict[str, List[Tuple[str, str, List[Dict[str, Any]]]]] = {}
        for abs_p, rel_p in rel_files:
            layer = self._classify_layer(rel_p)
            symbols = rm.extract_symbols(abs_p) if rm else []
            layer_groups.setdefault(layer, []).append((abs_p, rel_p, symbols))

        lines: List[str] = [
            f"```mermaid",
            f"flowchart {direction}",
        ]

        # Render subgraphs
        node_id_map: Dict[str, str] = {}

        for layer_name, members in layer_groups.items():
            subgraph_id = self._sanitize_id(layer_name)
            lines.append(f"  subgraph {subgraph_id}[\"{layer_name}\"]")
            for abs_p, rel_p, symbols in members:
                node_id = self._sanitize_id(rel_p)
                node_id_map[rel_p] = node_id
                node_id_map[Path(rel_p).stem] = node_id
                node_id_map[Path(rel_p).name] = node_id

                # Format key symbols (classes & functions)
                classes = [s["name"] for s in symbols if s.get("type") in ("class", "struct")][:2]
                funcs = [s["name"] for s in symbols if s.get("type") in ("function", "async_function")][:2]

                symbol_text = ""
                if classes:
                    symbol_text += "<br/><b>Classes:</b> " + ", ".join(classes)
                if funcs and not classes:
                    symbol_text += "<br/><b>Funcs:</b> " + ", ".join(funcs)

                label = f"<b>{Path(rel_p).name}</b>{symbol_text}"
                lines.append(f"    {node_id}[\"{label}\"]")
            lines.append("  end")

        # Render dependency edges
        added_edges: Set[Tuple[str, str]] = set()
        for src_rel, targets in dep_graph.items():
            src_id = node_id_map.get(src_rel) or node_id_map.get(Path(src_rel).stem) or node_id_map.get(Path(src_rel).name)
            if not src_id:
                continue
            for tgt_rel in targets:
                tgt_id = node_id_map.get(tgt_rel) or node_id_map.get(Path(tgt_rel).stem) or node_id_map.get(Path(tgt_rel).name)
                if tgt_id and tgt_id != src_id and (src_id, tgt_id) not in added_edges:
                    added_edges.add((src_id, tgt_id))
                    lines.append(f"  {src_id} --> {tgt_id}")

        # Add CSS classes & styling
        lines.append("")
        lines.append("  %% Styling & Theme")
        lines.append("  classDef ui fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c;")
        lines.append("  classDef core fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;")
        lines.append("  classDef safety fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20;")
        lines.append("  classDef knowledge fill:#fff3e0,stroke:#fb8c00,stroke-width:2px,color:#e65100;")
        lines.append("  classDef general fill:#eceff1,stroke:#607d8b,stroke-width:2px,color:#263238;")

        # Apply classes to nodes
        for rel_p, node_id in node_id_map.items():
            layer = self._classify_layer(rel_p)
            if "UI" in layer:
                lines.append(f"  class {node_id} ui;")
            elif "Core" in layer:
                lines.append(f"  class {node_id} core;")
            elif "Verification" in layer or "Safety" in layer:
                lines.append(f"  class {node_id} safety;")
            elif "Knowledge" in layer or "Visual" in layer:
                lines.append(f"  class {node_id} knowledge;")
            else:
                lines.append(f"  class {node_id} general;")

        lines.append("```")
        return "\n".join(lines)

    # =========================================================================
    # 2. Sequence Diagrams Synthesis
    # =========================================================================

    def generate_sequence_diagram(
        self,
        flow_name: str = "incident_triage",
        repo_path: Optional[str] = None,
    ) -> str:
        """
        Generates Mermaid sequence diagrams for key architectural workflows.

        Supported flows:
        - "incident_triage" / "triage_and_heal": Incident log ingestion, culprit AST resolution, and auto-heal loop.
        - "verification_loop" / "agent_execution": Developer task, LLM generation, AST verification, and git checkpoint.
        - "subagent_swarm" / "dag_execution": Parallel task decomposition, role worker dispatch, and synthesis.
        """
        flow = flow_name.lower().strip()

        if flow in ("incident_triage", "triage", "auto_heal", "triage_and_heal"):
            return (
                "```mermaid\n"
                "sequenceDiagram\n"
                "  autonumber\n"
                "  actor Dev as Developer / CI\n"
                "  participant CLI as k-cli CLI/TUI\n"
                "  participant Triage as IncidentTriageEngine\n"
                "  participant Repo as RepoMap (AST)\n"
                "  participant LLM as Universal LLM Driver\n"
                "  participant Patcher as Surgical Patcher\n"
                "  participant Verifier as Ground-Truth Verifier\n"
                "  participant Git as Git Guard\n"
                "\n"
                "  Dev->>CLI: k incident triage --log crash.log\n"
                "  CLI->>Triage: triage_log_or_trace(raw_log)\n"
                "  Triage->>Triage: Parse stack trace (Python/Node/Rust/Go/C++/Docker/CI)\n"
                "  Triage->>Repo: Cross-reference culprit frames & extract AST symbol\n"
                "  Repo-->>Triage: Enclosing symbol, lines, and source snippet\n"
                "  Triage->>LLM: Analyze root cause & synthesize reproduction\n"
                "  LLM-->>Triage: IncidentReport (Root Cause & Fix Guidance)\n"
                "  Triage-->>CLI: IncidentReport Card\n"
                "\n"
                "  opt Auto-Heal Enabled\n"
                "    CLI->>Triage: auto_heal_incident(incident, verifier, patcher)\n"
                "    Triage->>Git: Create workspace safety snapshot\n"
                "    Triage->>LLM: Generate SEARCH/REPLACE patch & regression test\n"
                "    LLM-->>Triage: Surgical Patch Blocks + Test Code\n"
                "    Triage->>Patcher: Apply candidate SEARCH/REPLACE block\n"
                "    Patcher-->>Triage: Syntactically patched file\n"
                "    Triage->>Verifier: Validate AST syntax & execute regression test\n"
                "    alt Verification Passes\n"
                "      Verifier-->>Triage: Test Passed (0 errors)\n"
                "      Triage->>Git: Commit atomic verified change\n"
                "      Triage-->>CLI: IncidentHealResult (Success & Diff)\n"
                "      CLI-->>Dev: Verified Fix Applied & Diff Rendered\n"
                "    else Verification Fails\n"
                "      Verifier-->>Triage: Test Failure Trace\n"
                "      Triage->>Git: Rollback workspace (git restore)\n"
                "      Triage-->>CLI: IncidentHealResult (Failure & Safe Rollback)\n"
                "      CLI-->>Dev: Rollback Notification & Diagnostics\n"
                "    end\n"
                "  end\n"
                "```"
            )

        elif flow in ("verification_loop", "agent_execution", "core_loop"):
            return (
                "```mermaid\n"
                "sequenceDiagram\n"
                "  autonumber\n"
                "  actor Dev as Developer\n"
                "  participant CLI as CLI / TUI Workstation\n"
                "  participant Session as Session & Rules\n"
                "  participant LLM as Universal LLM Driver\n"
                "  participant Verifier as Ground-Truth Verifier\n"
                "  participant Patcher as Surgical Patcher\n"
                "  participant Git as Git Guard\n"
                "\n"
                "  Dev->>CLI: k-cli run \"task\" or /plan\n"
                "  CLI->>Session: Load context files & bounded rules\n"
                "  Session->>LLM: Enhanced prompt with repo map & signatures\n"
                "  LLM-->>Session: Candidate code / SEARCH-REPLACE blocks\n"
                "  Session->>Verifier: AST Syntax & Type Check\n"
                "  alt Verification Fails\n"
                "    Verifier-->>Session: Syntax error trace & line numbers\n"
                "    Session->>LLM: Auto-debug prompt with error trace\n"
                "    LLM-->>Session: Repaired candidate code\n"
                "    Session->>Verifier: Re-verify repaired code\n"
                "  end\n"
                "  Session->>Git: Create workspace safety checkpoint\n"
                "  Session->>Patcher: Apply surgical patch\n"
                "  Session->>Verifier: Run project test suite (pytest / cargo / npm)\n"
                "  alt Tests Pass\n"
                "    Verifier-->>Session: All tests passed\n"
                "    Session->>Git: Commit atomic verified change\n"
                "    Session-->>CLI: Verified Diff & Success Card\n"
                "  else Tests Fail\n"
                "    Verifier-->>Session: Test failure output\n"
                "    Session->>Git: Auto-rollback workspace (git restore)\n"
                "    Session-->>CLI: Rollback notification & error details\n"
                "  end\n"
                "```"
            )

        elif flow in ("subagent_swarm", "dag_execution", "swarm"):
            return (
                "```mermaid\n"
                "sequenceDiagram\n"
                "  autonumber\n"
                "  actor User as Developer\n"
                "  participant Orch as Orchestrator\n"
                "  participant Disp as SubagentDispatcher\n"
                "  participant Exp as [EXPLORER Worker]\n"
                "  participant Res as [RESEARCHER Worker]\n"
                "  participant Cod as [CODER Worker]\n"
                "  participant Test as [TESTER Worker]\n"
                "  participant Ver as Verifier Guard\n"
                "\n"
                "  User->>Orch: Execute multi-stage goal\n"
                "  Orch->>Disp: Decompose into DAG Task Graph\n"
                "  Disp->>Exp: 1. Survey workspace & dependencies\n"
                "  Exp-->>Disp: Workspace context & file list\n"
                "  Disp->>Res: 2. Extract signatures & DevDocs\n"
                "  Res-->>Disp: API contracts & interfaces\n"
                "  Disp->>Cod: 3. Generate surgical implementation\n"
                "  Cod-->>Disp: Candidate patch blocks\n"
                "  Disp->>Test: 4. Generate regression test suite\n"
                "  Test-->>Disp: Unit test code\n"
                "  Disp->>Ver: Verify AST syntax & execute test\n"
                "  Ver-->>Disp: Verification passed\n"
                "  Disp-->>Orch: Aggregated DAG Execution Result\n"
                "  Orch-->>User: Verified Goal Completed\n"
                "```"
            )

        else:
            # Generic workflow sequence diagram
            return (
                "```mermaid\n"
                "sequenceDiagram\n"
                "  autonumber\n"
                "  actor User\n"
                "  participant CLI as k-cli\n"
                "  participant Core as Core Engine\n"
                "  participant Output as Result\n"
                "  User->>CLI: Invoke command\n"
                "  CLI->>Core: Process request\n"
                "  Core-->>Output: Render results\n"
                "  Output-->>User: Display in terminal / file\n"
                "```"
            )

    # =========================================================================
    # 3. Class Diagram Synthesis
    # =========================================================================

    def generate_class_diagram(
        self,
        repo_path: Optional[str] = None,
        focus_files: Optional[List[str]] = None,
        max_classes: int = 20,
    ) -> str:
        """
        Generates a Mermaid classDiagram showing classes, methods, and relationships.

        Args:
            repo_path: Optional workspace path.
            focus_files: Optional file list to filter.
            max_classes: Max classes to include.

        Returns:
            Mermaid classDiagram markdown string.
        """
        r_path = Path(repo_path).resolve() if repo_path else self.repo_path
        rm = RepoMap(str(r_path)) if RepoMap else self._repo_map

        if not rm:
            return "```mermaid\nclassDiagram\n  class Workspace\n```"

        files = rm.scan_workspace_files()
        lines: List[str] = [
            "```mermaid",
            "classDiagram",
        ]

        class_count = 0
        for f in files:
            try:
                rel = str(Path(f).relative_to(r_path)).replace("\\", "/")
            except ValueError:
                rel = Path(f).name

            if focus_files and not any(ff in rel for ff in focus_files):
                continue
            if "test" in rel or "k_cli_env" in rel:
                continue

            symbols = rm.extract_symbols(f)
            for sym in symbols:
                if sym.get("type") in ("class", "struct") and class_count < max_classes:
                    cname = sym.get("name", "")
                    if not cname:
                        continue
                    class_count += 1
                    safe_cname = self._sanitize_id(cname)
                    lines.append(f"  class {safe_cname} {{")
                    # Add methods
                    methods = sym.get("methods", [])
                    for m in methods[:5]:
                        m_name = m.get("name", "")
                        if m_name and not m_name.startswith("__"):
                            lines.append(f"    +{m_name}()")
                    lines.append("  }")

        if class_count == 0:
            lines.append("  class KCLIApplication")

        lines.append("```")
        return "\n".join(lines)

    # =========================================================================
    # 4. Comprehensive Architecture Synthesis & Markdown Injection
    # =========================================================================

    def generate_mermaid_architecture(
        self,
        repo_path: str = ".",
        output_file: Optional[str] = None,
        diagram_type: str = "all",
        title: Optional[str] = None,
    ) -> str:
        """
        Main entrypoint: Inspects codebase AST imports, symbol dependencies, and module hierarchy,
        produces clean, beautiful Mermaid flowchart and sequence diagrams, and optionally
        injects/updates into ARCHITECTURE.md or README.md.

        Args:
            repo_path: Root directory of the repository.
            output_file: Optional path to markdown file for injection (e.g. ARCHITECTURE.md).
            diagram_type: Diagram type ('flowchart', 'sequence', 'class_diagram', 'all').
            title: Optional custom section title.

        Returns:
            Generated Markdown document containing the complete architecture diagrams.
        """
        self.repo_path = Path(repo_path).resolve()

        sections: List[str] = []
        sec_title = title or "K-CLI Visual Repository Architecture"
        sections.append(f"## {sec_title}\n")

        dtype = diagram_type.lower().strip()

        if dtype in ("flowchart", "all"):
            sections.append("### 1. High-Level Modular Component Architecture")
            sections.append(self.generate_flowchart(repo_path=str(self.repo_path)))
            sections.append("")

        if dtype in ("sequence", "all"):
            sections.append("### 2. Incident Triage & Auto-Heal Execution Loop")
            sections.append(self.generate_sequence_diagram(flow_name="incident_triage", repo_path=str(self.repo_path)))
            sections.append("")

            sections.append("### 3. Ground-Truth Verification & Rollback Loop")
            sections.append(self.generate_sequence_diagram(flow_name="verification_loop", repo_path=str(self.repo_path)))
            sections.append("")

        if dtype in ("class_diagram", "all"):
            sections.append("### 4. Core Domain Symbol & Class Hierarchy")
            sections.append(self.generate_class_diagram(repo_path=str(self.repo_path)))
            sections.append("")

        full_content = "\n".join(sections)

        if output_file:
            self.inject_into_file(full_content, output_file)

        return full_content

    def inject_into_file(
        self,
        content: str,
        output_file: str,
        marker_start: str = MARKER_START,
        marker_end: str = MARKER_END,
    ) -> bool:
        """
        Injects or updates generated Mermaid architecture diagrams into a Markdown file
        (e.g., ARCHITECTURE.md or README.md) enclosed cleanly within comment markers.

        Args:
            content: Diagram content to inject.
            output_file: Target file path.
            marker_start: Opening comment marker.
            marker_end: Closing comment marker.

        Returns:
            True if injection was successful.
        """
        out_path = Path(output_file)
        if not out_path.is_absolute():
            out_path = (self.repo_path / out_path).resolve()

        out_path.parent.mkdir(parents=True, exist_ok=True)

        wrapped_content = f"{marker_start}\n\n{content.strip()}\n\n{marker_end}"

        if out_path.exists() and out_path.is_file():
            existing_text = out_path.read_text(encoding="utf-8", errors="replace")
            if marker_start in existing_text and marker_end in existing_text:
                # Replace between markers
                pattern = re.compile(
                    re.escape(marker_start) + r"[\s\S]*?" + re.escape(marker_end),
                    re.MULTILINE,
                )
                updated_text = pattern.sub(wrapped_content, existing_text)
            else:
                # Append to bottom of file
                updated_text = existing_text.rstrip() + "\n\n---\n\n" + wrapped_content + "\n"
        else:
            # Create fresh document
            updated_text = f"# Repository Architecture\n\n{wrapped_content}\n"

        out_path.write_text(updated_text, encoding="utf-8")
        logger.info(f"Successfully injected Mermaid architecture diagram into {out_path}")
        return True


__all__ = [
    "DiagramType",
    "DiagramGenerator",
]
