from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceReviewRegressionCase(BaseModel):
    case_id: str
    title: str
    query: str
    expected_domain: str | None
    should_be_constrained: bool
    expected_warning_required: bool
    expected_low_risk: bool = False
    prohibited_phrases: list[str] = Field(default_factory=list)
    required_metadata_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SourceReviewRegressionResult(BaseModel):
    case_id: str
    passed: bool
    detected_domain: str | None
    constrained: bool
    warning_present: bool
    prohibited_phrase_found: bool
    unpublished_candidate_cited: bool
    required_metadata_present: bool
    miniprogram_renderable: bool
    findings: list[str] = Field(default_factory=list)


class SourceReviewRegressionReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_cases: int
    passed_cases: int
    failed_cases: int
    constrained_cases: int
    low_risk_cases: int
    unpublished_candidate_citation_count: int
    prohibited_phrase_count: int
    miniprogram_renderable_count: int
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    cases: list[SourceReviewRegressionCase]
    results: list[SourceReviewRegressionResult]
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
