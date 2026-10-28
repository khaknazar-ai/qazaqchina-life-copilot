from typing import Any

from backend.app.answer_quality.models import (
    AnswerQualityIssue,
    AnswerQualityReport,
    GroundedAnswerDraft,
)
from backend.app.answer_quality.policies import is_high_risk_scenario


def build_answer_quality_report(draft: GroundedAnswerDraft) -> AnswerQualityReport:
    has_direct_answer = bool(draft.direct_answer.strip())
    has_grounded_facts = bool(draft.grounded_facts)
    has_steps = bool(draft.recommended_steps)
    has_escalation = bool(draft.escalation)
    has_uncertainty = bool(draft.uncertainty)
    trusted_source_count = len(draft.source_notes)
    high_risk = is_high_risk_scenario(draft.scenario, draft.risk_level)
    issues: list[AnswerQualityIssue] = []

    if not has_direct_answer:
        issues.append(
            AnswerQualityIssue(
                severity="error",
                code="missing_direct_answer",
                message="Answer draft is missing a direct short answer.",
            )
        )
    if not has_steps:
        issues.append(
            AnswerQualityIssue(
                severity="warning",
                code="missing_recommended_steps",
                message="Answer draft has no recommended next steps.",
            )
        )
    if trusted_source_count == 0:
        issues.append(
            AnswerQualityIssue(
                severity="warning",
                code="no_trusted_sources",
                message="No trusted source notes are attached to the answer.",
            )
        )
    cited_action = any(step.source_ids for step in draft.recommended_steps)
    if not has_grounded_facts and not cited_action and trusted_source_count > 0:
        issues.append(
            AnswerQualityIssue(
                severity="warning",
                code="missing_grounded_facts",
                message="Trusted source notes exist but no grounded fact section was produced.",
            )
        )
    if high_risk and not has_escalation:
        issues.append(
            AnswerQualityIssue(
                severity="error",
                code="high_risk_missing_escalation",
                message="High-risk answer draft is missing escalation guidance.",
            )
        )
    if high_risk and not has_uncertainty:
        issues.append(
            AnswerQualityIssue(
                severity="warning",
                code="high_risk_missing_uncertainty",
                message="High-risk answer draft is missing uncertainty or verification wording.",
            )
        )
    if draft.unreviewed_candidate_count > 0:
        issues.append(
            AnswerQualityIssue(
                severity="info",
                code="unreviewed_candidates_not_cited",
                message=(
                    "Unreviewed source candidates are present but must not be cited as "
                    "trusted evidence."
                ),
            )
        )

    return AnswerQualityReport(
        scenario=draft.scenario,
        risk_level=draft.risk_level,
        has_direct_answer=has_direct_answer,
        has_grounded_facts=has_grounded_facts,
        has_steps=has_steps,
        has_escalation=has_escalation,
        has_uncertainty=has_uncertainty,
        trusted_source_count=trusted_source_count,
        unreviewed_candidate_count=draft.unreviewed_candidate_count,
        issues=issues,
    )


def answer_quality_report_to_jsonable(report: AnswerQualityReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def answer_quality_report_to_markdown(report: AnswerQualityReport) -> str:
    lines = [
        "# Answer Quality Report",
        "",
        f"- Scenario: {report.scenario or 'unspecified'}",
        f"- Risk level: {report.risk_level or 'unspecified'}",
        f"- Has direct answer: {report.has_direct_answer}",
        f"- Has grounded facts: {report.has_grounded_facts}",
        f"- Has recommended steps: {report.has_steps}",
        f"- Has escalation: {report.has_escalation}",
        f"- Has uncertainty: {report.has_uncertainty}",
        f"- Trusted source notes: {report.trusted_source_count}",
        f"- Unreviewed candidates: {report.unreviewed_candidate_count}",
        "",
        "## Issues",
    ]
    if not report.issues:
        lines.append("- None")
    else:
        lines.extend(
            f"- {issue.severity.upper()} {issue.code}: {issue.message}"
            for issue in report.issues
        )
    return "\n".join(lines)
