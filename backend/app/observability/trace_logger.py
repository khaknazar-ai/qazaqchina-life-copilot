from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.privacy.values import redact_private_value


class TraceEvent(BaseModel):
    event_type: str
    trace_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class LocalJSONLTraceLogger:
    def __init__(self, trace_dir: str | Path, file_name: str = "traces.jsonl") -> None:
        self.trace_dir = Path(trace_dir)
        self.file_path = self.trace_dir / file_name

    def log(self, event: TraceEvent) -> Path:
        event = event.model_copy(update={"payload": redact_sensitive_payload(event.payload)})
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(event.model_dump_json() + "\n")
        return self.file_path


def read_trace_events(
    trace_dir: str | Path,
    file_name: str = "traces.jsonl",
) -> list[TraceEvent]:
    file_path = Path(trace_dir) / file_name
    if not file_path.exists():
        return []

    events: list[TraceEvent] = []
    with file_path.open(encoding="utf-8") as trace_file:
        for line_number, line in enumerate(trace_file, start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            try:
                events.append(TraceEvent.model_validate_json(raw_line))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid trace event in {file_path} at line {line_number}: {exc}"
                ) from exc
    return events


def redact_sensitive_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_private_value(payload, preserve_references=True)
