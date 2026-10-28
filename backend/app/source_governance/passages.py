"""Bounded complete originals or explicitly reviewed, self-contained passages."""

from typing import Any

from backend.app.cloud_ai.answer_contract import answer_texts
from backend.app.domain.enums import SourceType
from backend.app.domain.sources import SourceReference


def complete_source_text(source: Any) -> str:
    if isinstance(source, SourceReference) and source.source_type in {
        SourceType.official, SourceType.curated_guide,
    }:
        complete = "\n\n".join(answer_texts(source))
        # Local composition has one fact/citation per source. Withhold a set
        # that cannot fit intact; never silently clip its later restrictions.
        return complete if len(complete) <= 2400 else ""
    content = str(getattr(source, "content", "") or "")
    return content if len(content) <= 2400 else ""
