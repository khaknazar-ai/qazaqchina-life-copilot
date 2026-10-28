import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

OfficialSourceReviewEvidenceStatus = Literal[
    "missing",
    "template_only",
    "invalid",
    "blocked_sensitive_data",
    "blocked_secret_pattern",
    "valid_metadata_only",
    "ready_for_review_application",
]

FindingSeverity = Literal["info", "warning", "blocker"]
ReviewRound = Literal["first_review", "second_review"]
EvidenceDecision = Literal[
    "pending",
    "needs_changes",
    "rejected",
    "approved_for_preview",
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
SECRET_TERM_PATTERN = re.compile(
    r"\b(api[_-]?key|token|secret|password|bearer|openai_api_key|google_api_key)\b",
    re.IGNORECASE,
)
SK_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OfficialSourceReviewEvidenceFinding(BaseModel):
    finding_id: str
    severity: FindingSeverity
    title: str
    description: str
    recommendation: str | None = None


class OfficialSourceCandidateReviewEvidence(BaseModel):
    candidate_id: str
    reviewer_role: str
    review_round: ReviewRound
    official_publisher_verified: bool = False
    url_or_document_captured: bool = False
    trust_tier_classified: bool = False
    domain_scope_confirmed: bool = False
    freshness_checked: bool = False
    source_version_recorded: bool = False
    no_conflict_with_existing_sources: bool = False
    reviewer_notes_present: bool = False
    high_risk_second_review_completed: bool = False
    decision: EvidenceDecision = "pending"
    allowed_claim_types: list[str] = Field(default_factory=list)
    prohibited_claim_types: list[str] = Field(default_factory=list)
    required_warnings: list[str] = Field(default_factory=list)
    sanitized_reviewer_notes: list[str] = Field(default_factory=list)
    reviewed_at: str | None = None
    not_trusted_until_published: bool = True


class OfficialSourceReviewEvidenceReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    evidence_path: str | None
    evidence_exists: bool
    template_only: bool
    status: OfficialSourceReviewEvidenceStatus
    total_evidence_items: int
    first_review_count: int
    second_review_count: int
    approved_for_preview_count: int
    needs_changes_count: int
    rejected_count: int
    blocker_count: int
    warning_count: int
    findings: list[OfficialSourceReviewEvidenceFinding]
    evidence_items: list[OfficialSourceCandidateReviewEvidence]
    sanitized_summary: dict[str, object]
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class OfficialSourceReviewEvidenceService:
    def __init__(
        self,
        project_root: Path | str = ".",
        evidence_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.evidence_path = Path(evidence_path) if evidence_path is not None else None

    def default_local_evidence_path(self) -> Path:
        return (
            self.project_root
            / "configs"
            / "source_review"
            / "official_source_review_evidence.local.json"
        )

    def load_evidence(self, path: Path | str) -> dict:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("official source review evidence must be a JSON object")
        return loaded

    def validate_evidence_data(
        self,
        data: dict,
    ) -> list[OfficialSourceReviewEvidenceFinding]:
        findings: list[OfficialSourceReviewEvidenceFinding] = []
        raw_items = _raw_evidence_items(data)
        if not raw_items:
            return [
                OfficialSourceReviewEvidenceFinding(
                    finding_id="REVIEW-EVIDENCE-NO-ITEMS",
                    severity="warning",
                    title="No review evidence items found.",
                    description="The evidence file has no structured review evidence entries.",
                    recommendation="Add evidence items only after human review is complete.",
                )
            ]

        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-{index}-INVALID",
                        severity="blocker",
                        title="Review evidence entry is invalid.",
                        description="Each review evidence item must be a JSON object.",
                        recommendation="Replace the entry with structured review evidence.",
                    )
                )
                continue
            item = _evidence_item_from_raw(raw_item, index)
            missing = _missing_required_metadata(item)
            if missing:
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-{index}-MISSING-METADATA",
                        severity="warning",
                        title="Review evidence metadata is incomplete.",
                        description=f"Missing metadata: {', '.join(missing)}.",
                        recommendation=(
                            "Complete candidate ID, reviewer role label, review round, "
                            "decision, and reviewer notes presence before applying evidence."
                        ),
                    )
                )
            if item.review_round not in {"first_review", "second_review"}:
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-{index}-ROUND",
                        severity="blocker",
                        title="Review round is invalid.",
                        description="Review round must be first_review or second_review.",
                        recommendation="Use a supported review round label.",
                    )
                )
            if item.decision not in {
                "pending",
                "needs_changes",
                "rejected",
                "approved_for_preview",
            }:
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-{index}-DECISION",
                        severity="blocker",
                        title="Review decision is invalid.",
                        description=(
                            "Decision must be pending, needs_changes, rejected, or "
                            "approved_for_preview."
                        ),
                        recommendation="Use a supported review decision.",
                    )
                )
            if item.decision == "approved_for_preview" and not _complete_for_preview(item):
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-{index}-PREVIEW-INCOMPLETE",
                        severity="warning",
                        title="Approved-for-preview evidence is incomplete.",
                        description=(
                            "Preview approval requires publisher, capture, tier, domain, "
                            "freshness, version, conflict, notes, and high-risk second review."
                        ),
                        recommendation=(
                            "Complete the review checklist and high-risk second review before "
                            "requesting publish preview."
                        ),
                    )
                )
        return findings

    def detect_sensitive_or_secret_data(
        self,
        data: dict,
    ) -> list[OfficialSourceReviewEvidenceFinding]:
        findings: list[OfficialSourceReviewEvidenceFinding] = []
        for path, value in _iter_string_values(data):
            category = _sensitive_category(value)
            if category is None:
                continue
            if category == "secret":
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-SECRET-{len(findings) + 1}",
                        severity="blocker",
                        title="Secret-like value detected in review evidence.",
                        description=f"Secret-like content was detected at `{path}`.",
                        recommendation=(
                            "Remove tokens, keys, passwords, bearer values, and private keys "
                            "from local review evidence."
                        ),
                    )
                )
            else:
                findings.append(
                    OfficialSourceReviewEvidenceFinding(
                        finding_id=f"REVIEW-EVIDENCE-SENSITIVE-{len(findings) + 1}",
                        severity="blocker",
                        title="Sensitive personal data detected in review evidence.",
                        description=f"Personal contact-like content was detected at `{path}`.",
                        recommendation=(
                            "Use reviewer role labels only. Remove private emails, phone "
                            "numbers, and personal contact details."
                        ),
                    )
                )
        return findings

    def build_evidence_items(
        self,
        data: dict,
    ) -> list[OfficialSourceCandidateReviewEvidence]:
        items: list[OfficialSourceCandidateReviewEvidence] = []
        for index, raw_item in enumerate(_raw_evidence_items(data), start=1):
            if isinstance(raw_item, dict):
                items.append(_evidence_item_from_raw(raw_item, index))
        return items

    def generate_report(self) -> OfficialSourceReviewEvidenceReport:
        path = self.evidence_path or self.default_local_evidence_path()
        if not path.exists():
            findings = [
                OfficialSourceReviewEvidenceFinding(
                    finding_id="REVIEW-EVIDENCE-MISSING",
                    severity="info",
                    title="Local review evidence file is missing.",
                    description="Missing review evidence is safe and does not create trust.",
                    recommendation="Create an ignored local evidence file only after review.",
                )
            ]
            return _report(path, False, False, "missing", [], findings)

        try:
            data = self.load_evidence(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings = [
                OfficialSourceReviewEvidenceFinding(
                    finding_id="REVIEW-EVIDENCE-INVALID",
                    severity="blocker",
                    title="Local review evidence cannot be parsed.",
                    description=(
                        "Review evidence is invalid JSON/object metadata: "
                        f"{type(exc).__name__}."
                    ),
                    recommendation="Fix the local evidence JSON structure before applying it.",
                )
            ]
            return _report(path, True, False, "invalid", [], findings)

        template_only = bool(data.get("template_only") or data.get("example_only"))
        items = self.build_evidence_items(data)
        safety_findings = self.detect_sensitive_or_secret_data(data)
        if template_only:
            findings = [
                OfficialSourceReviewEvidenceFinding(
                    finding_id="REVIEW-EVIDENCE-TEMPLATE-ONLY",
                    severity="info",
                    title="Review evidence file is template/example only.",
                    description="Template/example evidence is safe but cannot be applied.",
                    recommendation="Create an ignored local evidence file after real review.",
                ),
                *safety_findings,
            ]
        else:
            findings = [*self.validate_evidence_data(data), *safety_findings]
        status = _status_for_report(template_only, items, findings)
        return _report(path, True, template_only, status, items, findings)


def official_source_review_evidence_report_to_jsonable(
    report: OfficialSourceReviewEvidenceReport,
) -> dict:
    return report.model_dump(mode="json")


def official_source_review_evidence_report_to_markdown(
    report: OfficialSourceReviewEvidenceReport,
) -> str:
    lines = [
        "# Official Source Human Review Evidence Report",
        "",
        "## Executive Decision",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: {report.status}",
        f"- Evidence exists: {report.evidence_exists}",
        f"- Template only: {report.template_only}",
        f"- Total evidence items: {report.total_evidence_items}",
        f"- First review count: {report.first_review_count}",
        f"- Second review count: {report.second_review_count}",
        f"- Approved for preview count: {report.approved_for_preview_count}",
        f"- Needs changes count: {report.needs_changes_count}",
        f"- Rejected count: {report.rejected_count}",
        f"- Blocker count: {report.blocker_count}",
        f"- Warning count: {report.warning_count}",
        f"- Ready for closed beta: {report.ready_for_closed_beta}",
        f"- Ready for public launch: {report.ready_for_public_launch}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "Human review evidence is not trusted citizen-answer evidence.",
        "Approved-for-publish-preview evidence is still not published.",
        "",
        "## Sanitized Evidence Summary",
        "",
        (
            "- Candidate IDs: "
            f"{', '.join(report.sanitized_summary.get('candidate_ids', [])) or 'none'}"
        ),
        (
            "- Reviewer roles: "
            f"{', '.join(report.sanitized_summary.get('reviewer_roles', [])) or 'none'}"
        ),
        "",
        "## Evidence Items",
        "",
        "| Candidate | Round | Decision | Notes present | Second review completed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.evidence_items:
        lines.append(
            f"| {item.candidate_id} | {item.review_round} | {item.decision} | "
            f"{item.reviewer_notes_present} | {item.high_risk_second_review_completed} |"
        )

    lines.extend(["", "## Findings", ""])
    if report.findings:
        for finding in report.findings:
            lines.extend(
                [
                    f"### {finding.finding_id}",
                    "",
                    f"- Severity: {finding.severity}",
                    f"- Title: {finding.title}",
                    f"- Description: {finding.description}",
                    f"- Recommendation: {finding.recommendation or 'None'}",
                    "",
                ]
            )
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Safety Limits",
            "",
            "- Human review evidence is not citizen-answer evidence.",
            "- First review alone is insufficient for high-risk domains.",
            "- Approved for publish preview is not published.",
            "- Local review evidence must not be committed.",
            "- No private reviewer identity is required.",
            "- No automatic registry writes.",
            "- Closed beta/public launch remain false.",
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def _report(
    path: Path,
    evidence_exists: bool,
    template_only: bool,
    status: str,
    items: list[OfficialSourceCandidateReviewEvidence],
    findings: list[OfficialSourceReviewEvidenceFinding],
) -> OfficialSourceReviewEvidenceReport:
    return OfficialSourceReviewEvidenceReport(
        evidence_path=str(path),
        evidence_exists=evidence_exists,
        template_only=template_only,
        status=status,
        total_evidence_items=len(items),
        first_review_count=sum(1 for item in items if item.review_round == "first_review"),
        second_review_count=sum(1 for item in items if item.review_round == "second_review"),
        approved_for_preview_count=sum(1 for item in items if _complete_for_preview(item)),
        needs_changes_count=sum(1 for item in items if item.decision == "needs_changes"),
        rejected_count=sum(1 for item in items if item.decision == "rejected"),
        blocker_count=sum(1 for finding in findings if finding.severity == "blocker"),
        warning_count=sum(1 for finding in findings if finding.severity == "warning"),
        findings=findings,
        evidence_items=items,
        sanitized_summary=_sanitized_summary(items),
        ready_for_closed_beta=False,
        ready_for_public_launch=False,
        used_network=False,
        used_external_provider=False,
        notes=[
            "Official source human review evidence is local and review-only.",
            "Human review evidence is not trusted citizen-answer evidence.",
            "Approved-for-preview evidence is not source publishing.",
            "No trusted data/sources/*.jsonl files were modified.",
            "No network, provider, OCR, or source publishing was used.",
        ],
    )


def _raw_evidence_items(data: dict) -> list[Any]:
    raw_items = data.get("evidence_items")
    if isinstance(raw_items, list):
        return raw_items
    if isinstance(raw_items, dict):
        return [raw_items]
    if any(key in data for key in ("candidate_id", "reviewer_role", "decision")):
        return [data]
    return []


def _evidence_item_from_raw(
    raw_item: dict,
    index: int,
) -> OfficialSourceCandidateReviewEvidence:
    return OfficialSourceCandidateReviewEvidence(
        candidate_id=_safe_text(raw_item.get("candidate_id")) or f"unknown-candidate-{index}",
        reviewer_role=_safe_text(raw_item.get("reviewer_role")) or "unknown_reviewer_role",
        review_round=_safe_round(raw_item.get("review_round")),
        official_publisher_verified=bool(raw_item.get("official_publisher_verified")),
        url_or_document_captured=bool(raw_item.get("url_or_document_captured")),
        trust_tier_classified=bool(raw_item.get("trust_tier_classified")),
        domain_scope_confirmed=bool(raw_item.get("domain_scope_confirmed")),
        freshness_checked=bool(raw_item.get("freshness_checked")),
        source_version_recorded=bool(raw_item.get("source_version_recorded")),
        no_conflict_with_existing_sources=bool(
            raw_item.get("no_conflict_with_existing_sources")
        ),
        reviewer_notes_present=bool(raw_item.get("reviewer_notes_present")),
        high_risk_second_review_completed=bool(
            raw_item.get("high_risk_second_review_completed")
        ),
        decision=_safe_decision(raw_item.get("decision")),
        allowed_claim_types=_safe_list(raw_item.get("allowed_claim_types")),
        prohibited_claim_types=_safe_list(raw_item.get("prohibited_claim_types")),
        required_warnings=_safe_list(raw_item.get("required_warnings")),
        sanitized_reviewer_notes=[
            _sanitize_note(note) for note in _raw_notes(raw_item)
        ],
        reviewed_at=_safe_text(raw_item.get("reviewed_at")),
        not_trusted_until_published=True,
    )


def _safe_round(value: Any) -> str:
    text = _safe_text(value) or "first_review"
    if text not in {"first_review", "second_review"}:
        return "first_review"
    return text


def _safe_decision(value: Any) -> str:
    text = _safe_text(value) or "pending"
    if text not in {"pending", "needs_changes", "rejected", "approved_for_preview"}:
        return "pending"
    return text


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_safe_text(item) for item in value) if text]


def _raw_notes(raw_item: dict) -> list[Any]:
    notes = raw_item.get("sanitized_reviewer_notes", raw_item.get("reviewer_notes", []))
    if isinstance(notes, list):
        return notes
    if notes:
        return [notes]
    return []


def _sanitize_note(value: Any) -> str:
    text = _safe_text(value)
    if not text or text == "[redacted]":
        return "[redacted]"
    return "[reviewer note present]"


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    if not stripped:
        return None
    if _sensitive_category(stripped) is not None:
        return "[redacted]"
    return stripped


def _missing_required_metadata(item: OfficialSourceCandidateReviewEvidence) -> list[str]:
    missing: list[str] = []
    if not item.candidate_id or item.candidate_id.startswith("unknown-candidate"):
        missing.append("candidate_id")
    if not item.reviewer_role or item.reviewer_role == "unknown_reviewer_role":
        missing.append("reviewer_role")
    if item.review_round not in {"first_review", "second_review"}:
        missing.append("review_round")
    if item.decision not in {"pending", "needs_changes", "rejected", "approved_for_preview"}:
        missing.append("decision")
    if not item.reviewer_notes_present:
        missing.append("reviewer_notes_present")
    return missing


def _complete_for_preview(item: OfficialSourceCandidateReviewEvidence) -> bool:
    return all(
        [
            item.decision == "approved_for_preview",
            item.official_publisher_verified,
            item.url_or_document_captured,
            item.trust_tier_classified,
            item.domain_scope_confirmed,
            item.freshness_checked,
            item.source_version_recorded,
            item.no_conflict_with_existing_sources,
            item.reviewer_notes_present,
            item.high_risk_second_review_completed,
        ]
    )


def _status_for_report(
    template_only: bool,
    items: list[OfficialSourceCandidateReviewEvidence],
    findings: list[OfficialSourceReviewEvidenceFinding],
) -> str:
    if any(finding.finding_id.startswith("REVIEW-EVIDENCE-SECRET") for finding in findings):
        return "blocked_secret_pattern"
    if any(finding.finding_id.startswith("REVIEW-EVIDENCE-SENSITIVE") for finding in findings):
        return "blocked_sensitive_data"
    if any(finding.severity == "blocker" for finding in findings):
        return "invalid"
    if template_only:
        return "template_only"
    if items and all(not _missing_required_metadata(item) for item in items):
        return "ready_for_review_application"
    return "valid_metadata_only"


def _iter_string_values(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_string_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_string_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _sensitive_category(value: str) -> str | None:
    if EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
        return "sensitive"
    if (
        SECRET_TERM_PATTERN.search(value)
        or SK_KEY_PATTERN.search(value)
        or PRIVATE_KEY_PATTERN.search(value)
        or _looks_high_entropy_secret(value)
    ):
        return "secret"
    return None


def _looks_high_entropy_secret(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 32 or compact.startswith(("http://", "https://")):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_+=/.-]+", compact):
        return False
    unique_ratio = len(set(compact)) / len(compact)
    if unique_ratio < 0.45:
        return False
    return _shannon_entropy(compact) > 4.0


def _shannon_entropy(value: str) -> float:
    counts = {character: value.count(character) for character in set(value)}
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _sanitized_summary(
    items: list[OfficialSourceCandidateReviewEvidence],
) -> dict[str, object]:
    return {
        "candidate_ids": _unique([item.candidate_id for item in items]),
        "reviewer_roles": _unique([item.reviewer_role for item in items]),
        "not_trusted_until_published_count": sum(
            1 for item in items if item.not_trusted_until_published
        ),
    }


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
