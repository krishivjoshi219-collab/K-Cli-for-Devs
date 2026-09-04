import pytest
from pathlib import Path
from k_cli.agents.autonomous_agent import (
    AutonomousAgent,
    tool_list_dir,
    tool_read_workspace_file,
    tool_write_workspace_file,
    tool_edit_workspace_file,
    tool_execute_command,
    tool_verify_code_file,
    tool_search_codebase,
    clean_conversational_filler,
    AVAILABLE_TOOLS,
)
from k_cli.core.llm_driver import LLMDriver

def test_tool_list_dir(tmp_path):
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "world.txt").write_text("world", encoding="utf-8")
    
    out = tool_list_dir(str(tmp_path))
    assert "hello.py" in out
    assert "world.txt" in out

def test_tool_write_and_read_workspace_file(tmp_path):
    fpath = str(tmp_path / "test_file.py")
    res = tool_write_workspace_file(fpath, "def add(a, b):\n    return a + b\n")
    assert "Successfully wrote" in res
    assert "py_compile verified" in res
    
    read_out = tool_read_workspace_file(fpath)
    assert "def add(a, b):" in read_out
    assert "1 |" in read_out

def test_tool_edit_workspace_file(tmp_path):
    fpath = str(tmp_path / "mod.py")
    tool_write_workspace_file(fpath, "x = 10\n")
    res = tool_edit_workspace_file(fpath, "x = 10", "x = 20")
    assert "Successfully updated" in res
    
    content = Path(fpath).read_text(encoding="utf-8")
    assert "x = 20" in content

def test_tool_execute_command():
    res = tool_execute_command("echo 'K-CLI Agentic Test'")
    assert "K-CLI Agentic Test" in res
    assert "exit code: 0" in res

def test_tool_verify_code_file(tmp_path):
    fpath = str(tmp_path / "code.py")
    tool_write_workspace_file(fpath, "def foo(): pass")
    res = tool_verify_code_file(fpath)
    assert "Success=True" in res

def test_autonomous_agent_mock_run(tmp_path):
    driver = LLMDriver(mock_mode=True)
    agent = AutonomousAgent(driver=driver, cwd=str(tmp_path))
    res = agent.run("build a quick function in python")
    assert res.success is True
    assert res.final_response is not None


def test_clean_conversational_filler():
    immature_text = (
        "Okay, I now have a clear picture of the /home/k/K-Cli-for-Devs directory. "
        "Based on the file structure, this project appears to be a highly sophisticated and ambitious "
        "AI-powered command-line interface for developers. Here's why I find it impressive: "
        "Comprehensive AI Features (k_cli/agents, k_cli/tools, incident_triage, security_healer), "
        "Deep Git Integration (conflict_resolver, verifier), Rich User Interface (Textual TUI, Web UI), "
        "and Robust Testing Infrastructure (tests/)..."
    )
    cleaned = clean_conversational_filler(immature_text)
    assert not cleaned.startswith("Okay, I now have a clear picture")
    assert not cleaned.startswith("Based on the file structure")
    assert not cleaned.startswith("Here's why I find it impressive")
    assert "Comprehensive AI Features" in cleaned

