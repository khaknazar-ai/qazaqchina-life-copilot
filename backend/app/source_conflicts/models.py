from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.checks import detect_prompt_injection

ConflictStatus = Literal["open", "proposed", "approved", "rejected", "revoked"]
ResolutionOutcome = Literal["prefer_source", "different_conditions", "unresolved"]
ScopeDimension = Literal[
    "nationality", "document", "activity", "city", "basis", "facility", "department", "contract"
]


def normalize_scope(value: str) -> str:
    return " ".join(value.strip().casefold().split())


_SCOPE_ALIASES = {
    "city": {
        "上海": "shanghai",
        "шанхай": "shanghai",
        "北京": "beijing",
        "пекин": "beijing",
        "广州": "guangzhou",
        "гуанчжоу": "guangzhou",
        "深圳": "shenzhen",
        "шэньчжэнь": "shenzhen",
        "成都": "chengdu",
        "чэнду": "chengdu",
        "杭州": "hangzhou",
        "ханчжоу": "hangzhou",
        "西安": "xi'an",
        "xian": "xi'an",
        "сиань": "xi'an",
        "乌鲁木齐": "urumqi",
        "урумчи": "urumqi",
    },
    "nationality": {
        "казахстан": "kazakhstan",
        "қазақстан": "kazakhstan",
        "哈萨克斯坦": "kazakhstan",
        "kazakhstani": "kazakhstan",
        "казахстанский": "kazakhstan",
        "kz": "kazakhstan",
        "中国": "china",
        "китай": "china",
        "қытай": "china",
        "cn": "china",
        "uk": "united kingdom",
        "british": "united kingdom",
        "英国": "united kingdom",
        "usa": "united states",
        "us": "united states",
        "美国": "united states",
    },
    "document": {
        "x1 visa": "x1",
        "x2 visa": "x2",
        "s1 visa": "s1",
        "s2 visa": "s2",
        "z visa": "z",
        "m visa": "m",
        "l visa": "l",
        "q1 visa": "q1",
        "q2 visa": "q2",
    },
}


def canonical_scope(dimension: str, value: str) -> str:
    normalized = normalize_scope(value)
    return _SCOPE_ALIASES.get(dimension, {}).get(normalized, normalized)


class ResolutionApplicability(BaseModel):
    """Explicit, non-sensitive case facts; unknown facts never match a condition."""

    model_config = ConfigDict(extra="forbid")

    nationality: str | None = Field(default=None, min_length=1, max_length=120)
    document: str | None = Field(default=None, min_length=1, max_length=120)
    activity: str | None = Field(default=None, min_length=1, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    basis: str | None = Field(default=None, min_length=1, max_length=120)
    facility: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    contract: str | None = Field(default=None, min_length=1, max_length=120)
    on_date: date | None = None

    @field_validator(
        "nationality", "document", "activity", "city", "basis", "facility", "department", "contract"
    )
    @classmethod
    def safe_fact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = normalize_scope(value)
        redacted, warnings = redact_sensitive_text(clean)
        if not clean or warnings or redacted != clean or detect_prompt_injection(clean):
            raise ValueError("Applicability must contain a non-sensitive explicit fact")
        return clean


class EvidenceCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=120)
    quotes: dict[str, str] = Field(min_length=1, max_length=20)

    @field_validator("value")
    @classmethod
    def explicit_value(cls, value: str) -> str:
        value = normalize_scope(value)
        if value in {"", "*", "any", "all", "unknown", "other", "otherwise"}:
            raise ValueError("Use an explicit applicability value, never a wildcard")
        return value


class ConditionalBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=1, max_length=20)
    conditions: dict[ScopeDimension, EvidenceCondition] = Field(default_factory=dict, max_length=8)
    valid_from: date | None = None
    valid_until: date | None = None
    date_quotes: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def valid_scope(self) -> "ConditionalBranch":
        if not self.conditions and self.valid_from is None and self.valid_until is None:
            raise ValueError("A branch needs explicit conditions or an effective date interval")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("The effective interval is reversed")
        return self


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceReference
    snapshot_id: str
    snapshot_hash: str


class ResolutionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=2000)
    outcome: ResolutionOutcome
    preferred_source_ids: list[str] = Field(default_factory=list, max_length=20)
    conditions: list[ConditionalBranch] = Field(default_factory=list, max_length=10)
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("valid_until must have a timezone")
        return value.astimezone(UTC)


class ConflictCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    revision: int = Field(ge=1)
    status: ConflictStatus
    topic: str
    scenario: UserScenario
    risk_level: RiskLevel
    city: str | None = None
    scope_partitioned: bool = False
    sources: list[SourceSnapshot]
    quotes: dict[str, str]
    proposal: ResolutionProposal | None = None
    proposal_actor_id: str | None = None
    approval_actor_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AppliedResolution(BaseModel):
    conflict_id: str
    revision: int
    note: str
    outcome: ResolutionOutcome
    preferred_source_ids: list[str] = Field(default_factory=list)
    quotes: dict[str, str]
    snapshot_refs: dict[str, str]
    proposal_actor_id: str
    approval_actor_id: str
    valid_until: datetime
    matched_branch_index: int | None = None
    applicability: ResolutionApplicability | None = None


class ResolutionEvaluation(BaseModel):
    applied: list[AppliedResolution] = Field(default_factory=list)
    blocked_conflict_ids: list[str] = Field(default_factory=list)
    excluded_source_ids: list[str] = Field(default_factory=list)


class ConflictEvent(BaseModel):
    event_id: str
    sequence: int
    event_type: str
    conflict_id: str | None = None
    revision: int | None = None
    actor_id: str | None = None
    actor_roles: list[str] = Field(default_factory=list)
    reason: str
    created_at: datetime
    payload: dict
    previous_hash: str
    event_hash: str


class IntegrityReport(BaseModel):
    passed: bool
    event_count: int
    snapshot_count: int
    problems: list[str] = Field(default_factory=list)
