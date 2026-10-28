from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator

from backend.app.official_source_review.intake import (
    OfficialSourceIntakeCandidate,
    OfficialSourceIntakeService,
)
from backend.app.official_source_review.review_evidence import (
    OfficialSourceCandidateReviewEvidence,
    OfficialSourceReviewEvidenceReport,
    OfficialSourceReviewEvidenceService,
)
from backend.app.official_source_review.service import HIGH_RISK_DOMAINS

BlockerSeverity = Literal["warning", "blocker"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OfficialSourcePublishPreviewBlocker(BaseModel):
    blocker_id: str
    severity: BlockerSeverity
    candidate_id: str | None
    title: str
    description: str
    required_action: str


class OfficialSourcePublishPreviewCandidate(BaseModel):
    candidate_id: str
    domain: str
    proposed_trust_tier: str
    source_title: str | None = None
    sanitized_source_reference: str | None = None
    intake_ready: bool = False
    review_evidence_present: bool = False
    human_review_complete: bool = False
    high_risk_second_review_complete: bool = False
    freshness_checked: bool = False
    source_version_recorded: bool = False
    no_conflict_with_existing_sources: bool = False
    eligible_for_publish_preview: bool = False
    not_trusted_until_published: bool = True
    blockers: list[OfficialSourcePublishPreviewBlocker] = Field(default_factory=list)


class OfficialSourcePublishPreviewGateReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    intake_status: str
    review_evidence_status: str
    total_candidates: int
    eligible_for_preview_count: int
    blocked_count: int
    blocker_count: int
    high_risk_candidate_count: int
    preview_package_created: bool
    registry_write_performed: bool = False
    published_count: int = 0
    publish_preview_is_trusted_evidence: bool = False
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    candidates: list[OfficialSourcePublishPreviewCandidate]
    blockers: list[OfficialSourcePublishPreviewBlocker]
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class OfficialSourcePublishPreviewGateService:
    def __init__(
        self,
        project_root: Path | str = ".",
        intake_path: Path | str | None = None,
        review_evidence_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.intake_path = Path(intake_path) if intake_path is not None else None
        self.review_evidence_path = (
            Path(review_evidence_path) if review_evidence_path is not None else None
        )
        self._current_intake_status = "missing"
        self._current_review_evidence_status = "missing"
        self._current_review_evidence_usable = False
        self._current_review_evidence_is_draft = False

    def build_report(self) -> OfficialSourcePublishPreviewGateReport:
        intake_status, intake_candidates = self._load_intake_candidates()
        (
            review_evidence_status,
            review_evidence_report,
            evidence_usable,
            evidence_is_draft,
        ) = self._load_review_evidence_report()

        self._current_intake_status = intake_status
        self._current_review_evidence_status = review_evidence_status
        self._current_review_evidence_usable = evidence_usable
        self._current_review_evidence_is_draft = evidence_is_draft

        evidence_by_candidate = (
            _latest_evidence_by_candidate(review_evidence_report.evidence_items)
            if evidence_usable and review_evidence_report is not None
            else {}
        )
        preview_candidates = [
            self.build_preview_candidate(
                candidate,
                evidence_by_candidate.get(_candidate_id(candidate)),
            )
            for candidate in intake_candidates
        ]
        blockers = [
            blocker
            for preview_candidate in preview_candidates
            for blocker in preview_candidate.blockers
        ]
        eligible_count = sum(
            1
            for preview_candidate in preview_candidates
            if preview_candidate.eligible_for_publish_preview
        )
        return OfficialSourcePublishPreviewGateReport(
            intake_status=intake_status,
            review_evidence_status=review_evidence_status,
            total_candidates=len(preview_candidates),
            eligible_for_preview_count=eligible_count,
            blocked_count=len(preview_candidates) - eligible_count,
            blocker_count=len(blockers),
            high_risk_candidate_count=sum(
                1 for candidate in preview_candidates if _is_high_risk(candidate.domain)
            ),
            preview_package_created=eligible_count > 0,
            registry_write_performed=False,
            published_count=0,
            publish_preview_is_trusted_evidence=False,
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            candidates=preview_candidates,
            blockers=blockers,
            notes=[
                "Publish preview eligibility is not publishing and is not trusted "
                "citizen-answer evidence.",
                "Publish preview packages contain eligible candidates only and remain "
                "untrusted until controlled publishing updates trusted registry data.",
                "Complete human review evidence is required before a candidate can enter "
                "a publish preview package.",
                "High-risk domains require independent second review before publish "
                "preview eligibility.",
                "Reviewer packets and generated draft evidence cannot satisfy review "
                "evidence.",
                "No trusted data/sources/*.jsonl files were modified.",
                "Closed beta and public launch remain false.",
                "No network, provider, OCR, publishing, or registry write occurred.",
            ],
        )

    def build_preview_candidate(
        self,
        candidate: OfficialSourceIntakeCandidate,
        evidence_item: OfficialSourceCandidateReviewEvidence | None,
    ) -> OfficialSourcePublishPreviewCandidate:
        candidate_id = _candidate_id(candidate)
        domain = _safe_text(candidate.domain) or "unknown"
        trust_tier = _safe_text(candidate.proposed_trust_tier) or "unknown"
        blockers: list[OfficialSourcePublishPreviewBlocker] = []
        intake_ready = self._current_intake_status == "ready_for_review"
        evidence_present = (
            self._current_review_evidence_usable
            and evidence_item is not None
            and not self._current_review_evidence_is_draft
        )

        if not intake_ready:
            blockers.append(
                _blocker(
                    "PUBLISH-PREVIEW-INTAKE-NOT-READY",
                    candidate_id,
                    "Candidate intake is not ready for review.",
                    (
                        "Publish preview requires validated local intake metadata with "
                        "status=ready_for_review."
                    ),
                    "Complete and inspect intake metadata before publish preview review.",
                )
            )

        if self._current_review_evidence_is_draft:
            blockers.append(
                _blocker(
                    "PUBLISH-PREVIEW-DRAFT-EVIDENCE",
                    candidate_id,
                    "Reviewer packet draft evidence cannot be used.",
                    (
                        "Generated reviewer-packet evidence is draft-only preparation "
                        "material, not completed human review evidence."
                    ),
                    "Record real local human review evidence after human review.",
                )
            )

        if not evidence_present:
            blockers.append(
                _blocker(
                    "PUBLISH-PREVIEW-REVIEW-EVIDENCE-MISSING",
                    candidate_id,
                    "Complete human review evidence is missing.",
                    (
                        "Publish preview requires a matching non-template, non-secret, "
                        "non-draft review evidence item."
                    ),
                    "Provide reviewed local evidence with a matching candidate ID.",
                )
            )

        official_publisher_verified = bool(
            evidence_item.official_publisher_verified if evidence_present else False
        )
        url_or_document_captured = bool(
            evidence_item.url_or_document_captured if evidence_present else False
        )
        trust_tier_classified = bool(
            evidence_item.trust_tier_classified if evidence_present else False
        )
        domain_scope_confirmed = bool(
            evidence_item.domain_scope_confirmed if evidence_present else False
        )
        freshness_checked = bool(
            evidence_item.freshness_checked if evidence_present else False
        )
        source_version_recorded = bool(
            evidence_item.source_version_recorded if evidence_present else False
        )
        no_conflict_with_existing_sources = bool(
            evidence_item.no_conflict_with_existing_sources if evidence_present else False
        )
        reviewer_notes_present = bool(
            evidence_item.reviewer_notes_present if evidence_present else False
        )
        decision_approved = bool(
            evidence_item is not None
            and evidence_present
            and evidence_item.decision == "approved_for_preview"
        )
        high_risk_second_review_complete = bool(
            evidence_item is not None
            and evidence_present
            and evidence_item.review_round == "second_review"
            and evidence_item.high_risk_second_review_completed
        )

        for blocker_id, passed, title, description, action in [
            (
                "PUBLISH-PREVIEW-PUBLISHER-NOT-VERIFIED",
                official_publisher_verified,
                "Official publisher is not verified.",
                "A URL or claimed publisher does not prove official status.",
                "Have a human reviewer verify the official publisher.",
            ),
            (
                "PUBLISH-PREVIEW-SOURCE-NOT-CAPTURED",
                url_or_document_captured,
                "Source URL or document capture is missing.",
                "The reviewer must capture the source URL or authoritative document reference.",
                "Record the captured URL or document in human review evidence.",
            ),
            (
                "PUBLISH-PREVIEW-TRUST-TIER-NOT-CLASSIFIED",
                trust_tier_classified,
                "Trust tier classification is incomplete.",
                "The proposed trust tier must be confirmed during human review.",
                "Classify the source into the correct official trust tier.",
            ),
            (
                "PUBLISH-PREVIEW-DOMAIN-SCOPE-NOT-CONFIRMED",
                domain_scope_confirmed,
                "Domain scope is not confirmed.",
                "The reviewer has not confirmed that the source covers the candidate domain.",
                "Confirm exact domain and jurisdiction/scope coverage.",
            ),
            (
                "PUBLISH-PREVIEW-FRESHNESS-NOT-CHECKED",
                freshness_checked,
                "Freshness check is missing.",
                "Publish preview requires a freshness or effective-date check.",
                "Record freshness, effective date, amendment, or review-date evidence.",
            ),
            (
                "PUBLISH-PREVIEW-VERSION-NOT-RECORDED",
                source_version_recorded,
                "Source version is not recorded.",
                (
                    "Publish preview requires source version, effective date, or "
                    "document version metadata."
                ),
                "Record source version metadata before preview packaging.",
            ),
            (
                "PUBLISH-PREVIEW-CONFLICT-NOT-CHECKED",
                no_conflict_with_existing_sources,
                "Conflict check is missing.",
                "The candidate has not been checked against existing trusted sources.",
                "Compare the candidate against current registry entries and record the result.",
            ),
            (
                "PUBLISH-PREVIEW-REVIEWER-NOTES-MISSING",
                reviewer_notes_present,
                "Reviewer notes are missing.",
                "Human review evidence must include a reviewer-notes-present marker.",
                "Add sanitized reviewer notes or an explicit notes-present marker.",
            ),
            (
                "PUBLISH-PREVIEW-DECISION-NOT-APPROVED",
                decision_approved,
                "Review decision is not approved_for_preview.",
                "Only explicit approved_for_preview evidence can enter a preview package.",
                "Record approved_for_preview only after all human review checks are complete.",
            ),
        ]:
            if evidence_present and not passed:
                blockers.append(
                    _blocker(blocker_id, candidate_id, title, description, action)
                )

        if _is_high_risk(domain) and not high_risk_second_review_complete:
            blockers.append(
                _blocker(
                    "PUBLISH-PREVIEW-HIGH-RISK-SECOND-REVIEW-MISSING",
                    candidate_id,
                    "High-risk second review is incomplete.",
                    (
                        "High-risk domains such as visa, residence registration, police, "
                        "work, medical, scam, passport, and emergency cases require "
                        "independent second review before publish preview eligibility."
                    ),
                    "Complete and record independent second review before preview packaging.",
                )
            )

        human_review_complete = all(
            [
                evidence_present,
                official_publisher_verified,
                url_or_document_captured,
                trust_tier_classified,
                domain_scope_confirmed,
                freshness_checked,
                source_version_recorded,
                no_conflict_with_existing_sources,
                reviewer_notes_present,
                decision_approved,
            ]
        )
        eligible = all(
            [
                intake_ready,
                human_review_complete,
                not _is_high_risk(domain) or high_risk_second_review_complete,
            ]
        )
        return OfficialSourcePublishPreviewCandidate(
            candidate_id=candidate_id,
            domain=domain,
            proposed_trust_tier=trust_tier,
            source_title=_safe_text(candidate.source_title),
            sanitized_source_reference=_sanitized_source_reference(candidate),
            intake_ready=intake_ready,
            review_evidence_present=evidence_present,
            human_review_complete=human_review_complete,
            high_risk_second_review_complete=high_risk_second_review_complete,
            freshness_checked=freshness_checked,
            source_version_recorded=source_version_recorded,
            no_conflict_with_existing_sources=no_conflict_with_existing_sources,
            eligible_for_publish_preview=eligible,
            not_trusted_until_published=True,
            blockers=[] if eligible else blockers,
        )

    def build_preview_package(
        self,
        report: OfficialSourcePublishPreviewGateReport,
    ) -> dict:
        eligible_candidates = [
            candidate
            for candidate in report.candidates
            if candidate.eligible_for_publish_preview
        ]
        return {
            "generated_at": report.generated_at.isoformat(),
            "package_type": "official_source_publish_preview_package",
            "candidate_count": len(eligible_candidates),
            "not_trusted_until_published": True,
            "registry_write_performed": False,
            "published_count": 0,
            "publish_preview_is_trusted_evidence": False,
            "ready_for_closed_beta": False,
            "ready_for_public_launch": False,
            "used_network": False,
            "used_external_provider": False,
            "warning": (
                "Publish preview package is not trusted evidence, is not publishing, "
                "and must not be cited in citizen answers."
            ),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "domain": candidate.domain,
                    "proposed_trust_tier": candidate.proposed_trust_tier,
                    "source_title": candidate.source_title,
                    "sanitized_source_reference": candidate.sanitized_source_reference,
                    "not_trusted_until_published": True,
                }
                for candidate in eligible_candidates
            ],
        }

    def _load_intake_candidates(self) -> tuple[str, list[OfficialSourceIntakeCandidate]]:
        if self.intake_path is None:
            return "missing", []
        intake_report = OfficialSourceIntakeService(
            self.project_root,
            intake_path=self.intake_path,
        ).generate_report()
        return intake_report.status, intake_report.candidates

    def _load_review_evidence_report(
        self,
    ) -> tuple[str, OfficialSourceReviewEvidenceReport | None, bool, bool]:
        if self.review_evidence_path is None:
            return "missing", None, False, False
        review_evidence_service = OfficialSourceReviewEvidenceService(
            self.project_root,
            evidence_path=self.review_evidence_path,
        )
        report = review_evidence_service.generate_report()
        is_draft = _evidence_path_is_reviewer_packet_draft(
            review_evidence_service,
            self.review_evidence_path,
        )
        usable = report.status == "ready_for_review_application" and not is_draft
        return report.status, report, usable, is_draft


def official_source_publish_preview_gate_report_to_jsonable(
    report: OfficialSourcePublishPreviewGateReport,
) -> dict:
    return report.model_dump(mode="json")


def official_source_publish_preview_gate_report_to_markdown(
    report: OfficialSourcePublishPreviewGateReport,
) -> str:
    lines = [
        "# Official Source Publish Preview Gate Report",
        "",
        "## Executive Decision",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Intake status: {report.intake_status}",
        f"- Review evidence status: {report.review_evidence_status}",
        f"- Total candidates: {report.total_candidates}",
        f"- Eligible for preview count: {report.eligible_for_preview_count}",
        f"- Blocked count: {report.blocked_count}",
        f"- Blocker count: {report.blocker_count}",
        f"- High-risk candidate count: {report.high_risk_candidate_count}",
        f"- Preview package created: {report.preview_package_created}",
        f"- Registry write performed: {report.registry_write_performed}",
        f"- Published count: {report.published_count}",
        (
            "- Publish preview is trusted evidence: "
            f"{report.publish_preview_is_trusted_evidence}"
        ),
        f"- Ready for closed beta: {report.ready_for_closed_beta}",
        f"- Ready for public launch: {report.ready_for_public_launch}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "Publish preview eligibility is not publishing and is not trusted citizen-answer evidence.",
        "",
        "## Publish Preview Scope",
        "",
        "- The gate evaluates whether reviewed candidates may enter an internal preview package.",
        "- It does not publish sources, write trusted registry entries, or certify legal status.",
        "- Source URL presence does not prove official status.",
        "- Metadata completeness is not approval.",
        "",
        "## Candidate Eligibility Table",
        "",
        (
            "| Candidate | Domain | Trust tier | Intake ready | Evidence present | "
            "Human review complete | High-risk second review complete | Eligible | Not trusted |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in report.candidates:
        lines.append(
            f"| {candidate.candidate_id} | {candidate.domain} | "
            f"{candidate.proposed_trust_tier} | {candidate.intake_ready} | "
            f"{candidate.review_evidence_present} | "
            f"{candidate.human_review_complete} | "
            f"{candidate.high_risk_second_review_complete} | "
            f"{candidate.eligible_for_publish_preview} | "
            f"{candidate.not_trusted_until_published} |"
        )

    lines.extend(["", "## Blockers Per Candidate", ""])
    if not report.candidates:
        lines.append("- No candidates were loaded.")
    for candidate in report.candidates:
        lines.extend([f"### {candidate.candidate_id}", ""])
        if candidate.blockers:
            for blocker in candidate.blockers:
                lines.extend(
                    [
                        f"- `{blocker.blocker_id}` ({blocker.severity}): {blocker.title}",
                        f"  Required action: {blocker.required_action}",
                    ]
                )
        else:
            lines.append("- No blockers for preview eligibility.")
        lines.append("")

    lines.extend(
        [
            "## High-Risk Second Review Requirement",
            "",
            "- High-risk domains require independent second review before publish "
            "preview eligibility.",
            "- First review alone is insufficient for visa, residence registration, "
            "police, work, medical, scam, passport, or emergency domains.",
            "",
            "## Missing Review Evidence Warning",
            "",
            "- Missing, template-only, invalid, secret-blocked, or draft review evidence "
            "blocks publish preview eligibility.",
            "- Reviewer packet draft evidence cannot satisfy human review evidence.",
            "",
            "## Preview Package Warning",
            "",
            "- A preview package is not trusted evidence.",
            "- A preview package must not be cited in citizen answers.",
            "- Only eligible candidates are included; blocked candidates remain excluded.",
            "",
            "## No Registry Write",
            "",
            "- No registry write occurred.",
            "- No trusted data/sources/*.jsonl file was modified.",
            "- Published count remains 0.",
            "",
            "## No Citizen-Answer Citation Before Publishing",
            "",
            "- Intake metadata, review evidence, review records, reviewer packets, and "
            "preview packages are not citizen-answer citation support.",
            "- Citizen-answer citations remain blocked until controlled publishing updates "
            "trusted registry data.",
            "",
            "## Launch And Execution Limits",
            "",
            "- Closed beta remains false.",
            "- Public launch remains false.",
            "- No network/provider used.",
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def _candidate_id(candidate: OfficialSourceIntakeCandidate) -> str:
    return f"official-source-candidate-{candidate.intake_id}"


def _blocker(
    blocker_id: str,
    candidate_id: str | None,
    title: str,
    description: str,
    required_action: str,
    severity: BlockerSeverity = "blocker",
) -> OfficialSourcePublishPreviewBlocker:
    return OfficialSourcePublishPreviewBlocker(
        blocker_id=blocker_id,
        severity=severity,
        candidate_id=candidate_id,
        title=title,
        description=description,
        required_action=required_action,
    )


def _latest_evidence_by_candidate(
    evidence_items: list[OfficialSourceCandidateReviewEvidence],
) -> dict[str, OfficialSourceCandidateReviewEvidence]:
    by_candidate: dict[str, OfficialSourceCandidateReviewEvidence] = {}
    for evidence_item in evidence_items:
        current = by_candidate.get(evidence_item.candidate_id)
        if current is None or _evidence_sort_key(evidence_item) >= _evidence_sort_key(current):
            by_candidate[evidence_item.candidate_id] = evidence_item
    return by_candidate


def _evidence_sort_key(
    evidence_item: OfficialSourceCandidateReviewEvidence,
) -> tuple[int, str]:
    round_rank = 1 if evidence_item.review_round == "second_review" else 0
    return round_rank, evidence_item.reviewed_at or ""


def _evidence_path_is_reviewer_packet_draft(
    review_evidence_service: OfficialSourceReviewEvidenceService,
    evidence_path: Path,
) -> bool:
    if not evidence_path.exists():
        return False
    try:
        data = review_evidence_service.load_evidence(evidence_path)
    except (OSError, ValueError):
        return False
    return bool(
        data.get("draft_only")
        or data.get("generated_by") == "official_source_reviewer_packet_workflow"
        or data.get("reviewer_packet_is_trusted_evidence") is False
    )


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
    return stripped


def _is_high_risk(domain: str) -> bool:
    return domain in HIGH_RISK_DOMAINS
