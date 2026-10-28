from pydantic import BaseModel, Field

from backend.app.checklist_engine.policies import (
    checklist_requires_escalation_step,
    checklist_requires_official_source,
)
from backend.app.domain.checklists import Checklist
from backend.app.domain.enums import RiskLevel, UserScenario

UNSAFE_WORK_PATTERNS = (
    "work on tourist visa",
    "start working first",
    "documents later",
    "nobody checks",
)

UNSAFE_MEDICAL_PATTERNS = (
    "take antibiotics without doctor",
    "do not go to doctor",
)

UNSAFE_MONEY_PATTERNS = (
    "send money to unknown agents",
    "send money to strangers",
)


class ChecklistValidationFinding(BaseModel):
    finding_type: str
    severity: str
    summary: str
    item_id: str | None = None


class ChecklistValidationReport(BaseModel):
    findings: list[ChecklistValidationFinding] = Field(default_factory=list)
    passed: bool


def validate_checklist(
    checklist: Checklist,
    scenario: UserScenario,
    risk_level: RiskLevel,
    selected_source_ids: list[str] | None = None,
    safety_flags: list[str] | None = None,
) -> ChecklistValidationReport:
    del selected_source_ids
    safety_flags = safety_flags or []
    findings: list[ChecklistValidationFinding] = []

    if not checklist.items:
        findings.append(
            ChecklistValidationFinding(
                finding_type="empty_checklist",
                severity="high",
                summary="Checklist has no items.",
            )
        )

    item_ids = [item.item_id for item in checklist.items]
    duplicate_ids = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    for item_id in duplicate_ids:
        findings.append(
            ChecklistValidationFinding(
                finding_type="duplicate_item_id",
                severity="high",
                summary=f"Duplicate checklist item ID: {item_id}.",
                item_id=item_id,
            )
        )

    combined_text = " ".join(
        f"{item.title} {item.description or ''}".casefold()
        for item in checklist.items
    )
    if checklist_requires_official_source(scenario, risk_level):
        if not _has_official_confirmation_step(combined_text):
            findings.append(
                ChecklistValidationFinding(
                    finding_type="missing_official_confirmation_step",
                    severity="high",
                    summary="High-risk checklist needs official or professional confirmation step.",
                )
            )

    if checklist_requires_escalation_step(risk_level, safety_flags):
        if not any(item.action == "support" for item in checklist.items) and not (
            _has_escalation_step(combined_text)
        ):
            findings.append(
                ChecklistValidationFinding(
                    finding_type="missing_escalation_step",
                    severity="high",
                    summary="Checklist needs human review or escalation step.",
                )
            )

    findings.extend(_unsafe_wording_findings(checklist, scenario))
    has_high_findings = any(finding.severity == "high" for finding in findings)
    return ChecklistValidationReport(findings=findings, passed=not has_high_findings)


def _has_official_confirmation_step(combined_text: str) -> bool:
    return any(
        term in combined_text for term in (
            "official", "professional", "consular", "официаль", "специалист",
            "ресми", "маман", "官方", "专业",
        )
    )


def _has_escalation_step(combined_text: str) -> bool:
    return (
        "escalat" in combined_text
        or "human" in combined_text
        or "emergency support" in combined_text
        or "official support" in combined_text
    )


def _unsafe_wording_findings(
    checklist: Checklist,
    scenario: UserScenario,
) -> list[ChecklistValidationFinding]:
    findings: list[ChecklistValidationFinding] = []
    for item in checklist.items:
        text = f"{item.title} {item.description or ''}".casefold()
        if scenario == UserScenario.work:
            findings.extend(
                _pattern_findings(
                    item.item_id,
                    text,
                    UNSAFE_WORK_PATTERNS,
                    "unsafe_work_wording",
                )
            )
        if scenario == UserScenario.medical:
            findings.extend(
                _pattern_findings(
                    item.item_id,
                    text,
                    UNSAFE_MEDICAL_PATTERNS,
                    "unsafe_medical_wording",
                )
            )
        if scenario in {UserScenario.payments, UserScenario.housing}:
            findings.extend(
                _pattern_findings(
                    item.item_id,
                    text,
                    UNSAFE_MONEY_PATTERNS,
                    "unsafe_money_wording",
                )
            )
    return findings


def _pattern_findings(
    item_id: str,
    text: str,
    patterns: tuple[str, ...],
    finding_type: str,
) -> list[ChecklistValidationFinding]:
    return [
        ChecklistValidationFinding(
            finding_type=finding_type,
            severity="high",
            summary=f"Unsafe checklist wording detected: {pattern}.",
            item_id=item_id,
        )
        for pattern in patterns
        if pattern in text
    ]
