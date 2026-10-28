from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import ModerationStatus, SourceType, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_coverage.models import (
    CoverageGap,
    SourceAcquisitionTask,
    SourceCoverageItem,
    SourceCoverageReport,
    SourceCoverageRequirement,
    SourceCoverageTrustTier,
)
from backend.app.source_coverage.taxonomy import (
    COVERAGE_DOMAINS,
    CRITICAL_DOMAINS,
    OFFICIAL_SOURCE_TIERS,
    default_coverage_requirements,
)
from backend.app.source_freshness.service import SourceFreshnessService
from backend.app.source_registry.registry import SourceRegistry


class SourceCoverageService:
    def __init__(
        self,
        source_registry: Any | None = None,
        source_freshness_service: Any | None = None,
    ) -> None:
        self.source_registry = source_registry
        self.source_freshness_service = source_freshness_service or SourceFreshnessService()

    def build_requirements(self) -> list[SourceCoverageRequirement]:
        return default_coverage_requirements()

    def collect_coverage_items(self) -> list[SourceCoverageItem]:
        registry = self._registry()
        role_by_post_id = _verified_roles_by_post_id(registry)
        items: list[SourceCoverageItem] = []
        requirements = {item.domain: item for item in self.build_requirements()}
        for source in _registry_sources(registry):
            if not _source_can_count_for_coverage(source):
                continue
            domains = _domains_for_source(source)
            trust_tier = _trust_tier_for_source(source, role_by_post_id.get(source.source_id))
            for domain in domains:
                requirement = requirements[domain]
                assessment = self.source_freshness_service.assess_sources(
                    [source],
                    domain=domain,
                    risk_level="high" if requirement.high_risk else "normal",
                ).assessments[0]
                freshness = (
                    "refresh_required"
                    if assessment.needs_refresh or _freshness_status(source) == "refresh_required"
                    else assessment.status
                )
                synthetic = _is_demo_source(source)
                notes = _coverage_notes(source, trust_tier)
                if synthetic:
                    notes.append("Synthetic/demo source does not count toward citizen readiness.")
                if freshness in {"unknown", "refresh_required"}:
                    notes.append("Source freshness is unknown or requires refresh.")
                items.append(
                    SourceCoverageItem(
                        domain=domain,
                        source_id=source.source_id,
                        source_title=source.title,
                        trust_tier=trust_tier,
                        freshness_status=freshness,
                        source_version_status=source.status_override or "active",
                        verified_role=role_by_post_id.get(source.source_id),
                        is_official=trust_tier in OFFICIAL_SOURCE_TIERS,
                        is_verified_comment=trust_tier
                        in {"verified_consular_comment", "verified_professional_comment"},
                        is_community=trust_tier == "community_experience",
                        eligible_for_readiness=not synthetic,
                        notes=list(dict.fromkeys(notes)),
                    )
                )
        return _dedupe_items(items)

    def analyze_coverage(self) -> SourceCoverageReport:
        requirements = self.build_requirements()
        coverage_items = self.collect_coverage_items()
        items_by_domain: dict[str, list[SourceCoverageItem]] = defaultdict(list)
        for item in coverage_items:
            items_by_domain[item.domain].append(item)

        gaps: list[CoverageGap] = []
        statuses: dict[str, str] = {}
        for requirement in requirements:
            domain_items = items_by_domain.get(requirement.domain, [])
            status = _domain_status(requirement, domain_items)
            statuses[requirement.domain] = status
            if _domain_has_gap(requirement, status):
                gaps.append(_gap_for_requirement(requirement, status, domain_items))

        acquisition_backlog = self.build_acquisition_backlog(gaps)
        return SourceCoverageReport(
            total_domains=len(requirements),
            covered_by_official_count=_count_status(statuses, "covered_by_official"),
            curated_count=_count_status(statuses, "covered_by_curated_official_backed"),
            verified_comment_count=_domain_count_with_tiers(
                coverage_items,
                {"verified_consular_comment", "verified_professional_comment"},
            ),
            community_only_count=_count_status(statuses, "community_only"),
            missing_count=_count_status(statuses, "missing"),
            refresh_required_count=_count_status(statuses, "refresh_required"),
            critical_gap_count=sum(1 for gap in gaps if gap.priority == "critical"),
            requirements=requirements,
            coverage_items=coverage_items,
            gaps=gaps,
            acquisition_backlog=acquisition_backlog,
            used_network=False,
            used_external_provider=False,
            notes=[
                "Coverage is based on local registry data only.",
                "Planned sources are not trusted evidence.",
                "Verified consular comments are practical context, not official law.",
                "Community-only coverage is insufficient for high-risk citizen guidance.",
            ],
        )

    def build_acquisition_backlog(
        self,
        gaps: list[CoverageGap],
    ) -> list[SourceAcquisitionTask]:
        tasks: list[SourceAcquisitionTask] = []
        for gap in gaps:
            if gap.priority not in {"critical", "high"}:
                continue
            target_tier = _target_tier_for_gap(gap)
            tasks.append(
                SourceAcquisitionTask(
                    task_id=f"source-acquisition-{gap.domain}",
                    domain=gap.domain,
                    priority=gap.priority,
                    target_trust_tier=target_tier,
                    description=_task_description(gap, target_tier),
                    suggested_owner_role=_owner_role_for_tier(target_tier),
                    acceptance_criteria=[
                        "official URL/document captured",
                        "source type classified",
                        "review completed",
                        "freshness checked",
                        "version recorded",
                        "not trusted until admin review/publishing",
                    ],
                    not_trusted_until_reviewed=True,
                )
            )
        return tasks

    def _registry(self):
        if self.source_registry is not None:
            return self.source_registry
        return SourceRegistry.from_data_dir()


def _registry_sources(registry: Any) -> list[SourceReference]:
    if hasattr(registry, "all_sources"):
        return list(registry.all_sources())
    return list(registry)


def _verified_roles_by_post_id(registry: Any) -> dict[str, str]:
    if not hasattr(registry, "approved_community_posts"):
        return {}
    roles: dict[str, str] = {}
    for post in registry.approved_community_posts():
        if not isinstance(post, CommunityPost):
            continue
        role = post.author.active_verified_role
        roles[post.post_id] = str(role)
    return roles


def _source_can_count_for_coverage(source: SourceReference) -> bool:
    if not source.allow_ai_retrieval:
        return False
    if source.source_type == SourceType.untrusted:
        return False
    if source.moderation_status and source.moderation_status != ModerationStatus.approved:
        return False
    return (source.status_override or "active") not in {
        "deprecated",
        "superseded",
        "rejected",
    }


def _is_demo_source(source: SourceReference) -> bool:
    hostname = (urlsplit(str(source.url or "")).hostname or "").casefold()
    text = f"{source.title} {source.content or ''}".casefold()
    return (
        "synthetic" in text
        or hostname.endswith((".test", ".invalid", ".example", ".localhost"))
        or hostname in {"example.com", "example.org", "example.net", "localhost"}
    )


def _domains_for_source(source: SourceReference) -> list[str]:
    text = f"{source.title} {source.content or ''}".casefold()
    scenario = source.scenario
    domains: list[str] = []
    if scenario == UserScenario.emergency:
        domains.extend(["emergency"])
        if "passport" in text:
            domains.append("lost_passport")
    elif scenario == UserScenario.documents:
        domains.extend(_document_domains(text))
    elif scenario == UserScenario.study:
        domains.append("university_registration")
    elif scenario == UserScenario.housing:
        domains.append("dormitory_or_housing")
        if "registration" in text or "address" in text:
            domains.extend(["residence_registration", "police_registration"])
    elif scenario == UserScenario.work:
        domains.append("work_contract")
    elif scenario == UserScenario.medical:
        domains.append("medical_or_hospital")
    elif scenario == UserScenario.payments:
        domains.extend(_payment_domains(text))
    elif scenario == UserScenario.translation:
        domains.append("chinese_notice_explanation")
    elif scenario == UserScenario.community_experience:
        domains.append("community_misinformation_conflict")
    elif scenario == UserScenario.kazakhstan_entry:
        domains.append("kazakhstan_entry_visa")
    elif scenario == UserScenario.tourism:
        if "registration" in text or "hotel" in text:
            domains.append("police_registration")
    if not domains and source.source_type == SourceType.ordinary_community:
        domains.append("community_misinformation_conflict")
    return [domain for domain in _unique(domains) if domain in COVERAGE_DOMAINS]


def _document_domains(text: str) -> list[str]:
    domains: list[str] = []
    if "visa" in text or "residence" in text:
        domains.append("visa_extension")
    if "residence" in text or "address" in text:
        domains.append("residence_registration")
    if "police" in text or "registration" in text:
        domains.append("police_registration")
    if "consul" in text or "embassy" in text:
        domains.append("consulate_appointment")
    return domains or ["visa_extension"]


def _payment_domains(text: str) -> list[str]:
    domains = ["payment_or_scam"]
    if "card" in text or "bank" in text:
        domains.append("bank_card_payment")
    if "sim" in text or "phone" in text:
        domains.append("sim_card_registration")
    return domains


def _trust_tier_for_source(
    source: SourceReference,
    verified_role: str | None = None,
) -> SourceCoverageTrustTier:
    text = f"{source.title} {source.content or ''}".casefold()
    if source.source_type == SourceType.official:
        if "law" in text:
            return "official_law"
        if "regulation" in text:
            return "official_regulation"
        if "policy" in text:
            return "official_policy_document"
        if "consul" in text or "embassy" in text or "passport" in text:
            return "official_consulate_or_embassy_page"
        if "university" in text:
            return "official_university_page"
        return "official_agency_page"
    if source.source_type == SourceType.curated_guide:
        return "curated_official_backed_guide"
    if source.source_type == SourceType.verified_institutional_contributor:
        role_text = (verified_role or "").casefold()
        if "consul" in role_text or "consul" in text:
            return "verified_consular_comment"
        return "verified_professional_comment"
    if source.source_type == SourceType.verified_experienced_contributor:
        return "verified_professional_comment"
    if source.source_type == SourceType.ordinary_community:
        return "community_experience"
    return "unknown_or_unclassified"


def _freshness_status(source: SourceReference) -> str:
    note = (source.freshness_note or "").casefold()
    if any(term in note for term in ("stale", "unknown", "refresh")):
        return "refresh_required"
    if source.date_accessed or source.reviewed_at or source.last_reviewed_at:
        return "freshness_checked"
    return "unknown"


def _coverage_notes(
    source: SourceReference,
    trust_tier: SourceCoverageTrustTier,
) -> list[str]:
    notes: list[str] = []
    if trust_tier in {"verified_consular_comment", "verified_professional_comment"}:
        notes.append("Verified comment is practical guidance, not official legal authority.")
    if trust_tier == "community_experience":
        notes.append("Community experience is practical context only.")
    if _freshness_status(source) in {"unknown", "refresh_required"}:
        notes.append("Source freshness is unknown or requires refresh.")
    return notes


def _dedupe_items(items: list[SourceCoverageItem]) -> list[SourceCoverageItem]:
    result: dict[tuple[str, str | None, str], SourceCoverageItem] = {}
    for item in items:
        result[(item.domain, item.source_id, item.trust_tier)] = item
    return list(result.values())


def _domain_status(
    requirement: SourceCoverageRequirement,
    items: list[SourceCoverageItem],
) -> str:
    active_items = [
        item
        for item in items
        if item.eligible_for_readiness
        and item.source_version_status not in {"deprecated", "superseded", "rejected"}
    ]
    matching = [
        item
        for item in active_items
        if any(_tier_satisfies(item.trust_tier, tier) for tier in requirement.required_trust_tiers)
    ]
    for tiers, status in [
        (OFFICIAL_SOURCE_TIERS, "covered_by_official"),
        (("curated_official_backed_guide",), "covered_by_curated_official_backed"),
    ]:
        candidates = [item for item in matching if item.trust_tier in tiers]
        if any(item.freshness_status in {"fresh", "freshness_checked"} for item in candidates):
            return status
        if candidates:
            return "refresh_required"
    if any(
        item.trust_tier in {"verified_consular_comment", "verified_professional_comment"}
        for item in active_items
    ):
        return "supported_by_verified_comment"
    if any(item.trust_tier == "community_experience" for item in active_items):
        return "community_only"
    return "missing"


def _tier_satisfies(actual: str, required: str) -> bool:
    return actual == required or (
        required == "official_agency_page"
        and actual in {"official_law", "official_regulation", "official_policy_document"}
    )


def _domain_has_gap(requirement: SourceCoverageRequirement, status: str) -> bool:
    if status in {"missing", "community_only", "supported_by_verified_comment"}:
        return True
    if status == "refresh_required":
        return True
    if requirement.minimum_status == "covered_by_official":
        return status != "covered_by_official"
    return status not in {"covered_by_official", "covered_by_curated_official_backed"}


def _gap_for_requirement(
    requirement: SourceCoverageRequirement,
    status: str,
    items: list[SourceCoverageItem],
) -> CoverageGap:
    missing_tiers = [
        tier
        for tier in requirement.required_trust_tiers
        if not any(
            _tier_satisfies(item.trust_tier, tier)
            and item.eligible_for_readiness
            and item.freshness_status in {"fresh", "freshness_checked"}
            for item in items
        )
    ]
    return CoverageGap(
        domain=requirement.domain,
        status=status,
        priority=requirement.priority,
        missing_trust_tiers=missing_tiers or requirement.required_trust_tiers,
        risk=_gap_risk(requirement, status),
        recommended_action=_gap_action(requirement, status),
        can_answer_without_official_source=not requirement.high_risk
        and status in {"covered_by_curated_official_backed", "supported_by_verified_comment"},
        requires_human_review=requirement.high_risk
        or status in {"community_only", "missing", "refresh_required"},
    )


def _gap_risk(requirement: SourceCoverageRequirement, status: str) -> str:
    if status == "community_only":
        return (
            "Only community experience is present. High-risk answers must not make "
            "official, legal, medical, or procedural claims."
        )
    if status == "supported_by_verified_comment":
        return (
            "Verified comments can support practical context but cannot replace official "
            "law, policy, agency, consular, or university coverage."
        )
    if status == "refresh_required":
        return "Coverage exists but freshness is stale or unknown and must be reviewed."
    if requirement.domain in CRITICAL_DOMAINS:
        return "Critical citizen scenario lacks required official or official-backed coverage."
    return "Coverage is incomplete for dependable citizen guidance."


def _gap_action(requirement: SourceCoverageRequirement, status: str) -> str:
    if status == "refresh_required":
        return "Refresh and re-review the existing official or curated source before use."
    return (
        "Collect, classify, review, freshness-check, and version an official or "
        "official-backed source before allowing confident answers."
    )


def _target_tier_for_gap(gap: CoverageGap) -> SourceCoverageTrustTier:
    official_missing = [tier for tier in gap.missing_trust_tiers if tier in OFFICIAL_SOURCE_TIERS]
    if official_missing:
        return official_missing[0]
    return gap.missing_trust_tiers[0]


def _task_description(
    gap: CoverageGap,
    target_tier: SourceCoverageTrustTier,
) -> str:
    if gap.status == "supported_by_verified_comment":
        return (
            f"Acquire {target_tier} coverage for {gap.domain}; keep verified comments "
            "as supporting practical context only."
        )
    return f"Acquire reviewed {target_tier} coverage for {gap.domain}."


def _owner_role_for_tier(target_tier: SourceCoverageTrustTier) -> str:
    if target_tier == "official_university_page":
        return "source_owner_university"
    if target_tier == "official_consulate_or_embassy_page":
        return "source_owner_consular"
    return "source_owner_official"


def _count_status(statuses: dict[str, str], status: str) -> int:
    return sum(1 for value in statuses.values() if value == status)


def _domain_count_with_tiers(
    items: list[SourceCoverageItem],
    tiers: set[str],
) -> int:
    return len({item.domain for item in items if item.trust_tier in tiers})


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
