from pathlib import Path
import pytest
from k_cli.tools.rules import MAX_RULE_BYTES, load_project_rules


def test_load_project_rules_is_bounded_and_labeled(tmp_path: Path):
    rules = tmp_path / ".kcli" / "rules.md"
    rules.parent.mkdir()
    rules.write_text("Use the existing test command.", encoding="utf-8")

    loaded = load_project_rules(tmp_path)

    assert "untrusted repository context" in loaded
    assert "Use the existing test command." in loaded


def test_rules_path_cannot_escape_workspace(tmp_path: Path):
    outside = tmp_path.parent / "rules.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="inside the workspace"):
        load_project_rules(tmp_path, outside)


def test_rules_size_is_limited(tmp_path: Path):
    rules = tmp_path / "rules.md"
    rules.write_bytes(b"x" * (MAX_RULE_BYTES + 1))

    with pytest.raises(ValueError, match="byte limit"):
        load_project_rules(tmp_path, rules)
