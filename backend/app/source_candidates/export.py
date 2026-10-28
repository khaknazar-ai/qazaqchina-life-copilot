import json
from pathlib import Path

from backend.app.source_candidates.models import RegistryReadySource, SourceCandidate
from backend.app.source_candidates.policies import candidate_can_be_retrievable


def candidate_to_registry_ready_source(candidate: SourceCandidate) -> RegistryReadySource:
    if not candidate_can_be_retrievable(candidate):
        raise ValueError("Only approved retrievable source candidates can be exported.")
    if not candidate.assigned_source_type or not candidate.assigned_trust_level:
        raise ValueError("Registry-ready export requires assigned source type and trust level.")
    return RegistryReadySource(
        candidate_id=candidate.candidate_id,
        title=candidate.title,
        url=candidate.url,
        source_type=candidate.assigned_source_type,
        trust_level=candidate.assigned_trust_level,
        language=candidate.language,
        country=candidate.country,
        city=candidate.city,
        allow_retrieval=candidate.allow_retrieval,
        freshness_note=candidate.freshness_note,
        excerpt=candidate.snippet,
        warnings=list(candidate.warnings),
    )


def registry_ready_to_jsonl_line(source: RegistryReadySource) -> str:
    return json.dumps(
        source.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
    )


def write_registry_ready_sources(
    sources: list[RegistryReadySource],
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [registry_ready_to_jsonl_line(source) for source in sources]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path
