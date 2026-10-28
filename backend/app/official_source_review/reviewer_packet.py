import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator

from backend.app.official_source_review.intake import (
    OfficialSourceIntakeCandidate,
    OfficialSourceIntakeService,
)
from backend.app.official_source_review.service import HIGH_RISK_DOMAINS

SECRET_TERM_PATTERN = re.compile(
    r"\b(api[_-]?key|token|secret|password|bearer|openai_api_key|google_api_key)\b",
    re.IGNORECASE,
)

DEFAULT_PROHIBITED_CLAIMS = [
    "legal certainty",
    "immigration or residence-status certainty",
    "deadline certainty",
    "required document certainty",
    "official procedure certainty",
    "penalty or enforcement certainty",
]

DOMAIN_PROHIBITED_CLAIMS = {
    "visa_extension": [
        "legal or immigration-status certainty",
        "visa extension eligibility certainty",
        "visa or stay deadline certainty",
        "required document certainty",
        "official filing procedure certainty",
        "penalty or enforcement certainty",
    ],
    "residence_registration": [
        "legal or residence-status certainty",
        "police registration deadline certainty",
        "required document certainty",
        "official filing procedure certainty",
        "penalty or enforcement certainty",
    ],
    "police_registration": [
        "legal or residence-status certainty",
        "police registration deadline certainty",
        "required document certainty",
        "official filing procedure certainty",
        "penalty or enforcement certainty",
    ],
    "work_contract": [
        "work authorization legality",
        "employment status certainty",
        "contract enforceability certainty",
    ],
    "medical_or_hospital": [
        "medical diagnosis",
        "treatment certainty",
        "hospital admission or insurance certainty",
    ],
    "payment_or_scam": [
        "guaranteed refund path",
        "official police or bank procedure certainty",
        "fraud classification certainty",
    ],
    "lost_passport": [
        "official emergency procedure certainty",
        "guaranteed consular response",
        "official document replacement procedure certainty",
    ],
    "emergency": [
        "official emergency procedure certainty",
        "guaranteed human response",
        "official consular procedure certainty",
    ],
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OfficialSourceReviewerQuestion(BaseModel):
    question_id: str
    category: str
    prompt: str
    required: bool = True
    blocks_preview_if_unanswered: bool = True


class OfficialSourceReviewerPacketItem(BaseModel):
    candidate_id: str
    domain: str
    proposed_trust_tier: str
    source_title: str | None = None
    sanitized_source_reference: str | None = None
    verification_questions: list[OfficialSourceReviewerQuestion]
    required_documents_or_checks: list[str]
    prohibited_until_verified: list[str]
    allowed_after_review_preview: list[str]
    high_risk_second_review_required: bool = True
    recommended_initial_decision: str = "pending"
    not_trusted_until_published: bool = True
    notes: list[str] = Field(default_factory=list)


class OfficialSourceReviewerPacketReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    intake_status: str
    total_packet_items: int
    high_risk_items: int
    ready_for_human_review_count: int
    generated_draft_evidence_count: int
    approval_count: int = 0
    published_count: int = 0
    reviewer_packet_is_trusted_evidence: bool = False
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    packet_items: list[OfficialSourceReviewerPacketItem]
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class OfficialSourceReviewerPacketService:
    def __init__(
        self,
        project_root: Path | str = ".",
        intake_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.intake_path = Path(intake_path) if intake_path is not None else None

    def build_report(self) -> OfficialSourceReviewerPacketReport:
        intake_status, candidates = self._load_candidates()
        packet_items = [self.build_packet_item(candidate) for candidate in candidates]
        return OfficialSourceReviewerPacketReport(
            intake_status=intake_status,
            total_packet_items=len(packet_items),
            high_risk_items=sum(1 for item in packet_items if _is_high_risk(item.domain)),
            ready_for_human_review_count=len(packet_items),
            generated_draft_evidence_count=len(packet_items),
            approval_count=0,
            published_count=0,
            reviewer_packet_is_trusted_evidence=False,
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            packet_items=packet_items,
            notes=[
                "Reviewer packets are not trusted evidence and must not be cited in "
                "citizen answers.",
                "A generated packet is a human-review preparation artifact only.",
                "Generated draft evidence is pending-only and does not claim review completion.",
                "No approval, publishing, trusted registry write, network, provider, or "
                "OCR occurred.",
                "Closed beta and public launch remain false.",
                "Local intake and local review evidence files must not be committed.",
            ],
        )

    def build_packet_item(
        self,
        candidate: OfficialSourceIntakeCandidate,
    ) -> OfficialSourceReviewerPacketItem:
        domain = _safe_text(candidate.domain) or "unknown"
        trust_tier = _safe_text(candidate.proposed_trust_tier) or "unknown"
        return OfficialSourceReviewerPacketItem(
            candidate_id=f"official-source-candidate-{candidate.intake_id}",
            domain=domain,
            proposed_trust_tier=trust_tier,
            source_title=_safe_text(candidate.source_title),
            sanitized_source_reference=_sanitized_source_reference(candidate),
            verification_questions=_verification_questions(domain),
            required_documents_or_checks=_required_documents_or_checks(domain),
            prohibited_until_verified=_prohibited_until_verified(domain),
            allowed_after_review_preview=[
                "internal publish-preview metadata after all human checks pass",
                "source-scoped draft claims for later registry approval only",
                "no citizen-facing factual claims until controlled publishing is complete",
            ],
            high_risk_second_review_required=True,
            recommended_initial_decision="pending",
            not_trusted_until_published=True,
            notes=[
                "Generated from local intake metadata for human reviewer preparation.",
                "Metadata completeness is not approval.",
                "Source URL presence does not prove official status.",
                "The candidate remains untrusted until human review, publish approval, "
                "registry update, and source refresh operations are complete.",
                "Reviewer packet content must not be cited in citizen answers.",
                *_domain_notes(domain),
            ],
        )

    def build_draft_review_evidence(
        self,
        report: OfficialSourceReviewerPacketReport,
    ) -> dict:
        items = []
        for packet_item in report.packet_items:
            items.append(
                {
                    "candidate_id": packet_item.candidate_id,
                    "reviewer_role": "human_reviewer_required",
                    "review_round": "first_review",
                    "official_publisher_verified": False,
                    "url_or_document_captured": False,
                    "trust_tier_classified": False,
                    "domain_scope_confirmed": False,
                    "freshness_checked": False,
                    "source_version_recorded": False,
                    "no_conflict_with_existing_sources": False,
                    "reviewer_notes_present": False,
                    "high_risk_second_review_completed": False,
                    "decision": _draft_decision(packet_item.recommended_initial_decision),
                    "allowed_claim_types": [],
                    "prohibited_claim_types": packet_item.prohibited_until_verified,
                    "required_warnings": [
                        "Generated draft evidence is not human review evidence.",
                        "Do not use this draft to approve, publish, or cite a source.",
                        "Official publisher, freshness, source version, and conflicts "
                        "must be filled only after human review.",
                    ],
                    "sanitized_reviewer_notes": [],
                    "reviewed_at": None,
                    "not_trusted_until_published": True,
                    "draft_packet_questions": [
                        question.model_dump(mode="json")
                        for question in packet_item.verification_questions
                    ],
                }
            )
        return {
            "generated_at": report.generated_at.isoformat(),
            "generated_by": "official_source_reviewer_packet_workflow",
            "draft_only": True,
            "reviewer_packet_is_trusted_evidence": False,
            "warning": (
                "Generated draft evidence is pending only, is not human review evidence, "
                "and must not be cited in citizen answers."
            ),
            "approval_count": 0,
            "published_count": 0,
            "ready_for_closed_beta": False,
            "ready_for_public_launch": False,
            "used_network": False,
            "used_external_provider": False,
            "evidence_items": items,
        }

    def _load_candidates(self) -> tuple[str, list[OfficialSourceIntakeCandidate]]:
        if self.intake_path is None:
            return "missing", []
        intake_report = OfficialSourceIntakeService(
            self.project_root,
            intake_path=self.intake_path,
        ).generate_report()
        if intake_report.status != "ready_for_review":
            return intake_report.status, []
        return intake_report.status, intake_report.candidates


def official_source_reviewer_packet_report_to_jsonable(
    report: OfficialSourceReviewerPacketReport,
) -> dict:
    return report.model_dump(mode="json")


def official_source_reviewer_packet_report_to_markdown(
    report: OfficialSourceReviewerPacketReport,
) -> str:
    lines = [
        "# Official Source Reviewer Packet Report",
        "",
        "## Executive Decision",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Intake status: {report.intake_status}",
        f"- Total packet items: {report.total_packet_items}",
        f"- High-risk items: {report.high_risk_items}",
        f"- Ready for human review count: {report.ready_for_human_review_count}",
        f"- Generated draft evidence count: {report.generated_draft_evidence_count}",
        f"- Approval count: {report.approval_count}",
        f"- Published count: {report.published_count}",
        (
            "- Reviewer packet is trusted evidence: "
            f"{report.reviewer_packet_is_trusted_evidence}"
        ),
        f"- Ready for closed beta: {report.ready_for_closed_beta}",
        f"- Ready for public launch: {report.ready_for_public_launch}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "Reviewer packets are not trusted evidence and must not be cited in citizen answers.",
        "No approval, no publishing, and no trusted registry write occurred.",
        "",
        "## Reviewer Packet Scope",
        "",
        "- The packet converts validated local intake metadata into human-review checklists.",
        "- It does not verify URLs, crawl pages, search the internet, call providers, or run OCR.",
        "- Source URL presence does not prove official status.",
        "- Metadata completeness is not approval.",
        "- Local files must not be committed.",
        "",
        "## Per-Candidate Checklist",
        "",
    ]
    if not report.packet_items:
        lines.append("- No packet items were generated.")
    for item in report.packet_items:
        lines.extend(
            [
                f"### {item.candidate_id}",
                "",
                f"- Domain: {item.domain}",
                f"- Proposed trust tier: {item.proposed_trust_tier}",
                f"- Source title: {item.source_title or 'not captured'}",
                (
                    "- Sanitized source reference: "
                    f"{item.sanitized_source_reference or 'not captured'}"
                ),
                (
                    "- High-risk second review required: "
                    f"{item.high_risk_second_review_required}"
                ),
                f"- Recommended initial decision: {item.recommended_initial_decision}",
                f"- Not trusted until published: {item.not_trusted_until_published}",
                "",
                "Required documents or checks:",
            ]
        )
        lines.extend(f"- {check}" for check in item.required_documents_or_checks)
        lines.extend(["", "## High-Risk Second Review Requirement", ""])
        if item.high_risk_second_review_required:
            lines.append(
                "- Independent second review is required before any high-risk publish preview."
            )
        else:
            lines.append("- No high-risk second review flag was generated.")
        lines.extend(["", "## Verification Questions", ""])
        for question in item.verification_questions:
            lines.append(
                f"- `{question.question_id}` ({question.category}): {question.prompt}"
            )
        lines.extend(["", "## Prohibited Claims Until Review", ""])
        lines.extend(f"- {claim}" for claim in item.prohibited_until_verified)
        lines.extend(["", "Allowed after review preview only:", ""])
        lines.extend(f"- {claim}" for claim in item.allowed_after_review_preview)
        lines.extend(["", "Packet notes:", ""])
        lines.extend(f"- {note}" for note in item.notes)
        lines.append("")

    lines.extend(
        [
            "## Generated Evidence Draft Warning",
            "",
            "- Generated evidence draft items use `decision=pending` or `needs_changes` only.",
            "- Draft evidence does not set `official_publisher_verified=true`.",
            "- Draft evidence does not set `freshness_checked=true`.",
            "- Draft evidence does not set `source_version_recorded=true`.",
            "- A draft evidence file is not human review evidence.",
            "",
            "## No Approval/No Publishing",
            "",
            "- No approval occurred.",
            "- No publishing occurred.",
            "- No trusted registry write occurred.",
            "- No citizen-answer citation is allowed before publishing.",
            "",
            "## Launch And Execution Limits",
            "",
            "- Closed beta remains false.",
            "- Public launch remains false.",
            "- No network/provider used.",
            "- Local files must not be committed.",
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def _verification_questions(domain: str) -> list[OfficialSourceReviewerQuestion]:
    high_risk = _is_high_risk(domain)
    return [
        OfficialSourceReviewerQuestion(
            question_id="publisher-official-source",
            category="publisher",
            prompt="Is this publisher an official agency/law/regulation source?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="authoritative-chinese-version",
            category="language_authority",
            prompt="Is the Chinese authoritative version available?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="english-translation-status",
            category="translation",
            prompt="Is the English translation official or only reference?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="effective-date-version",
            category="freshness",
            prompt="What is the current effective date/version?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="amendments-local-rules",
            category="freshness",
            prompt="Are there amendments or local implementation rules?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="exact-domain-coverage",
            category="scope",
            prompt="Does the source cover the exact domain?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="registry-conflict-check",
            category="conflict",
            prompt="Does it conflict with existing source registry entries?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="safe-supported-claims",
            category="claims",
            prompt="What claim types can be safely supported?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="remaining-prohibited-claims",
            category="claims",
            prompt="What claim types remain prohibited?",
        ),
        OfficialSourceReviewerQuestion(
            question_id="high-risk-second-review",
            category="second_review",
            prompt=(
                "Is second review completed for this high-risk domain?"
                if high_risk
                else "Is second review required or waived by policy for this domain?"
            ),
        ),
    ]


def _required_documents_or_checks(domain: str) -> list[str]:
    checks = [
        "Manually verify publisher identity from the authoritative source page or document.",
        "Record authoritative Chinese title, publisher, URL/document reference, and jurisdiction.",
        "Record current effective date, version, amendment status, and freshness review date.",
        "Confirm the source covers the exact candidate domain and local scope.",
        "Compare against existing trusted registry entries for conflict or supersession.",
        "Record allowed claim types and prohibited claim types in reviewer notes.",
        "Use reviewer role labels only; do not record private reviewer identity or contact data.",
    ]
    if _is_high_risk(domain):
        checks.append(
            "Complete independent second review before any high-risk publish preview."
        )
    return checks


def _prohibited_until_verified(domain: str) -> list[str]:
    return DOMAIN_PROHIBITED_CLAIMS.get(domain, list(DEFAULT_PROHIBITED_CLAIMS))


def _domain_notes(domain: str) -> list[str]:
    if _is_high_risk(domain):
        return [
            "This is a high-risk domain; second review is mandatory before publish preview.",
            "High-risk citizen answers must remain cautious until published official "
            "evidence exists.",
        ]
    return ["Second review policy still needs an explicit reviewer decision."]


def _is_high_risk(domain: str) -> bool:
    return domain in HIGH_RISK_DOMAINS


def _draft_decision(value: str) -> str:
    if value in {"pending", "needs_changes"}:
        return value
    return "pending"


def _sanitized_source_reference(
    candidate: OfficialSourceIntakeCandidate,
) -> str | None:
    if candidate.source_url:
        return _sanitize_reference(candidate.source_url)
    if candidate.source_document_ref:
        return _sanitize_reference(candidate.source_document_ref)
    return None


def _sanitize_reference(value: str) -> str | None:
    text = _safe_text(value)
    if text is None:
        return None
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return text


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    if not stripped:
        return None
    if SECRET_TERM_PATTERN.search(stripped):
        return "[redacted]"
    return stripped
