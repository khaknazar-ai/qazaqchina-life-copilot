from backend.app.source_coverage.models import (
    CoveragePriority,
    SourceCoverageRequirement,
    SourceCoverageTrustTier,
)

OFFICIAL_SOURCE_TIERS: tuple[SourceCoverageTrustTier, ...] = (
    "official_law",
    "official_regulation",
    "official_policy_document",
    "official_agency_page",
    "official_consulate_or_embassy_page",
    "official_university_page",
)

SUPPORTING_SOURCE_TIERS: tuple[SourceCoverageTrustTier, ...] = (
    "curated_official_backed_guide",
    "verified_consular_comment",
    "verified_professional_comment",
    "community_experience",
)

COVERAGE_DOMAINS: tuple[str, ...] = (
    "lost_passport",
    "emergency",
    "visa_extension",
    "kazakhstan_entry_visa",
    "residence_registration",
    "police_registration",
    "university_registration",
    "dormitory_or_housing",
    "work_contract",
    "medical_or_hospital",
    "payment_or_scam",
    "bank_card_payment",
    "sim_card_registration",
    "consulate_appointment",
    "chinese_notice_explanation",
    "community_misinformation_conflict",
    "privacy_or_delete_request",
    "human_support_or_escalation",
)

CRITICAL_DOMAINS: tuple[str, ...] = (
    "lost_passport",
    "emergency",
    "visa_extension",
    "kazakhstan_entry_visa",
    "residence_registration",
    "police_registration",
    "medical_or_hospital",
    "payment_or_scam",
    "work_contract",
)

HIGH_PRIORITY_DOMAINS: tuple[str, ...] = (
    "university_registration",
    "dormitory_or_housing",
    "bank_card_payment",
    "consulate_appointment",
    "community_misinformation_conflict",
)

LOW_RISK_DOMAINS: tuple[str, ...] = (
    "chinese_notice_explanation",
    "privacy_or_delete_request",
    "human_support_or_escalation",
)

DOMAIN_REASONS: dict[str, str] = {
    "lost_passport": (
        "Lost passport cases can affect identity, travel, police reporting, and "
        "consular help."
    ),
    "emergency": "Emergency cases need immediate official or authority verification.",
    "visa_extension": "Visa and residence decisions can affect legal status in China.",
    "kazakhstan_entry_visa": (
        "Kazakhstan visa and entry conditions depend on citizenship, passport type, "
        "travel purpose, dates, and stay length."
    ),
    "residence_registration": "Residence registration errors can create legal and housing risk.",
    "police_registration": (
        "Police registration guidance must be based on official or curated "
        "official-backed sources."
    ),
    "university_registration": (
        "Student registration varies by university and must be tied to official "
        "instructions."
    ),
    "dormitory_or_housing": (
        "Housing and address registration can affect safety, money, and local "
        "compliance."
    ),
    "work_contract": "Work contract and authorization advice can affect legal work status.",
    "medical_or_hospital": (
        "Medical guidance must avoid diagnosis and point to official/professional care."
    ),
    "payment_or_scam": (
        "Scam and payment-risk cases require careful evidence preservation and "
        "official checks."
    ),
    "bank_card_payment": (
        "Payment setup is lower risk than scams but still involves identity and money "
        "handling."
    ),
    "sim_card_registration": (
        "SIM registration touches identity data and local operator requirements."
    ),
    "consulate_appointment": (
        "Consular appointment guidance must distinguish practical comments from "
        "official requirements."
    ),
    "chinese_notice_explanation": (
        "Notice explanation can be useful, but source-backed claims still matter."
    ),
    "community_misinformation_conflict": (
        "Community conflict needs official hierarchy and admin review."
    ),
    "privacy_or_delete_request": "Privacy workflow guidance should be product-policy backed.",
    "human_support_or_escalation": (
        "Escalation workflow guidance must not imply emergency dispatch."
    ),
}


def default_coverage_requirements() -> list[SourceCoverageRequirement]:
    return [
        SourceCoverageRequirement(
            domain=domain,
            required_trust_tiers=_required_tiers_for_domain(domain),
            minimum_status=_minimum_status_for_domain(domain),
            priority=_priority_for_domain(domain),
            reason=DOMAIN_REASONS[domain],
            high_risk=domain in CRITICAL_DOMAINS or domain in HIGH_PRIORITY_DOMAINS,
        )
        for domain in COVERAGE_DOMAINS
    ]


def _required_tiers_for_domain(domain: str) -> list[SourceCoverageTrustTier]:
    if domain == "kazakhstan_entry_visa":
        return ["official_agency_page", "official_regulation", "curated_official_backed_guide"]
    if domain == "university_registration":
        return ["official_university_page", "curated_official_backed_guide"]
    if domain in {"lost_passport", "consulate_appointment"}:
        return ["official_consulate_or_embassy_page", "curated_official_backed_guide"]
    if domain in LOW_RISK_DOMAINS:
        return ["curated_official_backed_guide", "official_agency_page"]
    return ["official_agency_page", "curated_official_backed_guide"]


def _minimum_status_for_domain(domain: str) -> str:
    if domain in LOW_RISK_DOMAINS:
        return "covered_by_curated_official_backed"
    return "covered_by_official"


def _priority_for_domain(domain: str) -> CoveragePriority:
    if domain in CRITICAL_DOMAINS:
        return "critical"
    if domain in HIGH_PRIORITY_DOMAINS:
        return "high"
    if domain in LOW_RISK_DOMAINS:
        return "low"
    return "medium"
