from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel
from backend.app.domain.sources import Citation, RetrievedSource, is_retrievable_source
from backend.app.source_governance.policies import (
    is_community_or_contributor_source,
    is_official_or_curated_source,
    requires_official_or_curated_sources,
)

COMMUNITY_LABEL_PHRASES = (
    "community experience",
    "user experience",
    "practical experience",
    "institutional experience",
    "verified contributor experience",
)


class CitationVerificationFinding(BaseModel):
    citation_id: str | None = None
    source_id: str | None = None
    severity: str
    finding_type: str
    summary: str


class CitationVerificationReport(BaseModel):
    findings: list[CitationVerificationFinding] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    missing_citation_count: int = 0
    community_label_required_count: int = 0
    passed: bool


class CitationVerifier:
    def verify(
        self,
        answer: str,
        citations: list[Citation],
        selected_sources: list[RetrievedSource],
        risk_level: RiskLevel,
    ) -> CitationVerificationReport:
        findings: list[CitationVerificationFinding] = []
        selected_by_source_id: dict[str, RetrievedSource] = {}
        for retrieved_source in selected_sources:
            selected_by_source_id.setdefault(
                retrieved_source.source.source_id,
                retrieved_source,
            )

        for citation in citations:
            selected_source = selected_by_source_id.get(citation.source_id)
            if selected_source is None:
                findings.append(
                    CitationVerificationFinding(
                        citation_id=citation.citation_id,
                        source_id=citation.source_id,
                        severity="high",
                        finding_type="citation_source_not_selected",
                        summary=(
                            f"Citation {citation.citation_id} references a source that "
                            "was not selected."
                        ),
                    )
                )
                continue

            if not is_retrievable_source(selected_source.source):
                findings.append(
                    CitationVerificationFinding(
                        citation_id=citation.citation_id,
                        source_id=citation.source_id,
                        severity="high",
                        finding_type="citation_source_blocked",
                        summary="Citation uses a source blocked by review or retrieval policy.",
                    )
                )
                continue

            if not citation.claim.strip():
                findings.append(
                    CitationVerificationFinding(
                        citation_id=citation.citation_id,
                        source_id=citation.source_id,
                        severity="high",
                        finding_type="empty_claim",
                        summary=f"Citation {citation.citation_id} has an empty claim.",
                    )
                )

            if citation.supporting_quote and not _quote_found(
                quote=citation.supporting_quote,
                content=selected_source.content,
            ):
                findings.append(
                    CitationVerificationFinding(
                        citation_id=citation.citation_id,
                        source_id=citation.source_id,
                        severity="high",
                        finding_type="quote_not_found_in_source",
                        summary=(
                            f"Citation {citation.citation_id} supporting quote was not "
                            "found in the selected source content."
                        ),
                    )
                )

        findings.extend(_community_label_findings(answer, citations, selected_by_source_id))
        findings.extend(_high_risk_citation_findings(citations, selected_by_source_id, risk_level))

        high_severity_count = sum(1 for finding in findings if finding.severity == "high")
        return CitationVerificationReport(
            findings=findings,
            unsupported_claim_count=sum(
                1
                for finding in findings
                if finding.finding_type
                in {
                    "citation_source_not_selected",
                    "citation_source_blocked",
                    "empty_claim",
                    "quote_not_found_in_source",
                }
            ),
            missing_citation_count=sum(
                1
                for finding in findings
                if finding.finding_type == "high_risk_missing_official_citation"
            ),
            community_label_required_count=sum(
                1
                for finding in findings
                if finding.finding_type
                in {
                    "community_source_labeled_as_official",
                    "community_label_missing",
                }
            ),
            passed=high_severity_count == 0,
        )


def _quote_found(quote: str, content: str) -> bool:
    normalized_quote = _normalize_text(quote)
    normalized_content = _normalize_text(content)
    if not normalized_quote:
        return True
    return bool(normalized_content) and normalized_quote in normalized_content


def _community_label_findings(
    answer: str,
    citations: list[Citation],
    selected_by_source_id: dict[str, RetrievedSource],
) -> list[CitationVerificationFinding]:
    findings: list[CitationVerificationFinding] = []
    answer_normalized = answer.casefold()
    community_citations = [
        citation
        for citation in citations
        if (
            citation.source_id in selected_by_source_id
            and is_community_or_contributor_source(
                selected_by_source_id[citation.source_id].source
            )
        )
    ]
    if not community_citations:
        return findings

    for citation in community_citations:
        if _answer_labels_source_as_official(answer_normalized, citation.source_id):
            findings.append(
                CitationVerificationFinding(
                    citation_id=citation.citation_id,
                    source_id=citation.source_id,
                    severity="high",
                    finding_type="community_source_labeled_as_official",
                    summary=(
                        f"Community or contributor source {citation.source_id} appears "
                        "to be labeled as official."
                    ),
                )
            )

    if not any(phrase in answer_normalized for phrase in COMMUNITY_LABEL_PHRASES):
        findings.append(
            CitationVerificationFinding(
                severity="high",
                finding_type="community_label_missing",
                summary=(
                    "Community or contributor citations require a practical, community, "
                    "or institutional experience label."
                ),
            )
        )

    return findings


def _high_risk_citation_findings(
    citations: list[Citation],
    selected_by_source_id: dict[str, RetrievedSource],
    risk_level: RiskLevel,
) -> list[CitationVerificationFinding]:
    if not citations or not requires_official_or_curated_sources(risk_level):
        return []

    has_official_or_curated_citation = any(
        citation.source_id in selected_by_source_id
        and is_official_or_curated_source(selected_by_source_id[citation.source_id].source)
        for citation in citations
    )
    if has_official_or_curated_citation:
        return []

    return [
        CitationVerificationFinding(
            severity="high",
            finding_type="high_risk_missing_official_citation",
            summary="High-risk answer has citations but no official or curated citation.",
        )
    ]


def _answer_labels_source_as_official(answer_normalized: str, source_id: str) -> bool:
    source_id_normalized = source_id.casefold()
    index = answer_normalized.find(source_id_normalized)
    while index != -1:
        window_start = max(0, index - 80)
        window_end = min(len(answer_normalized), index + len(source_id_normalized) + 80)
        window = answer_normalized[window_start:window_end]
        if "official" in window and "not official" not in window:
            return True
        index = answer_normalized.find(source_id_normalized, index + len(source_id_normalized))
    return False


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
