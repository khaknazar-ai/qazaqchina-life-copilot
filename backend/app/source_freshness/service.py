import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from backend.app.source_candidates.models import SourceCandidate
from backend.app.source_freshness.models import (
    SourceFreshnessAssessment,
    SourceFreshnessReport,
)
from backend.app.source_freshness.policies import (
    assess_source_freshness,
    freshness_warning_for_answer,
)
from backend.app.source_registry.registry import SourceRegistry


class SourceFreshnessService:
    def assess_sources(
        self,
        sources: list[Any],
        scenario: str | None = None,
        risk_level: str | None = None,
        domain: str | None = None,
    ) -> SourceFreshnessReport:
        assessments = [
            assess_source_freshness(
                source,
                scenario=scenario,
                risk_level=risk_level,
                domain=domain,
            )
            for source in sources
        ]
        warnings = [
            warning
            for assessment in assessments
            if (warning := freshness_warning_for_answer(assessment))
        ]
        return SourceFreshnessReport(
            total_sources=len(assessments),
            fresh_count=sum(1 for item in assessments if item.status == "fresh"),
            unknown_count=sum(1 for item in assessments if item.status == "unknown"),
            stale_count=sum(1 for item in assessments if item.status == "stale"),
            deprecated_count=sum(1 for item in assessments if item.status == "deprecated"),
            needs_refresh_count=sum(1 for item in assessments if item.needs_refresh),
            assessments=assessments,
            warnings=list(dict.fromkeys(warnings)),
        )

    def assess_registry(
        self,
        source_registry: SourceRegistry | None = None,
        scenario: str | None = None,
        risk_level: str | None = None,
        domain: str | None = None,
    ) -> SourceFreshnessReport:
        registry = source_registry or SourceRegistry.from_data_dir(Path("data/sources"))
        return self.assess_sources(
            registry.all_sources(),
            scenario=scenario,
            risk_level=risk_level,
            domain=domain,
        )

    def create_refresh_candidates(
        self,
        report: SourceFreshnessReport,
        sources: list[Any],
    ) -> list[SourceCandidate]:
        source_map = {
            str(getattr(_source_reference(source), "source_id", "unknown")): source
            for source in sources
        }
        candidates: list[SourceCandidate] = []
        for assessment in report.assessments:
            if not _should_create_refresh_candidate(assessment):
                continue
            source = source_map.get(assessment.source_id)
            candidates.append(_refresh_candidate_from_assessment(assessment, source))
        return candidates


def freshness_report_to_jsonable(report: SourceFreshnessReport) -> dict:
    return report.model_dump(mode="json")


def freshness_report_to_markdown(report: SourceFreshnessReport) -> str:
    lines = [
        "# Source Freshness Report",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Total sources: {report.total_sources}",
        f"- Fresh: {report.fresh_count}",
        f"- Unknown: {report.unknown_count}",
        f"- Stale: {report.stale_count}",
        f"- Deprecated: {report.deprecated_count}",
        f"- Needs refresh: {report.needs_refresh_count}",
        "",
        "## Warnings",
    ]
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- None")
    lines.extend(["", "## Assessments"])
    if not report.assessments:
        lines.append("- None")
    for assessment in report.assessments:
        lines.append(
            "- "
            f"{assessment.source_id}: {assessment.status}"
            f" (age={assessment.age_days if assessment.age_days is not None else 'unknown'}, "
            f"max={assessment.max_age_days if assessment.max_age_days is not None else 'none'}, "
            f"needs_refresh={assessment.needs_refresh})"
        )
        if assessment.recommended_action:
            lines.append(f"  - Recommended action: {assessment.recommended_action}")
        for warning in assessment.warnings:
            lines.append(f"  - Warning: {warning}")
    return "\n".join(lines) + "\n"


def write_refresh_candidates_json(
    candidates: list[SourceCandidate],
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [candidate.model_dump(mode="json") for candidate in candidates],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _should_create_refresh_candidate(assessment: SourceFreshnessAssessment) -> bool:
    return assessment.status in {"unknown", "stale", "deprecated", "needs_refresh"} or bool(
        assessment.needs_refresh
    )


def _refresh_candidate_from_assessment(
    assessment: SourceFreshnessAssessment,
    source: Any,
) -> SourceCandidate:
    source_reference = _source_reference(source)
    url = str(getattr(source_reference, "url", "") or f"source-refresh://{assessment.source_id}")
    title = assessment.title or str(getattr(source_reference, "title", "Source refresh needed"))
    snippet = _snippet(source_reference, assessment)
    source_type = assessment.source_type
    trust_level = assessment.trust_level
    candidate_key = f"{assessment.source_id}|{url}|{assessment.status}".encode()
    candidate_id = f"SRC-REFRESH-{sha256(candidate_key).hexdigest()[:12].upper()}"
    warnings = [
        f"Refresh proposal for source {assessment.source_id}.",
        f"freshness_status={assessment.status}",
        "Refresh candidates are pending and are not trusted sources.",
    ]
    warnings.extend(assessment.warnings)
    return SourceCandidate(
        candidate_id=candidate_id,
        title=f"Refresh needed: {title}",
        url=url,
        snippet=snippet,
        domain=_domain_from_url(url),
        source_type_guess=source_type,
        trust_guess=trust_level,
        language=_enum_value(getattr(source_reference, "language", None)),
        city=getattr(source_reference, "city", None),
        scenario=_enum_value(getattr(source_reference, "scenario", None)),
        risk_level=None,
        official_domain_hint=source_type == "official",
        requires_review=True,
        status="pending",
        warnings=list(dict.fromkeys(warnings)),
        discovered_by="source_freshness_refresh_workflow",
        allow_retrieval=False,
        freshness_note=assessment.recommended_action,
    )


def _snippet(source_reference: Any, assessment: SourceFreshnessAssessment) -> str:
    content = str(
        getattr(source_reference, "content", "")
        or assessment.recommended_action
        or "Source needs freshness review before future trusted use."
    )
    return " ".join(content.split())[:500]


def _domain_from_url(url: str) -> str | None:
    if "://" not in url:
        return None
    rest = url.split("://", 1)[1]
    return rest.split("/", 1)[0] or None


def _source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
