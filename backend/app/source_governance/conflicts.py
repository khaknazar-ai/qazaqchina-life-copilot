from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel, SourceType
from backend.app.domain.sources import RetrievedSource, is_retrievable_source, trust_level_rank
from backend.app.source_governance.policies import (
    is_community_or_contributor_source,
    is_official_or_curated_source,
    requires_official_or_curated_sources,
)

RISKY_COMMUNITY_ADVICE_PATTERNS = (
    "work on tourist visa",
    "start working first",
    "documents later",
    "\u0431\u0435\u0437\u0432\u0438\u0437",
    "\u0442\u0443\u0440\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a",
    "\u043f\u043e\u0442\u043e\u043c \u043e\u0444\u043e\u0440\u043c",
)


class SourceConflictFinding(BaseModel):
    conflict_id: str
    higher_trust_source_id: str | None = None
    lower_trust_source_id: str | None = None
    severity: str
    conflict_type: str
    summary: str
    recommended_action: str


class SourceConflictReport(BaseModel):
    findings: list[SourceConflictFinding] = Field(default_factory=list)
    has_conflicts: bool = False
    high_risk_without_official_source: bool = False


class SourceConflictChecker:
    def check_sources(
        self,
        sources: list[RetrievedSource],
        risk_level: RiskLevel,
        safety_flags: list[str] | None = None,
    ) -> SourceConflictReport:
        del safety_flags
        findings: list[SourceConflictFinding] = []
        selected_sources = [retrieved_source.source for retrieved_source in sources]
        official_or_curated = [
            source for source in selected_sources if is_official_or_curated_source(source)
        ]
        community_or_contributor = [
            source for source in selected_sources if is_community_or_contributor_source(source)
        ]

        high_risk_without_official_source = False
        if (
            requires_official_or_curated_sources(risk_level)
            and selected_sources
            and community_or_contributor
            and not official_or_curated
        ):
            high_risk_without_official_source = True
            findings.append(
                SourceConflictFinding(
                    conflict_id="SRC-CONFLICT-001",
                    severity="high",
                    conflict_type="missing_official_source",
                    summary=(
                        "High-risk case selected only community or contributor sources."
                    ),
                    recommended_action="use_official_or_curated_source_or_escalate",
                )
            )

        findings.extend(self._untrusted_source_findings(sources))
        findings.extend(self._risky_community_findings(sources, official_or_curated))
        findings.extend(
            self._verified_contributor_context_findings(
                selected_sources=selected_sources,
                official_or_curated=official_or_curated,
                risk_level=risk_level,
            )
        )

        return SourceConflictReport(
            findings=findings,
            has_conflicts=bool(findings),
            high_risk_without_official_source=high_risk_without_official_source,
        )

    @staticmethod
    def _untrusted_source_findings(
        sources: list[RetrievedSource],
    ) -> list[SourceConflictFinding]:
        findings: list[SourceConflictFinding] = []
        for index, retrieved_source in enumerate(sources, start=1):
            source = retrieved_source.source
            if is_retrievable_source(source):
                continue
            findings.append(
                SourceConflictFinding(
                    conflict_id=f"SRC-CONFLICT-UNTRUSTED-{index}",
                    lower_trust_source_id=source.source_id,
                    severity="high",
                    conflict_type="untrusted_source_selected",
                    summary=f"Selected source {source.source_id} is not retrievable.",
                    recommended_action="remove_untrusted_source_from_answer_support",
                )
            )
        return findings

    @staticmethod
    def _risky_community_findings(
        sources: list[RetrievedSource],
        official_or_curated_sources: list,
    ) -> list[SourceConflictFinding]:
        if not official_or_curated_sources:
            return []

        highest_trust_source = min(
            official_or_curated_sources,
            key=lambda source: (trust_level_rank(source.trust_level), source.source_id),
        )
        findings: list[SourceConflictFinding] = []
        for index, retrieved_source in enumerate(sources, start=1):
            source = retrieved_source.source
            if not is_community_or_contributor_source(source):
                continue
            if not _contains_risky_advice(retrieved_source.content):
                continue
            findings.append(
                SourceConflictFinding(
                    conflict_id=f"SRC-CONFLICT-RISKY-COMMUNITY-{index}",
                    higher_trust_source_id=highest_trust_source.source_id,
                    lower_trust_source_id=source.source_id,
                    severity="high",
                    conflict_type="risky_community_advice",
                    summary=(
                        f"Community or contributor source {source.source_id} contains "
                        "obvious risky work-status advice markers."
                    ),
                    recommended_action="prefer_official_or_curated_source_and_escalate",
                )
            )
        return findings

    @staticmethod
    def _verified_contributor_context_findings(
        selected_sources: list,
        official_or_curated: list,
        risk_level: RiskLevel,
    ) -> list[SourceConflictFinding]:
        if not requires_official_or_curated_sources(risk_level) or not official_or_curated:
            return []

        findings: list[SourceConflictFinding] = []
        for index, source in enumerate(selected_sources, start=1):
            if source.source_type != SourceType.verified_institutional_contributor:
                continue
            findings.append(
                SourceConflictFinding(
                    conflict_id=f"SRC-CONFLICT-VERIFIED-CONTEXT-{index}",
                    lower_trust_source_id=source.source_id,
                    severity="info",
                    conflict_type="verified_contributor_context_only",
                    summary=(
                        f"Verified contributor source {source.source_id} can provide "
                        "institutional experience only, not official law."
                    ),
                    recommended_action="label_as_institutional_experience_not_official_law",
                )
            )
        return findings


def _contains_risky_advice(content: str) -> bool:
    normalized = content.casefold()
    return any(pattern in normalized for pattern in RISKY_COMMUNITY_ADVICE_PATTERNS)
