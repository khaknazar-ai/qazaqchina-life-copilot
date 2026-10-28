from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel, UserScenario


class DetectedConflict(BaseModel):
    topic: str
    source_ids: list[str]
    quotes: list[str]
    scenario: UserScenario
    risk_level: RiskLevel
    city: str | None = None
    reason: str
    rule_id: str | None = None
    conflict_kind: str = "potential_contradiction"
    scope: dict[str, str] = Field(default_factory=dict)
    conflict_key: str | None = None


class ConflictDetectionReport(BaseModel):
    suggestions: list[DetectedConflict] = Field(default_factory=list)
    coverage_status: str = "bounded_rules"
    input_source_count: int = 0
    scanned_source_count: int = 0
    skipped_source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    used_network: bool = False
