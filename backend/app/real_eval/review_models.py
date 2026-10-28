"""Human evaluation labels are separate from source publication decisions."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.real_eval.dataset import RealMaterialCase
from backend.app.source_conflicts.models import ResolutionApplicability

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
LabelText = Annotated[str, Field(min_length=1, max_length=800)]


class EvaluationLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_behavior: Literal["grounded_answer", "clarify", "refuse", "escalate"]
    scenario: UserScenario
    risk_level: RiskLevel
    required_conditions: list[LabelText] = Field(default_factory=list, max_length=20)
    forbidden_claims: list[LabelText] = Field(default_factory=list, max_length=20)
    expected_conflict: StrictBool | None = None
    applicability: ResolutionApplicability | None = None


class EvaluationApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_case_hash: Hash
    expected_evidence_hash: Hash
    expected_review_id: str | None = Field(default=None, pattern=r"^eval-review-[a-f0-9]{32}$")
    labels: EvaluationLabels
    expires_at: datetime
    originals_checked: StrictBool
    question_checked: StrictBool
    conditions_checked: StrictBool
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Review expiry must include a timezone")
        return value.astimezone(UTC)


class EvaluationRevocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_review_id: str = Field(pattern=r"^eval-review-[a-f0-9]{32}$")
    reason: str = Field(min_length=1, max_length=1000)


class AnnotationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str
    case_hash: Hash
    evidence_hash: Hash
    labels_hash: Hash
    reviewer_id: str
    reviewed_at: datetime
    expires_at: datetime


class EvaluationReviewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "revoke"]
    case_id: str
    review_id: str
    actor_id: str
    actor_token_id: str
    actor_permissions: list[str]
    auth_mode: str
    at: datetime
    approval: EvaluationApproval | None = None
    reason: str | None = None
    labels_hash: Hash | None = None
    previous_review_id: str | None = None
    case_snapshot: RealMaterialCase | None = None
