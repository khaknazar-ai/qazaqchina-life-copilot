from pathlib import Path

from backend.app.critical_source_gap_closure.models import CriticalGapClosurePlan
from backend.app.critical_source_gap_closure.service import CriticalSourceGapClosureService
from backend.app.official_source_review.publish_preview_gate import (
    OfficialSourcePublishPreviewGateReport,
    OfficialSourcePublishPreviewGateService,
)
from backend.app.source_review_answer_constraints.models import (
    SourceReviewAnswerConstraint,
    SourceReviewAnswerConstraintsReport,
)

VISA_EXTENSION_PROHIBITED_CLAIMS = [
    "visa extension deadline certainty",
    "visa approval certainty",
    "exact document checklist certainty",
    "legal status certainty",
    "penalty certainty",
    "official filing procedure certainty",
]

KAZAKHSTAN_ENTRY_PROHIBITED_CLAIMS = [
    "visa requirement or visa-free eligibility by citizenship and passport type",
    "permitted stay length or day-counting rule",
    "e-Visa eligibility, category, invitation, fee, or processing-time certainty",
    "entry-document requirements or border-admission guarantee",
    "arrival-notification deadline or host-party obligation",
    "work, study, or residence permission inferred from visitor entry",
]

RESIDENCE_REGISTRATION_PROHIBITED_CLAIMS = [
    "exact residence registration deadline certainty",
    "exact local procedure certainty",
    "local public security office workflow certainty",
    "required document certainty",
    "penalty certainty",
    "city-specific workflow certainty",
]

DEFAULT_PROHIBITED_CLAIMS = [
    "official procedure certainty without a published official source",
    "deadline or penalty certainty without a published official source",
    "unpublished source candidate citation",
    "publish preview package citation",
]


class SourceReviewAnswerConstraintsService:
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
        self._critical_plans_by_domain: dict[str, CriticalGapClosurePlan] = {}

    def build_report(self) -> SourceReviewAnswerConstraintsReport:
        critical_gap_report = CriticalSourceGapClosureService(
            self.project_root
        ).build_report()
        self._critical_plans_by_domain = {
            plan.domain: plan for plan in critical_gap_report.plans
        }
        publish_gate_report = OfficialSourcePublishPreviewGateService(
            self.project_root,
            intake_path=self.intake_path,
            review_evidence_path=self.review_evidence_path,
        ).build_report()

        domains = _unique_sorted(
            [
                *self._critical_plans_by_domain.keys(),
                *(candidate.domain for candidate in publish_gate_report.candidates),
            ]
        )
        constraints = [
            self.build_constraint_for_domain(domain, publish_gate_report)
            for domain in domains
        ]
        return SourceReviewAnswerConstraintsReport(
            total_domains=len(constraints),
            constrained_domain_count=sum(
                1
                for constraint in constraints
                if constraint.allowed_mode != "direct_answer_allowed"
            ),
            direct_answer_allowed_count=sum(
                1
                for constraint in constraints
                if constraint.allowed_mode == "direct_answer_allowed"
            ),
            official_verification_required_count=sum(
                1
                for constraint in constraints
                if constraint.allowed_mode == "official_verification_required"
            ),
            human_escalation_recommended_count=sum(
                1
                for constraint in constraints
                if constraint.allowed_mode == "human_escalation_recommended"
            ),
            refuse_specific_claims_count=sum(
                1
                for constraint in constraints
                if constraint.allowed_mode == "refuse_high_risk_specific_claims"
            ),
            constraints=constraints,
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            notes=[
                "Unpublished source candidates must not be cited in citizen answers.",
                "Reviewer packets, draft evidence, review evidence, and publish preview "
                "packages are not trusted citizen-answer evidence.",
                "Missing review evidence constrains high-risk answers to uncertainty, "
                "safe general steps, official verification, or escalation.",
                "Publish preview eligibility is not publishing.",
                "No trusted data/sources/*.jsonl files were modified.",
                "Closed beta and public launch remain false.",
                "No network, provider, OCR, source publishing, or registry write occurred.",
            ],
        )

    def build_constraint_for_domain(
        self,
        domain: str,
        publish_gate_report: OfficialSourcePublishPreviewGateReport,
    ) -> SourceReviewAnswerConstraint:
        domain_candidates = [
            candidate
            for candidate in publish_gate_report.candidates
            if candidate.domain == domain
        ]
        candidate_count = len(domain_candidates)
        eligible_count = sum(
            1 for candidate in domain_candidates if candidate.eligible_for_publish_preview
        )
        blocked_candidate_count = candidate_count - eligible_count
        official_source_published = _official_source_published_for_domain(
            domain,
            publish_gate_report,
        )
        publish_preview_eligible = eligible_count > 0
        mode = self.classify_domain_mode(domain, publish_gate_report)
        status = _source_review_status(
            domain=domain,
            candidate_count=candidate_count,
            blocked_candidate_count=blocked_candidate_count,
            publish_preview_eligible=publish_preview_eligible,
            official_source_published=official_source_published,
            critical_plan=self._critical_plans_by_domain.get(domain),
        )
        return SourceReviewAnswerConstraint(
            domain=domain,
            source_review_status=status,
            official_source_published=official_source_published,
            publish_preview_eligible=publish_preview_eligible,
            candidate_count=candidate_count,
            blocked_candidate_count=blocked_candidate_count,
            allowed_mode=mode,
            prohibited_claim_types=_prohibited_claim_types(domain),
            required_warning=_required_warning(domain),
            safe_response_guidance=_safe_response_guidance(domain, mode),
            citizen_visible_source_review_disclosure_allowed=False,
            admin_only_notes=_admin_only_notes(
                critical_plan=self._critical_plans_by_domain.get(domain),
                candidate_count=candidate_count,
                blocked_candidate_count=blocked_candidate_count,
                publish_preview_eligible=publish_preview_eligible,
                official_source_published=official_source_published,
            ),
        )

    def classify_domain_mode(
        self,
        domain: str,
        publish_gate_report: OfficialSourcePublishPreviewGateReport,
    ) -> str:
        if _official_source_published_for_domain(domain, publish_gate_report):
            return "direct_answer_allowed"

        critical_plan = self._critical_plans_by_domain.get(domain)
        critical_gap_open = critical_plan is None or critical_plan.closure_status != "closed"
        if critical_gap_open and domain in {
            "visa_extension", "kazakhstan_entry_visa", "work_contract",
        }:
            return "refuse_high_risk_specific_claims"
        if critical_gap_open and domain in {
            "lost_passport",
            "emergency",
            "medical_or_hospital",
            "payment_or_scam",
        }:
            return "human_escalation_recommended"
        if critical_gap_open:
            return "official_verification_required"
        return "cautious_general_steps_only"


def _official_source_published_for_domain(
    domain: str,
    publish_gate_report: OfficialSourcePublishPreviewGateReport,
) -> bool:
    if publish_gate_report.published_count <= 0:
        return False
    return any(candidate.domain == domain for candidate in publish_gate_report.candidates)


def _source_review_status(
    *,
    domain: str,
    candidate_count: int,
    blocked_candidate_count: int,
    publish_preview_eligible: bool,
    official_source_published: bool,
    critical_plan: CriticalGapClosurePlan | None,
) -> str:
    if official_source_published:
        return "published_official_source_available"
    if publish_preview_eligible:
        return "publish_preview_eligible_not_published"
    if candidate_count and blocked_candidate_count == candidate_count:
        return "source_candidates_blocked"
    if candidate_count:
        return "source_candidates_incomplete"
    if critical_plan is not None and critical_plan.closure_status != "closed":
        return "critical_gap_open_no_candidate"
    return f"{domain}_requires_official_source_review"


def _prohibited_claim_types(domain: str) -> list[str]:
    if domain == "visa_extension":
        return list(VISA_EXTENSION_PROHIBITED_CLAIMS)
    if domain == "kazakhstan_entry_visa":
        return list(KAZAKHSTAN_ENTRY_PROHIBITED_CLAIMS)
    if domain == "residence_registration":
        return list(RESIDENCE_REGISTRATION_PROHIBITED_CLAIMS)
    return list(DEFAULT_PROHIBITED_CLAIMS)


def _required_warning(domain: str) -> str:
    if domain == "visa_extension":
        return (
            "Visa-extension information must be verified with the local Exit-Entry "
            "Administration or, for students, the university international office before "
            "the user acts."
        )
    if domain == "residence_registration":
        return (
            "Residence-registration information must be verified with local public "
            "security, the university, or the accommodation provider before the user acts."
        )
    if domain == "kazakhstan_entry_visa":
        return (
            "Kazakhstan visa and entry requirements depend on citizenship, passport type, "
            "purpose, dates, and stay length. Verify current conditions through Kazakhstan "
            "official sources before travel."
        )
    return (
        "Official source coverage is incomplete; verify with the relevant official source "
        "or a qualified human before acting."
    )


def _safe_response_guidance(domain: str, mode: str) -> list[str]:
    guidance = [
        "State uncertainty when published official source coverage is missing.",
        "Do not cite unpublished source candidates, reviewer packets, draft evidence, "
        "review evidence, or publish preview packages.",
        "Give safe general preparation steps only.",
        "Recommend official verification before any status-sensitive or deadline-sensitive "
        "action.",
    ]
    if mode == "refuse_high_risk_specific_claims":
        guidance.append(
            "Refuse to provide exact legal, procedure, deadline, document, approval, or "
            "penalty claims without a published official source."
        )
    if domain == "visa_extension":
        guidance.extend(
            [
                "Suggest preparing passport, current visa/residence permit, university or "
                "host documents if applicable, and any official notice the user already has.",
                "Recommend contacting Exit-Entry Administration or the university "
                "international office for current requirements.",
            ]
        )
    elif domain == "residence_registration":
        guidance.extend(
            [
                "Suggest preparing passport, visa/residence permit, accommodation details, "
                "and any landlord/dormitory documents the user already has.",
                "Recommend contacting local public security, the university, or the "
                "accommodation provider for the current local workflow.",
            ]
        )
    elif domain == "kazakhstan_entry_visa":
        guidance.extend(
            [
                "Ask for citizenship, passport type, travel purpose, intended dates, and "
                "planned stay length; do not request passport numbers.",
                "Do not infer visa-free entry, e-Visa eligibility, or permission to work or "
                "study from nationality or tourism alone.",
                "Direct the user to the current Kazakhstan MFA visa-regime table, official "
                "e-Visa guidance, and the Visa and Migration Portal.",
            ]
        )
    return guidance


def _admin_only_notes(
    *,
    critical_plan: CriticalGapClosurePlan | None,
    candidate_count: int,
    blocked_candidate_count: int,
    publish_preview_eligible: bool,
    official_source_published: bool,
) -> list[str]:
    notes: list[str] = []
    if critical_plan is not None and critical_plan.closure_status != "closed":
        notes.append(
            f"Critical gap closure status is {critical_plan.closure_status}."
        )
    if candidate_count and blocked_candidate_count:
        notes.append(
            f"{blocked_candidate_count} of {candidate_count} source candidates are blocked."
        )
    if candidate_count:
        notes.append("Source candidates are under review and are admin/internal state only.")
    if publish_preview_eligible and not official_source_published:
        notes.append("At least one candidate is preview-eligible but not published.")
    if not official_source_published:
        notes.append("No published official source coverage is available for direct answers.")
    return notes


def _unique_sorted(values) -> list[str]:
    return sorted({value for value in values if value})
