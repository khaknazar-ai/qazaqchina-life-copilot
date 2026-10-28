from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.app.api.dependencies import get_trace_service
from backend.app.main import app
from backend.app.services.trace_service import TraceService


@pytest.fixture(autouse=True)
def override_trace_service(tmp_path: Path) -> Iterator[Path]:
    trace_dir = tmp_path / "traces"

    def get_test_trace_service() -> TraceService:
        return TraceService(trace_dir=trace_dir)

    app.dependency_overrides[get_trace_service] = get_test_trace_service
    yield trace_dir
    app.dependency_overrides.pop(get_trace_service, None)
