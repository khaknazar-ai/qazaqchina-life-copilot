from backend.app.safety_policy.models import SafetyRiskDomain

EMERGENCY_WARNING = (
    "This queue is not emergency dispatch. Contact local emergency services or "
    "official authorities if immediate danger exists."
)
OFFICIAL_SOURCE_WARNING = (
    "Official or curated sources are required before making definitive legal, visa, "
    "work, police, medical, or emergency claims."
)
COMMUNITY_CONFLICT_WARNING = (
    "Official and curated sources outrank community claims. Unverified community "
    "claims are not authoritative."
)
UNCERTAINTY_WARNING = (
    "No official or curated source is available in this result, so the answer must "
    "state uncertainty and recommend official verification."
)
MEDICAL_WARNING = (
    "Do not diagnose. Give safe next steps and advise urgent medical or qualified "
    "professional help when symptoms may be serious."
)
SCAM_WARNING = (
    "Avoid sending money, preserve evidence, and seek trusted human or official "
    "verification before taking irreversible action."
)


DOMAIN_KEYWORDS: dict[SafetyRiskDomain, tuple[str, ...]] = {
    "emergency": (
        "urgent",
        "immediate danger",
        "danger",
        "police emergency",
        "ambulance",
    ),
    "passport_or_document_loss": (
        "lost-passport",
        "passport",
        "document loss",
        "documents lost",
        "travel document",
    ),
    "misinformation_or_source_conflict": (
        "misinformation",
        "source conflict",
        "community conflict",
        "community says",
        "unverified",
    ),
    "visa_or_residence": (
        "visa",
        "residence",
        "registration",
        "overstay",
        "permit",
    ),
    "legal_or_police": (
        "legal",
        "police",
        "detained",
        "lawyer",
        "court",
        "fine",
    ),
    "work_contract": (
        "work",
        "contract",
        "employer",
        "employment",
        "salary",
    ),
    "medical": (
        "medical",
        "hospital",
        "doctor",
        "symptom",
        "diagnosis",
        "medicine",
    ),
    "scam_or_payment": (
        "scam",
        "payment",
        "deposit",
        "wechat pay",
        "alipay",
        "fraud",
    ),
    "housing": (
        "housing",
        "apartment",
        "landlord",
        "rent",
        "lease",
    ),
}


def infer_domain(
    query: str | None = None,
    scenario: str | None = None,
) -> SafetyRiskDomain:
    text = f"{scenario or ''} {query or ''}".casefold()
    if (scenario or "").casefold() == "emergency":
        return "emergency"
    if (scenario or "").casefold() == "kazakhstan_entry":
        return "visa_or_residence"
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return domain
    return "general_low_risk"


def risk_is_high(risk_level: str | None) -> bool:
    return (risk_level or "").casefold() in {
        "high",
        "urgent",
        "critical",
        "emergency",
        "legal_sensitive",
        "work_status_sensitive",
        "medical_sensitive",
    }
