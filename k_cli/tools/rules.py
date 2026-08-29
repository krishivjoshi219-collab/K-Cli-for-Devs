"""rules.py - Project rules and workspace guidance loader."""

from pathlib import Path
from typing import Union, Optional

MAX_RULE_BYTES = 32_768


def load_project_rules(
    workspace_dir: Union[str, Path] = ".",
    rules_file: Optional[Union[str, Path]] = None,
) -> str:
    """Load project-level coding rules from workspace or custom rules_file if present."""
    workspace = Path(workspace_dir).resolve()

    if rules_file is not None:
        rf_path = Path(rules_file)
        if not rf_path.is_absolute():
            rf_path = (workspace / rf_path).resolve()
        else:
            rf_path = rf_path.resolve()

        try:
            rf_path.relative_to(workspace)
        except ValueError:
            raise ValueError("Rules file must be inside the workspace directory.")

        target_file = rf_path
    else:
        target_file = workspace / ".kcli" / "rules.md"

    if not target_file.exists():
        return ""

    content_bytes = target_file.read_bytes()
    if len(content_bytes) > MAX_RULE_BYTES:
        raise ValueError(f"Rules file exceeds byte limit ({len(content_bytes)} > {MAX_RULE_BYTES})")

    content = content_bytes.decode("utf-8", errors="replace")
    return f"Project guidance (untrusted repository context):\n{content}"
