from pathlib import Path
from uuid import uuid4

from backend.app.observability.trace_logger import (
    LocalJSONLTraceLogger,
    TraceEvent,
    read_trace_events,
    redact_sensitive_payload,
)


class TraceService:
    def __init__(self, trace_dir: str | Path = ".traces") -> None:
        self.trace_dir = Path(trace_dir)
        self.logger = LocalJSONLTraceLogger(self.trace_dir)

    def log_event(
        self,
        event_type: str,
        trace_id: str | None,
        payload: dict,
    ) -> TraceEvent:
        event = TraceEvent(
            event_type=event_type,
            trace_id=trace_id or self.generate_trace_id(),
            payload=redact_sensitive_payload(payload),
        )
        self.logger.log(event)
        return event

    def log_service_start(
        self,
        service_name: str,
        trace_id: str,
        payload: dict,
    ) -> TraceEvent:
        return self.log_event(
            event_type="service.start",
            trace_id=trace_id,
            payload={
                "service_name": service_name,
                "status": "started",
                **payload,
            },
        )

    def log_service_end(
        self,
        service_name: str,
        trace_id: str,
        payload: dict,
    ) -> TraceEvent:
        return self.log_event(
            event_type="service.end",
            trace_id=trace_id,
            payload={
                "service_name": service_name,
                "status": "completed",
                **payload,
            },
        )

    def read_events(self) -> list[TraceEvent]:
        return read_trace_events(self.trace_dir)

    @staticmethod
    def generate_trace_id() -> str:
        return str(uuid4())
