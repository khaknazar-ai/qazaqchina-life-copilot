"""Apply retrieval eligibility before text can leave the process."""

from datetime import UTC, datetime

from backend.app.agent.classification import has_active_prompt_injection, requests_document_forgery
from backend.app.answer_quality.policies import is_synthetic_source
from backend.app.domain.enums import SourceType, TrustLevel
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.embeddings.cloud_http import RetrievalProviderError
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.source_conflicts.models import canonical_scope
from backend.app.source_freshness.policies import assess_source_freshness

_CANONICAL_TRUST = {
    SourceType.official: TrustLevel.level_1_official,
    SourceType.curated_guide: TrustLevel.level_2_curated,
    SourceType.verified_institutional_contributor: TrustLevel.level_3_verified_institutional,
    SourceType.verified_experienced_contributor: TrustLevel.level_4_verified_experienced,
    SourceType.ordinary_community: TrustLevel.level_5_ordinary_community,
}


def safe_external_text(text: str, *, max_chars: int = 6000) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > max_chars:
        raise RetrievalProviderError("retrieval_input_invalid")
    if has_active_prompt_injection(text) or requests_document_forgery(text):
        raise RetrievalProviderError("retrieval_input_unsafe")
    sanitized, _ = redact_sensitive_text(text)
    return sanitized


def eligible_cloud_source(
    source: SourceReference,
    *,
    scenario: str | None = None,
    risk_level: str | None = None,
    domain: str | None = None,
    city: str | None = None,
    enforce_city_scope: bool = False,
) -> bool:
    body = source.content or ""
    if (
        not is_retrievable_source(source)
        or _CANONICAL_TRUST.get(source.source_type) != source.trust_level
        or not body.strip()
        or len(body) > 160_000
        or is_synthetic_source(source)
        or has_active_prompt_injection(body)
        or requests_document_forgery(body)
        or (enforce_city_scope and not source_city_applies(source, city))
    ):
        return False
    # Public contact details are also removed before embedding. The original body
    # remains in the registry for citations; privacy filtering never edits it.
    if source.source_type in {SourceType.official, SourceType.curated_guide}:
        reviewed = source.last_reviewed_at or source.reviewed_at
        if not reviewed or not (source.reviewed_by or "").strip():
            return False
        if reviewed.tzinfo is None:
            reviewed = reviewed.replace(tzinfo=UTC)
        if reviewed > datetime.now(UTC):
            return False
    freshness = assess_source_freshness(
        source,
        scenario=scenario,
        risk_level=risk_level,
        domain=domain,
    )
    return freshness.status == "fresh" and not freshness.needs_refresh


def source_city_applies(source: SourceReference, city: str | None) -> bool:
    scoped_city = canonical_scope("city", source.city or "")
    if scoped_city in {
        "",
        "china",
        "mainland china",
        "中国",
        "中国大陆",
        "китай",
        "қытай",
        "全国",
        "national",
    }:
        return True
    requested_city = canonical_scope("city", city or "")
    return bool(requested_city) and requested_city == scoped_city
