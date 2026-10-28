from pathlib import Path

from backend.app.critical_source_gap_closure.models import CriticalGapClosurePlan
from backend.app.critical_source_gap_closure.service import CriticalSourceGapClosureService
from backend.app.official_source_review.intake import OfficialSourceIntakeService
from backend.app.official_source_review.models import (
    OfficialSourceCandidate,
    OfficialSourceReviewChecklist,
    OfficialSourceReviewRecord,
    OfficialSourceReviewSummary,
    utc_now,
)
from backend.app.official_source_review.review_evidence import (
    OfficialSourceCandidateReviewEvidence,
    OfficialSourceReviewEvidenceReport,
    OfficialSourceReviewEvidenceService,
)

HIGH_RISK_DOMAINS = {
    "lost_passport",
    "emergency",
    "visa_extension",
    "residence_registration",
    "police_registration",
    "medical_or_hospital",
    "payment_or_scam",
    "work_contract",
}

DEFAULT_PROHIBITED_CLAIMS = [
    "legal certainty",
    "visa or residence status certainty",
    "deadline certainty",
    "required document certainty",
    "official procedure certainty",
    "penalty or enforcement certainty",
]


class OfficialSourceReviewService:
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

    def create_candidate_templates_from_critical_gaps(
        self,
    ) -> list[OfficialSourceCandidate]:
        report = CriticalSourceGapClosureService(self.project_root).build_report()
        candidates: list[OfficialSourceCandidate] = []
        for plan in sorted(report.plans, key=lambda item: item.domain):
            if plan.closure_status == "closed":
                continue
            candidates.extend(_candidates_for_plan(plan))
        return candidates

    def create_candidates_from_local_intake(self) -> list[OfficialSourceCandidate]:
        if self.intake_path is None:
            return []
        intake_service = OfficialSourceIntakeService(
            self.project_root,
            intake_path=self.intake_path,
        )
        intake_report = intake_service.generate_report()
        if intake_report.status != "ready_for_review":
            return []
        candidates = intake_service.build_review_candidates(intake_report.candidates)
        for candidate in candidates:
            candidate.not_trusted_until_approved = True
            candidate.notes.extend(
                [
                    "Local intake metadata is not review approval.",
                    "Official publisher verification requires human review.",
                    "High-risk second review is required before publishing.",
                ]
            )
        return candidates

    def load_review_evidence_report(self) -> OfficialSourceReviewEvidenceReport | None:
        if self.review_evidence_path is None:
            return None
        return OfficialSourceReviewEvidenceService(
            self.project_root,
            evidence_path=self.review_evidence_path,
        ).generate_report()

    def build_initial_review_record(
        self,
        candidate: OfficialSourceCandidate,
    ) -> OfficialSourceReviewRecord:
        checklist = OfficialSourceReviewChecklist(
            candidate_id=candidate.candidate_id,
            url_or_document_captured=bool(
                candidate.source_url or candidate.source_document_ref
            ),
            trust_tier_classified=bool(candidate.proposed_trust_tier),
            domain_scope_confirmed=bool(candidate.domain),
            high_risk_second_review_required=candidate.domain in HIGH_RISK_DOMAINS,
            prohibited_if_missing=_prohibited_claim_types(candidate.domain),
        )
        return self.evaluate_candidate(candidate, checklist)

    def evaluate_candidate(
        self,
        candidate: OfficialSourceCandidate,
        checklist: OfficialSourceReviewChecklist,
    ) -> OfficialSourceReviewRecord:
        required_items_complete = _required_items_complete(candidate.domain, checklist)
        prohibited_claim_types = _prohibited_claim_types(candidate.domain)
        warnings = [
            "Official source candidates are not trusted evidence until approved and published.",
            "Candidate review records must not be cited in citizen answers as factual authority.",
            "This phase does not publish source registry entries.",
        ]

        if candidate.status == "rejected":
            decision = "rejected"
            next_status = "rejected"
            allowed_claim_types = ["none"]
            review_notes = ["Candidate was already marked rejected."]
        elif required_items_complete:
            decision = "approved_for_preview"
            next_status = "approved_for_publish_preview"
            allowed_claim_types = [
                "publish-preview metadata only",
                "source-scoped claim drafting for later registry approval",
            ]
            review_notes = [
                "Checklist is complete enough for publish preview only.",
                "Second review remains required before any high-risk publishing decision.",
            ]
        else:
            decision = _decision_for_incomplete_checklist(checklist)
            next_status = _status_for_incomplete_checklist(checklist)
            allowed_claim_types = ["none for citizen-facing factual authority"]
            review_notes = [
                "Candidate is blocked because required official evidence or review "
                "metadata is missing.",
                "It cannot close a critical gap or support citizen answers.",
            ]

        record = OfficialSourceReviewRecord(
            review_id=f"official-source-review-{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            reviewer_role="source_reviewer",
            decision=decision,
            checklist=checklist.model_copy(
                update={
                    "prohibited_if_missing": checklist.prohibited_if_missing
                    or prohibited_claim_types
                }
            ),
            allowed_claim_types=allowed_claim_types,
            prohibited_claim_types=[] if required_items_complete else prohibited_claim_types,
            required_warnings=warnings,
            review_notes=review_notes,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        candidate.status = next_status
        candidate.not_trusted_until_approved = True
        return record

    def summarize(
        self,
        candidates: list[OfficialSourceCandidate] | None = None,
    ) -> OfficialSourceReviewSummary:
        if candidates is not None:
            review_candidates = candidates
        elif self.intake_path is not None:
            review_candidates = self.create_candidates_from_local_intake()
        else:
            review_candidates = self.create_candidate_templates_from_critical_gaps()
        review_records = [
            self.build_initial_review_record(candidate) for candidate in review_candidates
        ]
        evidence_report = self.load_review_evidence_report()
        review_records = self._apply_review_evidence(
            review_candidates,
            review_records,
            evidence_report,
        )
        return OfficialSourceReviewSummary(
            total_candidates=len(review_candidates),
            draft_count=sum(1 for item in review_candidates if item.status == "draft"),
            blocked_count=sum(
                1
                for item in review_candidates
                if item.status == "blocked_needs_official_evidence"
            ),
            approved_for_preview_count=sum(
                1
                for item in review_candidates
                if item.status == "approved_for_publish_preview"
            ),
            published_count=0,
            critical_gap_candidate_count=sum(
                1 for item in review_candidates if item.related_gap_id is not None
            ),
            not_trusted_candidate_count=sum(
                1 for item in review_candidates if item.not_trusted_until_approved
            ),
            review_records=review_records,
            candidates=review_candidates,
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            notes=[
                "Official source candidate review is offline and manual-review oriented.",
                "Generated templates contain no invented URLs or official facts.",
                "Local intake metadata completeness is not review approval.",
                "Human review evidence, when provided locally, is review metadata only.",
                "Candidate records are not trusted evidence and must not be cited.",
                "No trusted data/sources/*.jsonl files were modified.",
                "No source publishing occurred in this phase.",
                "Closed beta and public launch remain false.",
            ],
        )

    def _apply_review_evidence(
        self,
        candidates: list[OfficialSourceCandidate],
        records: list[OfficialSourceReviewRecord],
        evidence_report: OfficialSourceReviewEvidenceReport | None,
    ) -> list[OfficialSourceReviewRecord]:
        if evidence_report is None:
            return records
        if evidence_report.status != "ready_for_review_application":
            return records

        evidence_by_candidate = _latest_evidence_by_candidate(
            evidence_report.evidence_items
        )
        updated_records: list[OfficialSourceReviewRecord] = []
        candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        for record in records:
            candidate = candidates_by_id.get(record.candidate_id)
            evidence = evidence_by_candidate.get(record.candidate_id)
            if candidate is None or evidence is None:
                updated_records.append(record)
                continue
            updated_records.append(_record_with_evidence(record, candidate, evidence))
        return updated_records


def _candidates_for_plan(plan: CriticalGapClosurePlan) -> list[OfficialSourceCandidate]:
    candidates: list[OfficialSourceCandidate] = []
    task_ids = plan.acquisition_task_ids or [None]
    for index, need in enumerate(plan.official_source_needs):
        related_task_id = task_ids[index] if index < len(task_ids) else task_ids[0]
        candidates.append(
            OfficialSourceCandidate(
                candidate_id=f"official-source-candidate-{need.need_id}",
                domain=plan.domain,
                proposed_trust_tier=need.required_trust_tier,
                related_gap_id=f"critical-gap-{plan.domain}",
                related_acquisition_task_id=related_task_id,
                status="blocked_needs_official_evidence",
                not_trusted_until_approved=True,
                notes=[
                    "Template generated from a critical source gap closure plan.",
                    "No official URL or document reference has been captured.",
                    "This candidate is not trusted evidence until reviewed and published.",
                ],
            )
        )
    return candidates


def _required_items_complete(
    domain: str,
    checklist: OfficialSourceReviewChecklist,
) -> bool:
    return all(
        [
            checklist.official_publisher_verified,
            checklist.url_or_document_captured,
            checklist.trust_tier_classified,
            checklist.domain_scope_confirmed,
            checklist.freshness_checked,
            checklist.source_version_recorded,
            checklist.no_conflict_with_existing_sources,
            checklist.reviewer_notes_present,
            domain not in HIGH_RISK_DOMAINS or checklist.high_risk_second_review_required,
        ]
    )


def _decision_for_incomplete_checklist(
    checklist: OfficialSourceReviewChecklist,
) -> str:
    if not checklist.official_publisher_verified or not checklist.url_or_document_captured:
        return "pending"
    return "needs_changes"


def _status_for_incomplete_checklist(
    checklist: OfficialSourceReviewChecklist,
) -> str:
    if not checklist.official_publisher_verified or not checklist.url_or_document_captured:
        return "blocked_needs_official_evidence"
    return "changes_requested"


def _prohibited_claim_types(domain: str) -> list[str]:
    if domain in {"visa_extension", "residence_registration", "police_registration"}:
        return [
            "legal or immigration-status certainty",
            "visa, residence, or police registration deadline certainty",
            "required document certainty",
            "official filing procedure certainty",
            "penalty or enforcement certainty",
        ]
    if domain == "work_contract":
        return [
            "work authorization legality",
            "employment status certainty",
            "contract enforceability certainty",
        ]
    if domain == "medical_or_hospital":
        return [
            "medical diagnosis",
            "treatment certainty",
            "hospital admission or insurance certainty",
        ]
    if domain == "payment_or_scam":
        return [
            "guaranteed refund path",
            "official police or bank procedure certainty",
            "fraud classification certainty",
        ]
    if domain in {"lost_passport", "emergency"}:
        return [
            "official emergency procedure certainty",
            "guaranteed human response",
            "official consular procedure certainty",
        ]
    return list(DEFAULT_PROHIBITED_CLAIMS)


def _latest_evidence_by_candidate(
    evidence_items: list[OfficialSourceCandidateReviewEvidence],
) -> dict[str, OfficialSourceCandidateReviewEvidence]:
    by_candidate: dict[str, OfficialSourceCandidateReviewEvidence] = {}
    for evidence in evidence_items:
        current = by_candidate.get(evidence.candidate_id)
        if current is None or _evidence_sort_key(evidence) >= _evidence_sort_key(current):
            by_candidate[evidence.candidate_id] = evidence
    return by_candidate


def _evidence_sort_key(evidence: OfficialSourceCandidateReviewEvidence) -> tuple[int, str]:
    round_rank = 1 if evidence.review_round == "second_review" else 0
    return round_rank, evidence.reviewed_at or ""


def _record_with_evidence(
    record: OfficialSourceReviewRecord,
    candidate: OfficialSourceCandidate,
    evidence: OfficialSourceCandidateReviewEvidence,
) -> OfficialSourceReviewRecord:
    high_risk = candidate.domain in HIGH_RISK_DOMAINS
    checklist = OfficialSourceReviewChecklist(
        candidate_id=candidate.candidate_id,
        official_publisher_verified=evidence.official_publisher_verified,
        url_or_document_captured=evidence.url_or_document_captured,
        trust_tier_classified=evidence.trust_tier_classified,
        domain_scope_confirmed=evidence.domain_scope_confirmed,
        freshness_checked=evidence.freshness_checked,
        source_version_recorded=evidence.source_version_recorded,
        no_conflict_with_existing_sources=evidence.no_conflict_with_existing_sources,
        high_risk_second_review_required=high_risk,
        reviewer_notes_present=evidence.reviewer_notes_present,
        prohibited_if_missing=_prohibited_claim_types(candidate.domain),
    )

    if evidence.decision == "rejected":
        decision = "rejected"
        status = "rejected"
        allowed_claims = ["none"]
        prohibited_claims = evidence.prohibited_claim_types or _prohibited_claim_types(
            candidate.domain
        )
        notes = [
            "Human review evidence rejected this candidate.",
            "Rejected candidates are not trusted evidence and must not support answers.",
        ]
    elif _evidence_allows_publish_preview(candidate, evidence):
        decision = "approved_for_preview"
        status = "approved_for_publish_preview"
        allowed_claims = evidence.allowed_claim_types or [
            "publish-preview metadata only",
            "source-scoped claim drafting for later registry approval",
        ]
        prohibited_claims = []
        notes = [
            "Human review evidence supports publish preview only.",
            "The candidate is still not published and not trusted citizen-answer evidence.",
        ]
    else:
        decision = "needs_changes" if evidence.decision != "pending" else "pending"
        status = _status_for_incomplete_checklist(checklist)
        allowed_claims = ["none for citizen-facing factual authority"]
        prohibited_claims = evidence.prohibited_claim_types or _prohibited_claim_types(
            candidate.domain
        )
        notes = [
            "Human review evidence is incomplete for publish preview.",
            "First review alone is insufficient for high-risk source candidates.",
            "The candidate remains blocked or needs changes.",
        ]

    candidate.status = status
    candidate.not_trusted_until_approved = True
    candidate.notes.append(
        "Local human review evidence was applied as review metadata only."
    )
    return record.model_copy(
        update={
            "reviewer_role": evidence.reviewer_role,
            "decision": decision,
            "checklist": checklist,
            "allowed_claim_types": allowed_claims,
            "prohibited_claim_types": prohibited_claims,
            "required_warnings": [
                *record.required_warnings,
                *evidence.required_warnings,
                "Human review evidence is not trusted citizen-answer evidence.",
                "Approved-for-publish-preview candidates are not published.",
            ],
            "review_notes": [
                *notes,
                *evidence.sanitized_reviewer_notes,
            ],
            "updated_at": utc_now(),
        }
    )


def _evidence_allows_publish_preview(
    candidate: OfficialSourceCandidate,
    evidence: OfficialSourceCandidateReviewEvidence,
) -> bool:
    checklist_complete = all(
        [
            evidence.decision == "approved_for_preview",
            evidence.official_publisher_verified,
            evidence.url_or_document_captured,
            evidence.trust_tier_classified,
            evidence.domain_scope_confirmed,
            evidence.freshness_checked,
            evidence.source_version_recorded,
            evidence.no_conflict_with_existing_sources,
            evidence.reviewer_notes_present,
        ]
    )
    if not checklist_complete:
        return False
    if candidate.domain in HIGH_RISK_DOMAINS:
        return (
            evidence.review_round == "second_review"
            and evidence.high_risk_second_review_completed
        )
    return True
