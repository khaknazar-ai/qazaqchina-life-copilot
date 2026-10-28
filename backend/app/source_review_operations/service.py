from pathlib import Path

from backend.app.official_source_review.publish_preview_gate import (
    OfficialSourcePublishPreviewCandidate,
    OfficialSourcePublishPreviewGateReport,
    OfficialSourcePublishPreviewGateService,
)
from backend.app.official_source_review.review_evidence import (
    OfficialSourceReviewEvidenceService,
)
from backend.app.official_source_review.reviewer_packet import (
    OfficialSourceReviewerPacketReport,
    OfficialSourceReviewerPacketService,
)
from backend.app.official_source_review.service import HIGH_RISK_DOMAINS
from backend.app.source_review_answer_constraints.models import (
    SourceReviewAnswerConstraint,
    SourceReviewAnswerConstraintsReport,
)
from backend.app.source_review_answer_constraints.service import (
    SourceReviewAnswerConstraintsService,
)
from backend.app.source_review_operations.models import (
    SourceReviewOperationAction,
    SourceReviewOperationCandidateStatus,
    SourceReviewOperationsDashboardReport,
)
from backend.app.source_review_regression.service import (
    SourceReviewConstraintRegressionService,
)


class SourceReviewOperationsDashboardService:
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

    def build_report(self) -> SourceReviewOperationsDashboardReport:
        review_evidence_status = self._review_evidence_status()
        reviewer_packet_report = OfficialSourceReviewerPacketService(
            self.project_root,
            intake_path=self.intake_path,
        ).build_report()
        publish_gate_report = OfficialSourcePublishPreviewGateService(
            self.project_root,
            intake_path=self.intake_path,
            review_evidence_path=self.review_evidence_path,
        ).build_report()
        answer_constraints_report = SourceReviewAnswerConstraintsService(
            self.project_root,
            intake_path=self.intake_path,
            review_evidence_path=self.review_evidence_path,
        ).build_report()
        regression_report = SourceReviewConstraintRegressionService(
            self.project_root
        ).run()

        candidate_statuses = self.build_candidate_statuses(
            publish_gate_report=publish_gate_report,
            reviewer_packet_report=reviewer_packet_report,
            answer_constraints_report=answer_constraints_report,
            review_evidence_status=review_evidence_status,
        )
        actions = [
            action
            for candidate_status in candidate_statuses
            for action in candidate_status.next_required_actions
        ]
        candidate_domains = {status.domain for status in candidate_statuses}
        constrained_candidate_domains = {
            status.domain
            for status in candidate_statuses
            if status.answer_constraint_mode
            and status.answer_constraint_mode != "direct_answer_allowed"
        }
        return SourceReviewOperationsDashboardReport(
            total_candidates=len(candidate_statuses),
            total_domains=len(candidate_domains),
            blocked_candidate_count=sum(
                not status.publish_preview_eligible for status in candidate_statuses
            ),
            publish_preview_eligible_count=sum(
                status.publish_preview_eligible for status in candidate_statuses
            ),
            published_count=0,
            trusted_for_citizen_answers_count=0,
            constrained_domain_count=len(constrained_candidate_domains),
            critical_action_count=sum(action.priority == "critical" for action in actions),
            high_action_count=sum(action.priority == "high" for action in actions),
            operator_ready_count=sum(
                status.intake_ready and status.reviewer_packet_available
                for status in candidate_statuses
            ),
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            candidate_statuses=candidate_statuses,
            actions=actions,
            notes=[
                "Admin source review operations status is not citizen-facing source authority.",
                "Source candidates, reviewer packets, review evidence, and publish preview "
                "packages are not trusted citizen-answer evidence.",
                "Candidate published and trusted-for-citizen-answer flags remain false.",
                "Publish preview eligibility is not publishing and no registry write occurred.",
                "Citizen answer constraints are represented as admin-only impact.",
                "Closed beta and public launch remain false.",
                "No network, external provider, OCR, source publishing, or trusted registry "
                "write occurred.",
                (
                    "Source review regression summary: "
                    f"total_cases={regression_report.total_cases}, "
                    f"failed_cases={regression_report.failed_cases}, "
                    "unpublished_candidate_citation_count="
                    f"{regression_report.unpublished_candidate_citation_count}."
                ),
            ],
        )

    def build_candidate_statuses(
        self,
        *,
        publish_gate_report: OfficialSourcePublishPreviewGateReport,
        reviewer_packet_report: OfficialSourceReviewerPacketReport,
        answer_constraints_report: SourceReviewAnswerConstraintsReport,
        review_evidence_status: str,
    ) -> list[SourceReviewOperationCandidateStatus]:
        packet_candidate_ids = {
            packet_item.candidate_id for packet_item in reviewer_packet_report.packet_items
        }
        constraints_by_domain = {
            constraint.domain: constraint
            for constraint in answer_constraints_report.constraints
        }
        statuses: list[SourceReviewOperationCandidateStatus] = []
        for candidate in publish_gate_report.candidates:
            constraint = constraints_by_domain.get(candidate.domain)
            reviewer_packet_available = candidate.candidate_id in packet_candidate_ids
            actions = self.build_actions_for_candidate(
                candidate=candidate,
                review_evidence_status=review_evidence_status,
                reviewer_packet_available=reviewer_packet_available,
                constraint=constraint,
            )
            statuses.append(
                SourceReviewOperationCandidateStatus(
                    candidate_id=candidate.candidate_id,
                    domain=candidate.domain,
                    proposed_trust_tier=candidate.proposed_trust_tier,
                    intake_ready=candidate.intake_ready,
                    review_evidence_present=candidate.review_evidence_present,
                    reviewer_packet_available=reviewer_packet_available,
                    publish_preview_eligible=candidate.eligible_for_publish_preview,
                    published=False,
                    trusted_for_citizen_answers=False,
                    answer_constraint_mode=(
                        constraint.allowed_mode if constraint is not None else None
                    ),
                    citizen_visible_source_disclosure_allowed=False,
                    blocker_count=len(candidate.blockers),
                    next_required_actions=actions,
                    admin_only_notes=_admin_only_notes(
                        candidate=candidate,
                        review_evidence_status=review_evidence_status,
                        reviewer_packet_available=reviewer_packet_available,
                        constraint=constraint,
                    ),
                )
            )
        return statuses

    def build_actions_for_candidate(
        self,
        *,
        candidate: OfficialSourcePublishPreviewCandidate,
        review_evidence_status: str,
        reviewer_packet_available: bool,
        constraint: SourceReviewAnswerConstraint | None,
    ) -> list[SourceReviewOperationAction]:
        actions: list[SourceReviewOperationAction] = []
        if not candidate.intake_ready:
            actions.append(
                _action(
                    "complete-source-intake",
                    "high",
                    candidate,
                    "Complete source intake metadata.",
                    "Complete and validate official-source intake metadata before review.",
                    "source_reviewer",
                )
            )
        if not reviewer_packet_available:
            actions.append(
                _action(
                    "generate-reviewer-packet",
                    "medium",
                    candidate,
                    "Generate reviewer packet.",
                    (
                        "Prepare operator-only verification questions and required checks. "
                        "Reviewer packets remain non-evidence."
                    ),
                    "source_reviewer",
                )
            )
        if not candidate.review_evidence_present:
            actions.append(
                _action(
                    "record-human-review-evidence",
                    "high",
                    candidate,
                    "Collect and record human review evidence.",
                    (
                        "Collect/verify official publisher evidence, record source version "
                        "or effective date, freshness, scope, conflicts, and sanitized "
                        f"reviewer notes. Current review evidence status: {review_evidence_status}."
                    ),
                    "source_reviewer",
                )
            )
        if _is_high_risk(candidate.domain) and not candidate.high_risk_second_review_complete:
            actions.append(
                _action(
                    "complete-high-risk-second-review",
                    "critical",
                    candidate,
                    "Complete high-risk second review.",
                    (
                        "High-risk domains require independent second review before publish "
                        "preview eligibility or direct citizen-answer certainty."
                    ),
                    "senior_source_reviewer",
                )
            )
        if candidate.blockers:
            actions.append(
                _action(
                    "resolve-publish-preview-blockers",
                    "high",
                    candidate,
                    "Resolve publish preview blockers.",
                    (
                        "Resolve blocked publish preview requirements. Publish preview is "
                        "not publishing and remains non-citeable."
                    ),
                    "source_reviewer",
                )
            )
        if constraint is not None and constraint.allowed_mode != "direct_answer_allowed":
            actions.append(
                _action(
                    "keep-citizen-answers-constrained",
                    "medium",
                    candidate,
                    "Keep citizen answers constrained.",
                    (
                        "Citizen answers must remain cautious until published official "
                        f"coverage exists. Current mode: {constraint.allowed_mode}."
                    ),
                    "safety_reviewer",
                    blocks_publish_preview=False,
                    blocks_citizen_direct_answer=True,
                )
            )
        if not candidate.eligible_for_publish_preview:
            actions.append(
                _action(
                    "publish-through-later-registry-workflow",
                    "low",
                    candidate,
                    "Publish through reviewed registry workflow in a later phase.",
                    (
                        "Do not write the trusted registry in this phase. Use a later "
                        "reviewed publishing workflow only after all blockers are resolved."
                    ),
                    "source_publisher",
                    blocks_publish_preview=False,
                    blocks_citizen_direct_answer=True,
                )
            )
        return actions

    def _review_evidence_status(self) -> str:
        if self.review_evidence_path is None:
            return "missing"
        return OfficialSourceReviewEvidenceService(
            self.project_root,
            evidence_path=self.review_evidence_path,
        ).generate_report().status


def _action(
    action_suffix: str,
    priority: str,
    candidate: OfficialSourcePublishPreviewCandidate,
    title: str,
    description: str,
    owner_role: str,
    *,
    blocks_publish_preview: bool = True,
    blocks_citizen_direct_answer: bool = True,
) -> SourceReviewOperationAction:
    return SourceReviewOperationAction(
        action_id=f"{action_suffix}-{candidate.candidate_id}",
        priority=priority,
        domain=candidate.domain,
        candidate_id=candidate.candidate_id,
        title=title,
        description=description,
        owner_role=owner_role,
        blocks_publish_preview=blocks_publish_preview,
        blocks_citizen_direct_answer=blocks_citizen_direct_answer,
    )


def _admin_only_notes(
    *,
    candidate: OfficialSourcePublishPreviewCandidate,
    review_evidence_status: str,
    reviewer_packet_available: bool,
    constraint: SourceReviewAnswerConstraint | None,
) -> list[str]:
    notes = [
        "Admin-only operations status; not citizen-facing source authority.",
        "Candidate is not published and is not trusted for citizen answers.",
        f"Review evidence status is {review_evidence_status}.",
        f"Reviewer packet available: {reviewer_packet_available}.",
        f"Publish preview eligible: {candidate.eligible_for_publish_preview}.",
    ]
    if constraint is not None:
        notes.append(
            "Citizen answer impact is constrained by "
            f"{constraint.allowed_mode}; this is not source trust."
        )
        if constraint.admin_only_notes:
            notes.extend(constraint.admin_only_notes)
    if candidate.blockers:
        notes.append(
            f"{len(candidate.blockers)} publish preview blocker(s) require operator action."
        )
    return notes


def _is_high_risk(domain: str) -> bool:
    return domain in HIGH_RISK_DOMAINS
