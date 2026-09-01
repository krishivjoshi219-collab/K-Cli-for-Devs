"""Local plugin registry for extending K-CLI with external tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PluginSpec:
    name: str
    command: str
    description: str
    created_at: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "command": self.command,
            "description": self.description,
            "created_at": self.created_at,
        }


class PluginRegistry:
    """Stores lightweight plugin command definitions in JSON."""

    def __init__(self, workspace_dir: str | Path = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.data_dir = self.workspace_dir / ".kcli"
        self.registry_file = self.data_dir / "plugins.json"

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, str]]:
        if not self.registry_file.exists():
            return {}
        try:
            payload = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        normalized: Dict[str, Dict[str, str]] = {}
        for name, spec in payload.items():
            if not isinstance(name, str) or not isinstance(spec, dict):
                continue
            if "command" not in spec:
                continue
            normalized[name] = {
                "command": str(spec.get("command", "")),
                "description": str(spec.get("description", "")),
                "created_at": str(spec.get("created_at", _utc_now_iso())),
            }
        return normalized

    def _save(self, payload: Dict[str, Dict[str, str]]) -> None:
        self._ensure_dir()
        self.registry_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_plugins(self) -> List[PluginSpec]:
        payload = self._load()
        return [
            PluginSpec(name=name, command=spec["command"], description=spec["description"], created_at=spec["created_at"])
            for name, spec in sorted(payload.items(), key=lambda item: item[0].lower())
        ]

    def add_plugin(self, name: str, command: str, description: str = "") -> PluginSpec:
        payload = self._load()
        if not name.strip():
            raise ValueError("Plugin name cannot be empty.")
        if not command.strip():
            raise ValueError("Plugin command cannot be empty.")
        key = name.strip()
        spec = PluginSpec(name=key, command=command.strip(), description=description.strip(), created_at=_utc_now_iso())
        payload[key] = spec.to_dict()
        self._save(payload)
        return spec

    def remove_plugin(self, name: str) -> bool:
        payload = self._load()
        if name not in payload:
            return False
        del payload[name]
        self._save(payload)
        return True

    def get_plugin(self, name: str) -> Optional[PluginSpec]:
        payload = self._load()
        spec = payload.get(name)
        if not spec:
            return None
        return PluginSpec(name=name, command=spec["command"], description=spec["description"], created_at=spec["created_at"])
