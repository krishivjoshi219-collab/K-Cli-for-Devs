"""Persistent command telemetry for observability and hackathon demos."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TelemetrySummary:
    total_events: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p95_duration_ms: float
    events_last_24h: int
    top_commands: List[Dict[str, Any]]
    top_models: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_events": self.total_events,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": self.avg_duration_ms,
            "p95_duration_ms": self.p95_duration_ms,
            "events_last_24h": self.events_last_24h,
            "top_commands": self.top_commands,
            "top_models": self.top_models,
        }


class TelemetryStore:
    """Appends and summarizes command telemetry records."""

    def __init__(self, workspace_dir: str | Path = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.data_dir = self.workspace_dir / ".kcli"
        self.events_file = self.data_dir / "telemetry_events.jsonl"

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def record_event(
        self,
        command: str,
        success: bool,
        duration_ms: Optional[float] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure_dir()
        event: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "command": command,
            "success": bool(success),
            "duration_ms": float(duration_ms) if duration_ms is not None else None,
            "provider": provider,
            "model": model,
            "metadata": metadata or {},
        }
        with self.events_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def _read_events(self, limit: int = 5000) -> List[Dict[str, Any]]:
        if not self.events_file.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.events_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        if limit > 0:
            return rows[-limit:]
        return rows

    def summarize(self, limit: int = 5000, top_n: int = 5) -> TelemetrySummary:
        events = self._read_events(limit=limit)
        total = len(events)
        success_count = sum(1 for e in events if bool(e.get("success")))
        failure_count = total - success_count

        durations = sorted(
            float(e["duration_ms"])
            for e in events
            if isinstance(e.get("duration_ms"), (int, float))
        )
        avg_duration = (sum(durations) / len(durations)) if durations else 0.0
        if durations:
            p95_index = min(len(durations) - 1, int(round(0.95 * (len(durations) - 1))))
            p95_duration = durations[p95_index]
        else:
            p95_duration = 0.0

        cmd_counts = Counter(str(e.get("command", "unknown")) for e in events)
        model_counts = Counter(str(e.get("model", "unknown")) for e in events if e.get("model"))
        top_commands = [{"command": cmd, "count": count} for cmd, count in cmd_counts.most_common(top_n)]
        top_models = [{"model": model, "count": count} for model, count in model_counts.most_common(top_n)]

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        events_last_24h = 0
        for e in events:
            ts = e.get("timestamp")
            if not isinstance(ts, str):
                continue
            try:
                tsv = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if tsv.tzinfo is None:
                tsv = tsv.replace(tzinfo=timezone.utc)
            if tsv >= cutoff:
                events_last_24h += 1

        return TelemetrySummary(
            total_events=total,
            success_count=success_count,
            failure_count=failure_count,
            avg_duration_ms=avg_duration,
            p95_duration_ms=p95_duration,
            events_last_24h=events_last_24h,
            top_commands=top_commands,
            top_models=top_models,
        )
