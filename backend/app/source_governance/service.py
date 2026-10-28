from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel
from backend.app.domain.sources import Citation, RetrievedSource
from backend.app.source_governance.citations import CitationVerificationReport, CitationVerifier
from backend.app.source_governance.conflicts import SourceConflictChecker, SourceConflictReport


class SourceGovernanceResult(BaseModel):
    conflict_report: SourceConflictReport
    citation_report: CitationVerificationReport
    passed: bool
    recommended_actions: list[str] = Field(default_factory=list)


class SourceGovernanceService:
    def __init__(
        self,
        conflict_checker: SourceConflictChecker | None = None,
        citation_verifier: CitationVerifier | None = None,
    ) -> None:
        self.conflict_checker = conflict_checker or SourceConflictChecker()
        self.citation_verifier = citation_verifier or CitationVerifier()

    def check(
        self,
        answer: str,
        selected_sources: list[RetrievedSource],
        citations: list[Citation],
        risk_level: RiskLevel,
        safety_flags: list[str] | None = None,
    ) -> SourceGovernanceResult:
        conflict_report = self.conflict_checker.check_sources(
            sources=selected_sources,
            risk_level=risk_level,
            safety_flags=safety_flags or [],
        )
        citation_report = self.citation_verifier.verify(
            answer=answer,
            citations=citations,
            selected_sources=selected_sources,
            risk_level=risk_level,
        )
        has_high_conflict = any(
            finding.severity == "high" for finding in conflict_report.findings
        )
        passed = not has_high_conflict and citation_report.passed
        return SourceGovernanceResult(
            conflict_report=conflict_report,
            citation_report=citation_report,
            passed=passed,
            recommended_actions=_recommended_actions(conflict_report, citation_report),
        )


def _recommended_actions(
    conflict_report: SourceConflictReport,
    citation_report: CitationVerificationReport,
) -> list[str]:
    actions: list[str] = []
    for finding in conflict_report.findings:
        actions.append(finding.recommended_action)
    for finding in citation_report.findings:
        actions.append(finding.summary)
    return list(dict.fromkeys(actions))
