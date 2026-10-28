from typing import Any

from pydantic import BaseModel, Field

from backend.app.retrieval.planner import (
    CURATED_SOURCE,
    OFFICIAL_SOURCE,
    classify_retrieval_domain,
)

COMMUNITY_SOURCE_TYPES = {
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}

SENSITIVE_DOMAINS = {
    "passport_document_loss",
    "visa_overstay_registration",
    "work_contract_status",
    "medical_hospital",
    "emergency",
}

SENSITIVE_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
}


class RetrievalQualityInput(BaseModel):
    user_message: str
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    expected_source_types: list[str] = Field(default_factory=list)


class RetrievedSourceQuality(BaseModel):
    source_id: str
    title: str
    source_type: str | None = None
    trust_level: str | None = None
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RetrievalQualityReport(BaseModel):
    scenario: str | None
    domain: str
    query_count: int
    retrieved_count: int
    official_count: int
    curated_count: int
    community_count: int
    has_official_or_curated: bool
    has_required_source_type: bool
    warnings: list[str] = Field(default_factory=list)
    sources: list[RetrievedSourceQuality] = Field(default_factory=list)


def score_retrieved_source_quality(source: Any, plan: Any = None) -> RetrievedSourceQuality:
    source_reference = _extract_source_reference(source)
    source_type = _enum_value(getattr(source_reference, "source_type", None))
    trust_level = _enum_value(getattr(source_reference, "trust_level", None))
    base_score = float(getattr(source, "score", 0.0) or 0.0)
    reasons: list[str] = []
    warnings: list[str] = []
    quality_score = base_score

    if source_type == OFFICIAL_SOURCE:
        quality_score += 2.0
        reasons.append("official_source")
    elif source_type == CURATED_SOURCE:
        quality_score += 1.5
        reasons.append("curated_guide")
    elif source_type in COMMUNITY_SOURCE_TYPES:
        quality_score += 0.5
        reasons.append("community_practical_context")
        warnings.append("Community source can support practical context, not official claims.")
    else:
        warnings.append("Source type is missing or not recognized by retrieval hierarchy.")

    if _plan_requires_official(plan):
        if source_type in {OFFICIAL_SOURCE, CURATED_SOURCE}:
            reasons.append("matches_official_or_curated_need")
        elif source_type in COMMUNITY_SOURCE_TYPES:
            warnings.append("Official-required plan should not rely on community-only support.")

    return RetrievedSourceQuality(
        source_id=str(getattr(source_reference, "source_id", "unknown")),
        title=str(getattr(source_reference, "title", "Unknown source")),
        source_type=source_type,
        trust_level=trust_level,
        score=quality_score,
        reasons=reasons,
        warnings=warnings,
    )


def build_retrieval_quality_report(
    input: RetrievalQualityInput,
    retrieved_sources: list[Any],
    plan: Any = None,
) -> RetrievalQualityReport:
    domain = classify_retrieval_domain(input.user_message, input.scenario)
    source_reports = _dedupe_source_reports(
        [score_retrieved_source_quality(source, plan) for source in retrieved_sources]
    )
    official_count = sum(1 for source in source_reports if source.source_type == OFFICIAL_SOURCE)
    curated_count = sum(1 for source in source_reports if source.source_type == CURATED_SOURCE)
    community_count = sum(
        1 for source in source_reports if source.source_type in COMMUNITY_SOURCE_TYPES
    )
    has_official_or_curated = official_count + curated_count > 0
    required_source_types = _required_source_types(input.expected_source_types, plan)
    has_required_source_type = (
        True
        if not required_source_types
        else any(source.source_type in required_source_types for source in source_reports)
    )
    query_count = len(getattr(plan, "queries", []) or [])
    warnings = _report_warnings(
        input=input,
        domain=domain,
        retrieved_count=len(source_reports),
        has_official_or_curated=has_official_or_curated,
        has_required_source_type=has_required_source_type,
        plan=plan,
    )

    return RetrievalQualityReport(
        scenario=input.scenario,
        domain=domain,
        query_count=query_count,
        retrieved_count=len(source_reports),
        official_count=official_count,
        curated_count=curated_count,
        community_count=community_count,
        has_official_or_curated=has_official_or_curated,
        has_required_source_type=has_required_source_type,
        warnings=warnings,
        sources=source_reports,
    )


def report_to_markdown(report: RetrievalQualityReport) -> str:
    lines = [
        "# Retrieval Quality Report",
        "",
        f"- Scenario: {report.scenario or 'unspecified'}",
        f"- Domain: {report.domain}",
        f"- Query count: {report.query_count}",
        f"- Retrieved sources: {report.retrieved_count}",
        f"- Official sources: {report.official_count}",
        f"- Curated guides: {report.curated_count}",
        f"- Community sources: {report.community_count}",
        f"- Has official or curated: {report.has_official_or_curated}",
        f"- Has required source type: {report.has_required_source_type}",
        "",
        "## Warnings",
    ]
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- None")

    lines.extend(["", "## Sources"])
    if not report.sources:
        lines.append("- None")
    for source in report.sources:
        reasons = ", ".join(source.reasons) if source.reasons else "none"
        lines.append(
            f"- {source.source_id}: {source.title} "
            f"({source.source_type or 'unknown'}, score={source.score:.2f}, reasons={reasons})"
        )
        lines.extend(f"  - Warning: {warning}" for warning in source.warnings)

    return "\n".join(lines)


def quality_report_to_jsonable(report: RetrievalQualityReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def _report_warnings(
    input: RetrievalQualityInput,
    domain: str,
    retrieved_count: int,
    has_official_or_curated: bool,
    has_required_source_type: bool,
    plan: Any,
) -> list[str]:
    warnings: list[str] = []
    official_required = _plan_requires_official(plan) or _is_sensitive(input, domain)

    if retrieved_count == 0:
        warnings.append("No retrievable sources were selected for this query.")

    if official_required and not has_official_or_curated:
        warnings.append("High-risk or official-required retrieval lacks official/curated support.")

    if official_required and retrieved_count > 0 and not has_official_or_curated:
        warnings.append(
            "Community-only retrieval must not support legal, visa, work, medical, or "
            "passport claims."
        )

    if not has_required_source_type:
        warnings.append("Retrieved sources do not include the required source type.")

    return warnings


def _extract_source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _dedupe_source_reports(
    source_reports: list[RetrievedSourceQuality],
) -> list[RetrievedSourceQuality]:
    deduped: dict[str, RetrievedSourceQuality] = {}
    for source_report in source_reports:
        existing = deduped.get(source_report.source_id)
        if existing is None or source_report.score > existing.score:
            deduped[source_report.source_id] = source_report
    return list(deduped.values())


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _plan_requires_official(plan: Any) -> bool:
    source_policy = getattr(plan, "source_policy", None)
    return bool(getattr(source_policy, "require_official", False))


def _required_source_types(expected_source_types: list[str], plan: Any) -> list[str]:
    if expected_source_types:
        return expected_source_types
    return list(getattr(plan, "required_source_types", []) or [])


def _is_sensitive(input: RetrievalQualityInput, domain: str) -> bool:
    return (
        domain in SENSITIVE_DOMAINS
        or (input.risk_level or "").casefold() in SENSITIVE_RISK_LEVELS
    )
