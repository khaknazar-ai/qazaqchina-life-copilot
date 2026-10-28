from datetime import UTC, date, datetime, time
from typing import Any

from backend.app.source_freshness.models import (
    SourceFreshnessAssessment,
    SourceFreshnessMetadata,
    SourceFreshnessPolicy,
)

HIGH_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}
HIGH_RISK_HINTS = {
    "passport",
    "visa",
    "overstay",
    "registration",
    "police",
    "work",
    "contract",
    "medical",
    "hospital",
    "emergency",
    "document",
}
DEPRECATED_OVERRIDES = {"deprecated", "retired", "do_not_use"}
NEEDS_REFRESH_OVERRIDES = {"needs_refresh", "refresh_required", "stale"}


def default_freshness_policy(
    source_type: str | None = None,
    trust_level: str | None = None,
) -> SourceFreshnessPolicy:
    normalized_type = _normalize(source_type)
    normalized_trust = _normalize(trust_level)
    if normalized_type == "official" or normalized_trust == "level_1_official":
        return SourceFreshnessPolicy(
            source_type=source_type,
            trust_level=trust_level,
            default_max_age_days=180,
            high_risk_max_age_days=90,
            require_reviewed_at=False,
            notes=["Official sources use stricter freshness windows in high-risk contexts."],
        )
    if normalized_type == "curated_guide" or normalized_trust == "level_2_curated":
        return SourceFreshnessPolicy(
            source_type=source_type,
            trust_level=trust_level,
            default_max_age_days=365,
            high_risk_max_age_days=180,
            require_reviewed_at=True,
            notes=["Curated guides should carry review metadata."],
        )
    if "community" in normalized_type or "contributor" in normalized_type:
        return SourceFreshnessPolicy(
            source_type=source_type,
            trust_level=trust_level,
            default_max_age_days=365,
            high_risk_max_age_days=180,
            require_reviewed_at=False,
            notes=["Community freshness never elevates community content to official evidence."],
        )
    return SourceFreshnessPolicy(
        source_type=source_type,
        trust_level=trust_level,
        default_max_age_days=365,
        high_risk_max_age_days=180,
        require_reviewed_at=False,
        notes=["Unknown source types use conservative default freshness windows."],
    )


def is_high_risk_freshness_context(
    scenario: str | None = None,
    risk_level: str | None = None,
    domain: str | None = None,
) -> bool:
    if _normalize(risk_level) in HIGH_RISK_LEVELS:
        return True
    combined = " ".join(value or "" for value in [scenario, domain]).casefold()
    return any(hint in combined for hint in HIGH_RISK_HINTS)


def infer_source_freshness_metadata(source: Any) -> SourceFreshnessMetadata:
    source_reference = _source_reference(source)
    source_id = str(getattr(source_reference, "source_id", "unknown"))
    reviewed_at = (
        _to_datetime(getattr(source_reference, "last_reviewed_at", None))
        or _to_datetime(getattr(source_reference, "reviewed_at", None))
        or _to_datetime(getattr(source_reference, "date_accessed", None))
    )
    collected_at = (
        _to_datetime(getattr(source_reference, "collected_at", None))
        or _to_datetime(getattr(source_reference, "date_accessed", None))
        or _to_datetime(getattr(source_reference, "date_published", None))
        or _to_datetime(getattr(source_reference, "created_at", None))
    )
    return SourceFreshnessMetadata(
        source_id=source_id,
        url=getattr(source_reference, "url", None),
        collected_at=collected_at,
        last_reviewed_at=reviewed_at,
        expires_at=_to_datetime(getattr(source_reference, "expires_at", None)),
        content_hash=getattr(source_reference, "content_hash", None),
        freshness_note=getattr(source_reference, "freshness_note", None),
        status_override=getattr(source_reference, "status_override", None),
    )


def calculate_source_age_days(
    metadata: SourceFreshnessMetadata,
    now: datetime | None = None,
) -> int | None:
    reference_time = metadata.last_reviewed_at or metadata.collected_at
    if reference_time is None:
        return None
    active_now = _aware_datetime(now or datetime.now(UTC))
    return max(0, (active_now - _aware_datetime(reference_time)).days)


def assess_source_freshness(
    source: Any,
    scenario: str | None = None,
    risk_level: str | None = None,
    domain: str | None = None,
    now: datetime | None = None,
) -> SourceFreshnessAssessment:
    source_reference = _source_reference(source)
    source_type = _enum_value(getattr(source_reference, "source_type", None))
    trust_level = _enum_value(getattr(source_reference, "trust_level", None))
    metadata = infer_source_freshness_metadata(source_reference)
    policy = default_freshness_policy(source_type, trust_level)
    high_risk = is_high_risk_freshness_context(scenario, risk_level, domain)
    max_age_days = (
        policy.high_risk_max_age_days if high_risk else policy.default_max_age_days
    )
    active_now = _aware_datetime(now or datetime.now(UTC))
    warnings: list[str] = []
    recommended_action: str | None = None

    status_override = _normalize(metadata.status_override)
    if status_override in DEPRECATED_OVERRIDES:
        return SourceFreshnessAssessment(
            source_id=metadata.source_id,
            title=getattr(source_reference, "title", None),
            source_type=source_type,
            trust_level=trust_level,
            status="deprecated",
            age_days=calculate_source_age_days(metadata, active_now),
            max_age_days=max_age_days,
            needs_refresh=True,
            high_risk_context=high_risk,
            warnings=["Source is marked deprecated and should not be used as current support."],
            recommended_action="Remove from retrieval or replace through reviewed ingestion.",
        )

    if status_override in NEEDS_REFRESH_OVERRIDES:
        warnings.append("Source freshness status override requires refresh.")
        recommended_action = "Create a refresh candidate and complete human review."
        return _assessment(
            source_reference=source_reference,
            metadata=metadata,
            source_type=source_type,
            trust_level=trust_level,
            status="needs_refresh",
            age_days=calculate_source_age_days(metadata, active_now),
            max_age_days=max_age_days,
            needs_refresh=True,
            high_risk=high_risk,
            warnings=warnings,
            recommended_action=recommended_action,
        )

    if metadata.expires_at and _aware_datetime(metadata.expires_at) < active_now:
        warnings.append("Source freshness expiry date has passed.")
        return _assessment(
            source_reference,
            metadata,
            source_type,
            trust_level,
            "stale",
            calculate_source_age_days(metadata, active_now),
            max_age_days,
            True,
            high_risk,
            warnings,
            "Refresh or re-review this source before relying on exact requirements.",
        )

    if policy.require_reviewed_at and metadata.last_reviewed_at is None:
        warnings.append("Source policy expects reviewed_at metadata, but none was found.")

    age_days = calculate_source_age_days(metadata, active_now)
    if age_days is None:
        warnings.append("Source has no collected, accessed, published, or reviewed date.")
        return _assessment(
            source_reference,
            metadata,
            source_type,
            trust_level,
            "unknown",
            None,
            max_age_days,
            high_risk,
            high_risk,
            warnings,
            "Add review metadata; create a refresh candidate for high-risk use.",
        )

    if max_age_days is not None and age_days > max_age_days:
        warnings.append(
            f"Source age is {age_days} days, above the {max_age_days}-day freshness window."
        )
        return _assessment(
            source_reference,
            metadata,
            source_type,
            trust_level,
            "stale",
            age_days,
            max_age_days,
            True,
            high_risk,
            warnings,
            "Re-check the source through a reviewed refresh workflow.",
        )

    if warnings:
        recommended_action = "Keep review metadata current before high-risk use."
    return _assessment(
        source_reference,
        metadata,
        source_type,
        trust_level,
        "fresh",
        age_days,
        max_age_days,
        False,
        high_risk,
        warnings,
        recommended_action,
    )


def freshness_warning_for_answer(
    assessment: SourceFreshnessAssessment,
) -> str | None:
    if assessment.status == "fresh" and not assessment.warnings:
        return None
    if assessment.status == "unknown":
        return (
            f"Freshness unknown for source {assessment.source_id}; verify current official "
            "details before relying on exact requirements."
        )
    if assessment.status == "deprecated":
        return (
            f"Source {assessment.source_id} is marked deprecated and should be refreshed "
            "or replaced before use."
        )
    if assessment.needs_refresh or assessment.status in {"stale", "needs_refresh"}:
        return (
            f"Source {assessment.source_id} may be stale and needs refresh; verify with "
            "current official or reviewed sources before acting."
        )
    if assessment.warnings:
        return f"Source {assessment.source_id} has freshness warning: {assessment.warnings[0]}"
    return None


def _assessment(
    source_reference: Any,
    metadata: SourceFreshnessMetadata,
    source_type: str | None,
    trust_level: str | None,
    status: str,
    age_days: int | None,
    max_age_days: int | None,
    needs_refresh: bool,
    high_risk: bool,
    warnings: list[str],
    recommended_action: str | None,
) -> SourceFreshnessAssessment:
    return SourceFreshnessAssessment(
        source_id=metadata.source_id,
        title=getattr(source_reference, "title", None),
        source_type=source_type,
        trust_level=trust_level,
        status=status,
        age_days=age_days,
        max_age_days=max_age_days,
        needs_refresh=needs_refresh,
        high_risk_context=high_risk,
        warnings=list(dict.fromkeys(warnings)),
        recommended_action=recommended_action,
    )


def _source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            normalized = value.replace("Z", "+00:00")
            return _aware_datetime(datetime.fromisoformat(normalized))
        except ValueError:
            return None
    return None


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _normalize(value: Any) -> str:
    return str(value or "").casefold()
