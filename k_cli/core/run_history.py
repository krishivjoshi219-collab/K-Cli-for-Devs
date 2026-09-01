"""Persistent run history storage and replay support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    timestamp: str
    prompt: str
    language: str
    model: str
    provider: Optional[str]
    success: bool
    attempts: int
    duration_ms: float
    output: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "language": self.language,
            "model": self.model,
            "provider": self.provider,
            "success": self.success,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "output": self.output,
        }


class RunHistoryStore:
    """Stores run records in workspace-local JSONL history."""

    def __init__(self, workspace_dir: str | Path = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.data_dir = self.workspace_dir / ".kcli"
        self.history_file = self.data_dir / "run_history.jsonl"

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def add_record(
        self,
        prompt: str,
        language: str,
        model: str,
        provider: Optional[str],
        success: bool,
        attempts: int,
        duration_ms: float,
        output: str,
    ) -> RunRecord:
        self._ensure_dir()
        record = RunRecord(
            run_id=uuid.uuid4().hex[:12],
            timestamp=_utc_now_iso(),
            prompt=prompt,
            language=language,
            model=model,
            provider=provider,
            success=bool(success),
            attempts=int(attempts),
            duration_ms=float(duration_ms),
            output=output,
        )
        with self.history_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return record

    def _read_records(self) -> List[RunRecord]:
        if not self.history_file.exists():
            return []
        records: List[RunRecord] = []
        for line in self.history_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            try:
                records.append(
                    RunRecord(
                        run_id=str(obj.get("run_id", "")),
                        timestamp=str(obj.get("timestamp", "")),
                        prompt=str(obj.get("prompt", "")),
                        language=str(obj.get("language", "python")),
                        model=str(obj.get("model", "")),
                        provider=obj.get("provider"),
                        success=bool(obj.get("success", False)),
                        attempts=int(obj.get("attempts", 1)),
                        duration_ms=float(obj.get("duration_ms", 0.0)),
                        output=str(obj.get("output", "")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return records

    def list_recent(self, limit: int = 20) -> List[RunRecord]:
        recs = self._read_records()
        if limit <= 0:
            return recs
        return recs[-limit:]

    def get_record(self, run_id: str) -> Optional[RunRecord]:
        for rec in reversed(self._read_records()):
            if rec.run_id == run_id:
                return rec
        return None
