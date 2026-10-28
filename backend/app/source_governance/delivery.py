"""Recheck current publication and city scope before any chat answer is stored."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from backend.app.answer_quality.composer import (
    compose_grounded_answer,
    render_grounded_answer_markdown,
)
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.answer_quality.models import GroundedAnswerDraft
from backend.app.domain.sources import is_retrievable_source
from backend.app.embeddings.safety import source_city_applies
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.source_conflicts.delivery import response_source_ids
from backend.app.source_conflicts.registry import full_registry_sources
from backend.app.source_registry.registry import SourceRegistry


def registry_digests(registry: SourceRegistry | None) -> dict[str, str]:
    if registry is None:
        return {}
    return {
        source.source_id: hashlib.sha256(json.dumps(
            source.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        for source in full_registry_sources(registry)
    }


def apply_source_delivery_gate(
    request: ChatRequest,
    response: ChatResponse,
    registry: SourceRegistry | None,
    *,
    initial_digests: dict[str, str],
    registry_snapshot: Callable[[], SourceRegistry] | None = None,
    city: str | None = None,
) -> None:
    ids = response_source_ids(response)
    # Reviewed notes can depend on governing originals that are not quoted facts.
    # They obey the same publication snapshot without rewriting valid notes.
    ids = list(dict.fromkeys([
        *ids,
        *(sid for field in ("grounded_facts", "recommended_steps")
          for section in (response.grounded_answer or {}).get(field, [])
          for sid in section.get("source_ids", [])),
        *(sid for note in (response.grounded_answer or {}).get("reviewed_notes", [])
          for sid in note.get("source_ids", [])),
        *(sid for note in (response.grounded_answer or {}).get("reviewed_notes", [])
          for sid in note.get("snapshot_refs", {})),
    ]))
    if not ids:
        response.metadata["source_publication_gate"] = {"status": "no_sourced_claims"}
        return
    if registry is None and registry_snapshot is None:
        # Standalone offline services load the same local catalog as their graph.
        from pathlib import Path

        registry = SourceRegistry.from_data_dir(Path("data/sources"))
        initial_digests = registry_digests(registry)
    unavailable = False
    invalid = []
    try:
        current = registry_snapshot() if registry_snapshot else registry
        if not isinstance(current, SourceRegistry):
            raise TypeError("Invalid source snapshot")
        sources = full_registry_sources(current)
        by_id = {source.source_id: source for source in sources}
        if len(by_id) != len(sources):
            raise ValueError("Ambiguous source identity")
        current_digests = registry_digests(current)
        now = datetime.now(UTC)
        invalid = [
            sid for sid in ids
            if sid not in by_id
            or initial_digests.get(sid) != current_digests.get(sid)
            or not is_retrievable_source(by_id[sid])
            or (city is not None and not source_city_applies(by_id[sid], city))
            or (by_id[sid].expires_at is not None and now >= (
                by_id[sid].expires_at.replace(tzinfo=UTC)
                if by_id[sid].expires_at.tzinfo is None else by_id[sid].expires_at
            ))
        ]
    except Exception:
        # Storage failures must neither deliver stale facts nor expose source text.
        unavailable = True
    if not unavailable and not invalid:
        response.metadata["source_publication_gate"] = {
            "status": "passed", "checked_source_count": len(ids),
        }
        return

    safe = compose_grounded_answer(
        request.user_message, [], scenario=response.scenario.value,
        risk_level=response.risk_level.value, language=request.preferred_language.value,
    )
    try:
        previous = (
            GroundedAnswerDraft.model_validate(response.grounded_answer)
            if response.grounded_answer else safe
        )
    except (ValueError, TypeError):
        previous = safe
    # Keep existing governing safety warnings; remove all source-dependent facts,
    # actions and reviewed notes together instead of deleting just citations.
    safe.warnings = list(dict.fromkeys([*previous.warnings, *safe.warnings]))
    safe.uncertainty = list(dict.fromkeys([*previous.uncertainty, *safe.uncertainty]))
    safe.escalation = list(dict.fromkeys([*previous.escalation, *safe.escalation]))
    response.grounded_answer = safe.model_dump(mode="json")
    response.answer = render_grounded_answer_markdown(safe)
    response.answer_quality_report = build_answer_quality_report(safe).model_dump(mode="json")
    response.citations = []
    response.escalation_required = True
    response.escalation_recommended = True
    response.requires_human_escalation = True
    response.safety_flags = list(dict.fromkeys([
        *response.safety_flags, "source_publication_changed", "unverified_answer_withheld",
    ]))
    response.metadata["source_publication_gate"] = {
        "status": "snapshot_unavailable" if unavailable else "source_changed_or_inapplicable",
        "checked_source_count": len(ids), "claims_withheld": True,
    }
    response.metadata.update(
        hybrid_rag_evidence_count=0, official_count=0, curated_count=0,
        community_count=0, has_official_or_curated=False,
    )
    response.answer_verification_report = {
        "passed": False, "scope": "final_source_publication_and_applicability",
        "claims_withheld": True, "original_answer_withheld": True,
    }
