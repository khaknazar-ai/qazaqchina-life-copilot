"""Provisional evaluation questions bound to actual captured material."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.source_conflicts.models import ResolutionApplicability
from backend.app.source_corpus.models import CorpusPacket

if TYPE_CHECKING:
    from backend.app.real_eval.review_service import EvaluationReviewService


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote: str = Field(min_length=1, max_length=400)


class RealMaterialCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=100)
    language: LanguageCode
    question: str = Field(min_length=1, max_length=8000)
    expected_behavior: Literal["grounded_answer", "clarify", "refuse", "escalate"]
    scenario: UserScenario
    risk_level: RiskLevel
    evidence: list[Evidence] = Field(default_factory=list)
    required_conditions: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_conflict: bool | None = None
    annotation_status: Literal["pending", "reviewed"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    annotation_review_id: str | None = None
    source_applicability: ResolutionApplicability | None = None


def load_real_material_cases(
    path: Path | str = "data/evals/real_material_cases.json",
) -> list[RealMaterialCase]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported real-material dataset schema")
    catalog = value.get("evidence_catalog", {})
    cases = []
    for item in value["cases"]:
        resolved = dict(item)
        evidence = []
        for entry in item["evidence"]:
            if isinstance(entry, str):
                if entry not in catalog:
                    raise ValueError("Dataset evidence catalog reference is missing")
                entry = catalog[entry]
            evidence.append(entry)
        resolved["evidence"] = evidence
        cases.append(RealMaterialCase.model_validate(resolved))
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Dataset case identifiers must be unique")
    return cases


def validate_real_material_cases(
    cases: list[RealMaterialCase],
    packets: list[CorpusPacket],
    *,
    require_reviewed: bool = True,
    annotation_review_service: "EvaluationReviewService | None" = None,
) -> dict:
    sources = {packet.source_id: packet for packet in packets}
    errors: list[str] = []
    if not cases or len({case.case_id for case in cases}) != len(cases):
        errors.append("Evaluation case identifiers must be nonempty and unique")
    if len(sources) != len(packets):
        errors.append("Captured source identifiers must be unique")
    try:
        annotation_errors = (
            annotation_review_service.annotation_errors(cases, packets)
            if annotation_review_service is not None
            else [
                f"{case.case_id}: human annotation requires authenticated ledger approval"
                for case in cases
            ]
        )
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
        annotation_errors = [
            f"{case.case_id}: human annotation review storage is unavailable" for case in cases
        ]
    pending = len(annotation_errors)
    if require_reviewed:
        errors.extend(annotation_errors)
    for case in cases:
        if not case.evidence:
            errors.append(f"{case.case_id}: captured material provenance is missing")
        for evidence in case.evidence:
            packet = sources.get(evidence.source_id)
            if packet is None:
                errors.append(f"{case.case_id}: captured source is missing: {evidence.source_id}")
            elif packet.status != "pending":
                errors.append(
                    f"{case.case_id}: captured source body is blocked: {evidence.source_id}"
                )
            elif packet.text_sha256 != evidence.text_sha256:
                errors.append(f"{case.case_id}: source text hash has changed: {evidence.source_id}")
            elif evidence.quote not in packet.text:
                errors.append(f"{case.case_id}: quote is not an exact source substring")
    return {
        "case_count": len(cases),
        "pending_annotation_count": pending,
        "provenance_passed": not any("human annotation" not in error for error in errors),
        "passed": not errors,
        "quality_evaluation_ready": not errors and require_reviewed,
        "errors": errors,
        "used_network": False,
        "used_external_provider": False,
    }
