from pydantic import BaseModel

from backend.app.observability.trace_logger import TraceEvent


class TraceListResponse(BaseModel):
    events: list[TraceEvent]
