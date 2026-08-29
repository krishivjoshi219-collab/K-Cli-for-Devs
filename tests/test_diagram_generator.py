"""
test_diagram_generator.py - Comprehensive Unit Tests for Mermaid Diagram Generator
"""

import tempfile
from pathlib import Path

import pytest

from k_cli.tools.diagram_generator import DiagramGenerator, DiagramType


@pytest.fixture
def temp_repo():
    """Creates a temporary repository structure with sample components and classes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # UI layer
        (root / "cli.py").write_text(
            "class CommandLineApp:\n"
            "    def run(self):\n"
            "        pass\n"
            "    def parse_args(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        # Core Engine layer
        (root / "orchestrator.py").write_text(
            "from cli import CommandLineApp\n"
            "class Orchestrator:\n"
            "    def execute_pipeline(self):\n"
            "        pass\n"
            "    def step(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        (root / "llm_driver.py").write_text(
            "class UniversalLLMDriver:\n"
            "    def generate(self, prompt: str):\n"
            "        pass\n",
            encoding="utf-8",
        )

        # Verification & Safety layer
        (root / "verifier.py").write_text(
            "class GroundTruthVerifier:\n"
            "    def verify_python_ast(self, code: str):\n"
            "        pass\n"
            "    def verify_execution(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        (root / "patcher.py").write_text(
            "class SurgicalPatcher:\n"
            "    def apply_patch(self, original: str, search: str, replace: str):\n"
            "        pass\n",
            encoding="utf-8",
        )

        # Knowledge & Architecture layer
        (root / "repo_map.py").write_text(
            "class RepoMap:\n"
            "    def scan_workspace(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        (root / "incident_triage.py").write_text(
            "from verifier import GroundTruthVerifier\n"
            "from patcher import SurgicalPatcher\n"
            "class IncidentTriageEngine:\n"
            "    def triage_log_or_trace(self, raw_log: str):\n"
            "        pass\n"
            "    def auto_heal_incident(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        (root / "diagram_generator.py").write_text(
            "from repo_map import RepoMap\n"
            "class DiagramGenerator:\n"
            "    def generate_mermaid_architecture(self):\n"
            "        pass\n",
            encoding="utf-8",
        )

        yield root


# =============================================================================
# 1. Initialization & Sanitization Tests
# =============================================================================

def test_diagram_generator_init(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    assert generator.repo_path == temp_repo.resolve()


def test_sanitize_id():
    generator = DiagramGenerator()
    assert generator._sanitize_id("cli.py") == "cli_py"
    assert generator._sanitize_id("k-cli/src/main.rs") == "k_cli_src_main_rs"
    assert generator._sanitize_id("123_module") == "node_123_module"
    assert generator._sanitize_id("") == "node_root"


def test_classify_layer():
    generator = DiagramGenerator()
    assert generator._classify_layer("cli.py") == "UI & Workstation"
    assert generator._classify_layer("tui_app.py") == "UI & Workstation"
    assert generator._classify_layer("orchestrator.py") == "Core Engine & Agent Swarm"
    assert generator._classify_layer("llm_driver.py") == "Core Engine & Agent Swarm"
    assert generator._classify_layer("verifier.py") == "Verification & Safety Net"
    assert generator._classify_layer("patcher.py") == "Verification & Safety Net"
    assert generator._classify_layer("incident_triage.py") == "Knowledge & Visual Architecture"
    assert generator._classify_layer("diagram_generator.py") == "Knowledge & Visual Architecture"
    assert generator._classify_layer("tests/test_cli.py") == "Test Suite & Verification"


# =============================================================================
# 2. Flowchart Diagram Generation Tests
# =============================================================================

def test_generate_flowchart_basic(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    flowchart = generator.generate_flowchart()

    assert "```mermaid" in flowchart
    assert "flowchart TD" in flowchart
    assert "subgraph" in flowchart
    assert "classDef ui" in flowchart
    assert "classDef core" in flowchart
    assert "classDef safety" in flowchart
    assert "classDef knowledge" in flowchart
    assert "```" in flowchart

    # Ensure key modules and classes are rendered
    assert "orchestrator_py" in flowchart
    assert "verifier_py" in flowchart
    assert "incident_triage_py" in flowchart


def test_generate_flowchart_focus_modules(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    flowchart = generator.generate_flowchart(focus_modules=["orchestrator", "verifier"])

    assert "orchestrator_py" in flowchart
    assert "verifier_py" in flowchart


def test_generate_flowchart_empty_workspace():
    with tempfile.TemporaryDirectory() as empty_dir:
        generator = DiagramGenerator(repo_path=empty_dir)
        flowchart = generator.generate_flowchart()
        assert "```mermaid" in flowchart
        assert "Empty" in flowchart or "flowchart" in flowchart


# =============================================================================
# 3. Sequence Diagram Generation Tests
# =============================================================================

def test_generate_sequence_diagram_incident_triage():
    generator = DiagramGenerator()
    seq = generator.generate_sequence_diagram(flow_name="incident_triage")

    assert "```mermaid" in seq
    assert "sequenceDiagram" in seq
    assert "autonumber" in seq
    assert "IncidentTriageEngine" in seq
    assert "RepoMap (AST)" in seq
    assert "Universal LLM Driver" in seq
    assert "Surgical Patcher" in seq
    assert "Ground-Truth Verifier" in seq
    assert "Git Guard" in seq
    assert "opt Auto-Heal Enabled" in seq
    assert "```" in seq


def test_generate_sequence_diagram_verification_loop():
    generator = DiagramGenerator()
    seq = generator.generate_sequence_diagram(flow_name="verification_loop")

    assert "```mermaid" in seq
    assert "sequenceDiagram" in seq
    assert "autonumber" in seq
    assert "Universal LLM Driver" in seq
    assert "Ground-Truth Verifier" in seq
    assert "Surgical Patcher" in seq
    assert "Git Guard" in seq
    assert "alt Verification Fails" in seq
    assert "```" in seq


def test_generate_sequence_diagram_subagent_swarm():
    generator = DiagramGenerator()
    seq = generator.generate_sequence_diagram(flow_name="subagent_swarm")

    assert "```mermaid" in seq
    assert "sequenceDiagram" in seq
    assert "autonumber" in seq
    assert "SubagentDispatcher" in seq
    assert "[EXPLORER Worker]" in seq
    assert "[RESEARCHER Worker]" in seq
    assert "[CODER Worker]" in seq
    assert "[TESTER Worker]" in seq
    assert "```" in seq


def test_generate_sequence_diagram_generic():
    generator = DiagramGenerator()
    seq = generator.generate_sequence_diagram(flow_name="custom_unknown_flow")

    assert "```mermaid" in seq
    assert "sequenceDiagram" in seq
    assert "User" in seq
    assert "```" in seq


# =============================================================================
# 4. Class Diagram Generation Tests
# =============================================================================

def test_generate_class_diagram(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    class_diag = generator.generate_class_diagram()

    assert "```mermaid" in class_diag
    assert "classDiagram" in class_diag
    assert "class Orchestrator" in class_diag
    assert "+execute_pipeline()" in class_diag or "+step()" in class_diag
    assert "class GroundTruthVerifier" in class_diag
    assert "class IncidentTriageEngine" in class_diag
    assert "```" in class_diag


def test_generate_class_diagram_filtered(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    class_diag = generator.generate_class_diagram(focus_files=["verifier.py"])

    assert "class GroundTruthVerifier" in class_diag
    assert "class CommandLineApp" not in class_diag


# =============================================================================
# 5. Full Architecture Generation & Markdown Injection Tests
# =============================================================================

def test_generate_mermaid_architecture_all(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    full_arch = generator.generate_mermaid_architecture(diagram_type="all")

    assert "## K-CLI Visual Repository Architecture" in full_arch
    assert "### 1. High-Level Modular Component Architecture" in full_arch
    assert "### 2. Incident Triage & Auto-Heal Execution Loop" in full_arch
    assert "### 3. Ground-Truth Verification & Rollback Loop" in full_arch
    assert "### 4. Core Domain Symbol & Class Hierarchy" in full_arch
    assert "flowchart TD" in full_arch
    assert "sequenceDiagram" in full_arch
    assert "classDiagram" in full_arch


def test_generate_mermaid_architecture_filtered_types(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))

    fc_only = generator.generate_mermaid_architecture(diagram_type="flowchart")
    assert "flowchart TD" in fc_only
    assert "sequenceDiagram" not in fc_only

    seq_only = generator.generate_mermaid_architecture(diagram_type="sequence")
    assert "sequenceDiagram" in seq_only
    assert "flowchart TD" not in seq_only


def test_inject_into_new_file(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    out_file = temp_repo / "DOCS_ARCH.md"

    res = generator.inject_into_file(
        content="```mermaid\ngraph TD\n  A --> B\n```",
        output_file=str(out_file),
    )

    assert res is True
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert DiagramGenerator.MARKER_START in content
    assert "A --> B" in content
    assert DiagramGenerator.MARKER_END in content


def test_inject_into_existing_file_with_markers(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    out_file = temp_repo / "ARCHITECTURE.md"

    # Pre-existing file with markers and surrounding headers
    initial_text = (
        "# Custom Architecture Overview\n\n"
        "Here is the intro section.\n\n"
        f"{DiagramGenerator.MARKER_START}\n"
        "Old diagram content to be replaced.\n"
        f"{DiagramGenerator.MARKER_END}\n\n"
        "## Footer Section\n"
        "This footer text must be strictly preserved.\n"
    )
    out_file.write_text(initial_text, encoding="utf-8")

    generator.generate_mermaid_architecture(output_file=str(out_file), diagram_type="sequence")

    updated_text = out_file.read_text(encoding="utf-8")
    assert "# Custom Architecture Overview" in updated_text
    assert "Here is the intro section." in updated_text
    assert "## Footer Section" in updated_text
    assert "This footer text must be strictly preserved." in updated_text
    assert "Old diagram content to be replaced" not in updated_text
    assert "sequenceDiagram" in updated_text
    assert DiagramGenerator.MARKER_START in updated_text
    assert DiagramGenerator.MARKER_END in updated_text


def test_inject_into_existing_file_without_markers(temp_repo):
    generator = DiagramGenerator(repo_path=str(temp_repo))
    out_file = temp_repo / "README.md"

    initial_text = "# Project Readme\n\nWelcome to the project.\n"
    out_file.write_text(initial_text, encoding="utf-8")

    generator.inject_into_file(
        content="```mermaid\ngraph TD\n  Main --> Helper\n```",
        output_file=str(out_file),
    )

    updated_text = out_file.read_text(encoding="utf-8")
    assert "# Project Readme" in updated_text
    assert "Welcome to the project." in updated_text
    assert DiagramGenerator.MARKER_START in updated_text
    assert "Main --> Helper" in updated_text
    assert DiagramGenerator.MARKER_END in updated_text
