from pathlib import Path

from backend.app.critical_source_gap_closure.models import (
    AIResponseConstraint,
    ConsularCommentSupportPlan,
    CriticalGapClosurePlan,
    CriticalSourceGapClosureReport,
    CuratedGuideReadiness,
    OfficialSourceNeed,
)
from backend.app.source_acquisition.models import SourceAcquisitionTaskRecord
from backend.app.source_acquisition.service import SourceAcquisitionService
from backend.app.source_coverage.models import CoverageGap
from backend.app.source_coverage.service import SourceCoverageService
from backend.app.source_coverage.taxonomy import OFFICIAL_SOURCE_TIERS

_DOMAIN_OFFICIAL_NEEDS: dict[str, list[str]] = {
    "lost_passport": [
        "official_consulate_or_embassy_page",
        "official_policy_document",
    ],
    "emergency": ["official_agency_page", "official_consulate_or_embassy_page"],
    "visa_extension": ["official_agency_page", "official_regulation"],
    "kazakhstan_entry_visa": ["official_agency_page", "official_regulation"],
    "residence_registration": ["official_agency_page", "official_regulation"],
    "police_registration": ["official_agency_page", "official_regulation"],
    "medical_or_hospital": ["official_agency_page", "official_policy_document"],
    "work_contract": ["official_law", "official_regulation"],
    "payment_or_scam": ["official_agency_page", "official_policy_document"],
}

_DOMAIN_BLOCKED_CLAIMS: dict[str, list[str]] = {
    "lost_passport": [
        "definitive passport replacement procedure",
        "required police report details",
        "consular appointment requirements",
    ],
    "emergency": [
        "emergency dispatch promise",
        "official emergency procedure certainty",
        "guaranteed human response",
    ],
    "visa_extension": [
        "visa extension eligibility",
        "filing deadlines",
        "required documents or penalties",
    ],
    "kazakhstan_entry_visa": [
        "visa requirement or visa-free eligibility by citizenship and passport type",
        "permitted stay length or day-counting rule",
        "e-Visa eligibility, category, invitation, fee, or processing-time certainty",
        "entry-document requirements or border-admission guarantee",
        "arrival-notification deadline or host-party obligation",
        "work, study, or residence permission inferred from visitor entry",
    ],
    "residence_registration": [
        "residence registration deadline",
        "police registration procedure",
        "penalty or legality claims",
    ],
    "police_registration": [
        "police registration deadline",
        "required documents",
        "penalty or enforcement claims",
    ],
    "medical_or_hospital": [
        "medical diagnosis",
        "hospital admission requirements",
        "insurance or treatment certainty",
    ],
    "work_contract": [
        "work authorization legality",
        "contract enforceability",
        "employment status advice",
    ],
    "payment_or_scam": [
        "guaranteed refund path",
        "official police/bank procedure certainty",
        "fraud classification certainty",
    ],
}

_CONSULAR_ROLE_HINTS: dict[str, list[str]] = {
    "lost_passport": ["verified_consul", "verified_vice_consul"],
    "emergency": ["verified_consul", "verified_consular_worker"],
    "visa_extension": ["verified_consular_worker"],
    "residence_registration": ["verified_consular_worker"],
    "police_registration": ["verified_consular_worker"],
    "medical_or_hospital": ["verified_medical_visitor", "verified_consular_worker"],
    "work_contract": ["verified_worker", "verified_consular_worker"],
    "payment_or_scam": ["verified_business_visitor", "verified_consular_worker"],
}


class CriticalSourceGapClosureService:
    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root)

    def build_report(self) -> CriticalSourceGapClosureReport:
        coverage_report = SourceCoverageService().analyze_coverage()
        acquisition_service = SourceAcquisitionService()
        acquisition_tasks = acquisition_service.create_tasks_from_coverage_report(
            coverage_report
        )
        critical_gaps = [gap for gap in coverage_report.gaps if gap.priority == "critical"]
        plans = [
            self.build_plan_for_gap(gap, acquisition_tasks)
            for gap in sorted(critical_gaps, key=lambda item: item.domain)
        ]
        closed_count = sum(1 for plan in plans if plan.closure_status == "closed")
        ready_count = sum(
            1 for plan in plans if plan.closure_status == "ready_for_source_candidate"
        )
        blocked_count = sum(
            1
            for plan in plans
            if plan.closure_status == "blocked_waiting_official_source"
        )
        return CriticalSourceGapClosureReport(
            total_critical_gaps=len(plans),
            open_gap_count=sum(1 for plan in plans if plan.closure_status != "closed"),
            blocked_gap_count=blocked_count,
            ready_for_candidate_count=ready_count,
            closed_gap_count=closed_count,
            plans=plans,
            global_ai_constraints=[
                "Do not answer high-risk legal, visa, medical, police, work, or "
                "emergency claims with certainty while official coverage is missing.",
                "Use uncertainty, official verification, and human escalation language "
                "for open critical gaps.",
                "Do not cite closure plans, planned sources, acquisition tasks, "
                "consular comments, or community posts as official authority.",
                "Community experience cannot close critical official source gaps.",
            ],
            source_acquisition_backlog_links=[
                f"{task.task_id}:{task.domain}:{task.target_trust_tier}"
                for task in acquisition_tasks
            ],
            not_trusted_evidence_warning=(
                "Planned source closure items are not trusted evidence and must not be "
                "cited in citizen answers."
            ),
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            notes=[
                "Critical gap closure planning is offline and local-registry based.",
                "No trusted source registry files were modified.",
                "No official URLs, phone numbers, laws, deadlines, offices, addresses, "
                "procedures, or requirements were invented.",
                "Closed beta and public launch remain false.",
            ],
        )

    def build_plan_for_gap(
        self,
        gap: CoverageGap,
        acquisition_tasks: list[SourceAcquisitionTaskRecord],
    ) -> CriticalGapClosurePlan:
        domain_tasks = [task for task in acquisition_tasks if task.domain == gap.domain]
        official_needs = self.build_official_source_needs(gap)
        return CriticalGapClosurePlan(
            domain=gap.domain,
            priority=gap.priority,
            current_status=gap.status,
            risk=gap.risk,
            official_source_needs=official_needs,
            consular_comment_support=self.build_consular_comment_support(gap.domain),
            curated_guide_readiness=self.build_curated_guide_readiness(gap),
            ai_response_constraint=self.build_ai_response_constraint(gap),
            acquisition_task_ids=[task.task_id for task in domain_tasks],
            acceptance_criteria=_acceptance_criteria(gap, domain_tasks),
            closure_status=_closure_status_for(gap, domain_tasks),
            can_close_without_official_source=False,
            notes=[
                "This closure plan is not trusted evidence.",
                "Official source needs must be satisfied before the critical gap is closed.",
                "Verified comments can support practical context only.",
            ],
        )

    def build_official_source_needs(self, gap: CoverageGap) -> list[OfficialSourceNeed]:
        official_missing = [
            tier for tier in gap.missing_trust_tiers if tier in OFFICIAL_SOURCE_TIERS
        ]
        suggested_tiers = _DOMAIN_OFFICIAL_NEEDS.get(gap.domain, ["official_agency_page"])
        tiers = _unique([*official_missing, *suggested_tiers])
        return [
            OfficialSourceNeed(
                need_id=f"{gap.domain}-{tier}",
                domain=gap.domain,
                required_trust_tier=tier,
                description=(
                    f"Find and review an official source of tier `{tier}` for "
                    f"`{gap.domain}`."
                ),
                why_required=(
                    "Critical/high-risk guidance needs official backing before "
                    "procedural or authoritative claims can be made."
                ),
                blocks_claim_types=_DOMAIN_BLOCKED_CLAIMS.get(
                    gap.domain,
                    ["definitive official procedure claims"],
                ),
                can_be_replaced_by_consular_comment=False,
            )
            for tier in tiers
        ]

    def build_consular_comment_support(self, domain: str) -> ConsularCommentSupportPlan:
        return ConsularCommentSupportPlan(
            domain=domain,
            useful_roles=_CONSULAR_ROLE_HINTS.get(
                domain,
                ["verified_consular_worker", "verified_professional_commenter"],
            ),
            purpose=(
                "Use verified consular or professional comments only as labelled "
                "practical context after official source needs are separated."
            ),
            limitations=[
                "Cannot replace official law, regulation, policy, agency, or consular pages.",
                "Cannot close a critical official source gap by itself.",
                "Cannot support deadlines, fees, eligibility, penalties, or official procedure.",
                "Must be labelled as context and reviewed before use.",
            ],
            cannot_replace_official_source=True,
        )

    def build_curated_guide_readiness(self, gap: CoverageGap) -> CuratedGuideReadiness:
        return CuratedGuideReadiness(
            domain=gap.domain,
            guide_allowed_now=False,
            required_before_publish=[
                "official source candidate created manually",
                "official source classified into the required trust tier",
                "freshness checked and source version recorded",
                "source reviewer approves official-backed claims",
                "curated guide cites reviewed official sources only for official claims",
            ],
            warning=(
                "Curated guides are blocked until official-backed review is complete."
            ),
        )

    def build_ai_response_constraint(self, gap: CoverageGap) -> AIResponseConstraint:
        mode = _response_mode_for(gap)
        return AIResponseConstraint(
            domain=gap.domain,
            allowed_response_mode=mode,
            prohibited_claims=_DOMAIN_BLOCKED_CLAIMS.get(
                gap.domain,
                ["definitive official procedure claims"],
            ),
            required_user_warning=(
                "Official source coverage for this high-risk topic is missing or "
                "incomplete; the app cannot provide authoritative instructions."
            ),
            escalation_recommendation=(
                "Escalate to a human reviewer and direct the user to official "
                "verification for any time-sensitive or status-sensitive decision."
            ),
        )


def _response_mode_for(gap: CoverageGap) -> str:
    if gap.status == "supported_by_verified_comment":
        return "safe_general_steps_only"
    if gap.status == "community_only":
        return "uncertainty_only"
    if gap.domain in {"emergency", "lost_passport", "medical_or_hospital"}:
        return "human_escalation_required"
    if gap.domain in {"visa_extension", "kazakhstan_entry_visa", "work_contract"}:
        return "refuse_high_risk_claim"
    return "official_verification_required"


def _closure_status_for(
    gap: CoverageGap,
    domain_tasks: list[SourceAcquisitionTaskRecord],
) -> str:
    if gap.status == "refresh_required":
        return "needs_review"
    if any(
        task.status in {"candidate_created", "in_review", "approved_for_publishing_preview"}
        for task in domain_tasks
    ):
        return "needs_review"
    if domain_tasks:
        return "ready_for_source_candidate"
    return "blocked_waiting_official_source"


def _acceptance_criteria(
    gap: CoverageGap,
    domain_tasks: list[SourceAcquisitionTaskRecord],
) -> list[str]:
    criteria = [
        "At least one required official source is manually collected as a candidate.",
        "Source candidate review classifies the source into the required official tier.",
        "Freshness is checked and a source version record exists.",
        "Source reviewer approves official-backed claim boundaries.",
        "Curated guide remains unpublished until official-backed review is complete.",
        "AI constraints are updated only after official-backed acceptance criteria pass.",
        "Generated reports remain under reports/generated/ and are not committed.",
    ]
    if gap.can_answer_without_official_source is False:
        criteria.append(
            "High-risk answers remain refusal, uncertainty, safe-steps, or escalation "
            "oriented until official coverage is accepted."
        )
    for task in domain_tasks:
        criteria.extend(task.acceptance_criteria)
    return _unique(criteria)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
