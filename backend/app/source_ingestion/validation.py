import re

from backend.app.source_candidates.models import RegistryReadySource
from backend.app.source_ingestion.models import (
    SourceIngestionRecord,
    SourceIngestionValidationIssue,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SOURCE_ID_MAX_SLUG_LENGTH = 48
_EXCERPT_WARNING_LENGTH = 1200

_OFFICIAL_SOURCE_TYPES = {"official"}
_CURATED_SOURCE_TYPES = {"curated_guide"}
_COMMUNITY_SOURCE_TYPES = {
    "ordinary_community",
    "verified_experienced_contributor",
    "verified_institutional_contributor",
}
_OFFICIAL_TRUST_LEVELS = {"level_1_official"}
_CURATED_TRUST_LEVELS = {"level_2_curated"}
_COMMUNITY_TRUST_LEVELS = {
    "level_3_verified_institutional",
    "level_4_verified_experienced",
    "level_5_ordinary_community",
}
_HIGH_RISK_TERMS = (
    "passport",
    "visa",
    "overstay",
    "registration",
    "police",
    "psb",
    "public security",
    "work",
    "permit",
    "contract",
    "document",
    "government",
    "embassy",
    "consulate",
)


def normalize_source_id(title: str, candidate_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    if not slug:
        slug = "source"
    slug = slug[:_SOURCE_ID_MAX_SLUG_LENGTH].strip("-") or "source"
    suffix = re.sub(r"[^a-z0-9]+", "-", candidate_id.casefold()).strip("-")
    suffix_parts = [part for part in suffix.split("-") if part]
    stable_suffix = "-".join(suffix_parts[-2:]) if suffix_parts else "candidate"
    return f"src-{slug}-{stable_suffix}"


def registry_ready_to_ingestion_record(
    source: RegistryReadySource,
) -> SourceIngestionRecord:
    return SourceIngestionRecord(
        candidate_id=source.candidate_id,
        source_id=normalize_source_id(source.title, source.candidate_id),
        title=source.title,
        url=source.url,
        source_type=source.source_type,
        trust_level=source.trust_level,
        language=source.language,
        country=source.country,
        city=source.city,
        excerpt=source.excerpt,
        allow_retrieval=source.allow_retrieval,
        freshness_note=source.freshness_note,
        warnings=list(source.warnings),
    )


def validate_ingestion_record(
    record: SourceIngestionRecord,
) -> list[SourceIngestionValidationIssue]:
    issues: list[SourceIngestionValidationIssue] = []

    for field_name in ["title", "url", "source_type", "trust_level", "excerpt"]:
        if not str(getattr(record, field_name) or "").strip():
            issues.append(
                _issue(
                    "error",
                    f"missing_{field_name}",
                    f"{field_name} is required.",
                    record.candidate_id,
                )
            )

    if record.url and not record.url.startswith(("http://", "https://")):
        issues.append(
            _issue(
                "error",
                "invalid_url",
                "url must start with http:// or https://.",
                record.candidate_id,
            )
        )

    if not record.allow_retrieval:
        issues.append(
            _issue(
                "error",
                "retrieval_not_allowed",
                "allow_retrieval must be true for ingestion records.",
                record.candidate_id,
            )
        )

    if record.source_type in _OFFICIAL_SOURCE_TYPES and (
        record.trust_level not in _OFFICIAL_TRUST_LEVELS
    ):
        issues.append(
            _issue(
                "error",
                "official_trust_mismatch",
                "official source_type must use level_1_official trust level.",
                record.candidate_id,
            )
        )

    if record.source_type in _CURATED_SOURCE_TYPES and (
        record.trust_level not in _CURATED_TRUST_LEVELS
    ):
        issues.append(
            _issue(
                "error",
                "curated_trust_mismatch",
                "curated_guide source_type must use level_2_curated trust level.",
                record.candidate_id,
            )
        )

    if record.source_type in _COMMUNITY_SOURCE_TYPES and record.trust_level in (
        _OFFICIAL_TRUST_LEVELS | _CURATED_TRUST_LEVELS
    ):
        issues.append(
            _issue(
                "error",
                "community_trust_mismatch",
                "community source_type must not use official or curated trust level.",
                record.candidate_id,
            )
        )

    if not _SLUG_PATTERN.fullmatch(record.source_id):
        issues.append(
            _issue(
                "error",
                "invalid_source_id",
                "source_id must be stable and slug-like.",
                record.candidate_id,
            )
        )

    if len(record.excerpt) > _EXCERPT_WARNING_LENGTH:
        issues.append(
            _issue(
                "warning",
                "excerpt_too_long",
                "excerpt is long; shorten before manual registry insertion.",
                record.candidate_id,
            )
        )

    if _freshness_note_recommended(record) and not (record.freshness_note or "").strip():
        issues.append(
            _issue(
                "warning",
                "freshness_note_recommended",
                "freshness_note is recommended for high-risk official-style sources.",
                record.candidate_id,
            )
        )

    return issues


def validate_ingestion_records(
    records: list[SourceIngestionRecord],
) -> list[SourceIngestionValidationIssue]:
    issues: list[SourceIngestionValidationIssue] = []
    for record in records:
        issues.extend(validate_ingestion_record(record))
    issues.extend(detect_duplicate_source_ids(records))
    issues.extend(detect_duplicate_urls(records))
    return issues


def detect_duplicate_source_ids(
    records: list[SourceIngestionRecord],
) -> list[SourceIngestionValidationIssue]:
    seen: dict[str, SourceIngestionRecord] = {}
    issues: list[SourceIngestionValidationIssue] = []
    for record in records:
        if record.source_id in seen:
            issues.append(
                _issue(
                    "error",
                    "duplicate_source_id",
                    f"duplicate source_id: {record.source_id}",
                    record.candidate_id,
                )
            )
            continue
        seen[record.source_id] = record
    return issues


def detect_duplicate_urls(
    records: list[SourceIngestionRecord],
) -> list[SourceIngestionValidationIssue]:
    seen: dict[str, SourceIngestionRecord] = {}
    issues: list[SourceIngestionValidationIssue] = []
    for record in records:
        normalized_url = record.url.strip().casefold()
        if normalized_url in seen:
            issues.append(
                _issue(
                    "error",
                    "duplicate_url",
                    f"duplicate url: {record.url}",
                    record.candidate_id,
                )
            )
            continue
        seen[normalized_url] = record
    return issues


def _freshness_note_recommended(record: SourceIngestionRecord) -> bool:
    if record.source_type not in (_OFFICIAL_SOURCE_TYPES | _CURATED_SOURCE_TYPES):
        return False
    searchable = " ".join([record.title, record.url, record.excerpt]).casefold()
    return any(term in searchable for term in _HIGH_RISK_TERMS)


def _issue(
    severity: str,
    code: str,
    message: str,
    candidate_id: str | None = None,
) -> SourceIngestionValidationIssue:
    return SourceIngestionValidationIssue(
        severity=severity,
        code=code,
        message=message,
        candidate_id=candidate_id,
    )
