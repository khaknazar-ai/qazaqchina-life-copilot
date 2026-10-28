from pydantic import BaseModel, Field

from backend.app.retrieval.query_expansion import (
    multilingual_keyword_hints,
    normalize_query_text,
    scenario_keyword_hints,
)

OFFICIAL_SOURCE = "official"
CURATED_SOURCE = "curated_guide"
VERIFIED_INSTITUTIONAL_SOURCE = "verified_institutional_contributor"
VERIFIED_EXPERIENCED_SOURCE = "verified_experienced_contributor"
COMMUNITY_SOURCE = "ordinary_community"
UNTRUSTED_SOURCE = "untrusted"

SOURCE_HIERARCHY = [
    OFFICIAL_SOURCE,
    CURATED_SOURCE,
    VERIFIED_INSTITUTIONAL_SOURCE,
    VERIFIED_EXPERIENCED_SOURCE,
    COMMUNITY_SOURCE,
]

SENSITIVE_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}


class RetrievalPlanningInput(BaseModel):
    user_message: str
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    country: str | None = "CN"
    city: str | None = None
    user_role: str | None = None


class RetrievalQuery(BaseModel):
    query: str
    intent: str
    required: bool = True
    language: str | None = None
    source_type_preference: list[str] = Field(default_factory=list)


class RetrievalSourcePolicy(BaseModel):
    require_official: bool = False
    allow_curated: bool = True
    allow_verified_institutional: bool = True
    allow_verified_experience: bool = True
    allow_community: bool = False
    allow_unverified: bool = False
    require_approved_community: bool = True
    require_ai_retrievable_community: bool = True
    official_outranks_individuals: bool = True
    require_freshness_check: bool = False
    needs_human_escalation_context: bool = False


class RetrievalPlan(BaseModel):
    scenario: str | None
    risk_level: str | None
    source_policy: RetrievalSourcePolicy
    queries: list[RetrievalQuery]
    required_source_types: list[str]
    excluded_source_types: list[str]
    warnings: list[str] = Field(default_factory=list)
    web_discovery_recommended: bool = False
    web_discovery_reason: str | None = None


def classify_retrieval_domain(user_message: str, scenario: str | None = None) -> str:
    normalized_message = user_message.casefold()
    normalized_scenario = (scenario or "").casefold()
    combined = f"{normalized_scenario} {normalized_message}"

    if "payment-scam" in normalized_scenario:
        return "payment_scam"
    if "hospital-registration" in normalized_scenario:
        return "medical_hospital"
    if "work-contract" in normalized_scenario or "unsafe-work" in normalized_scenario:
        return "work_contract_status"
    if (
        "visa-extension" in normalized_scenario
        or "police-station-registration" in normalized_scenario
    ):
        return "visa_overstay_registration"
    if "housing-registration" in normalized_scenario:
        return "housing_registration"
    if (
        "study-registration" in normalized_scenario
        or "university-dormitory" in normalized_scenario
    ):
        return "study_university"

    if _contains_any(
        combined,
        [
            "lost-passport",
            "passport",
            "document loss",
            "lost documents",
            "lost phone and documents",
            "consulate",
            "embassy",
        ],
    ):
        return "passport_document_loss"

    if _contains_any(
        combined,
        [
            "work-contract",
            "unsafe-work",
            "work status",
            "work permit",
            "tourist visa work",
            "paid cash",
            "employer",
            "contract",
            "work",
        ],
    ):
        return "work_contract_status"

    if _contains_any(
        combined,
        [
            "visa-extension",
            "visa",
            "overstay",
            "residence permit",
            "police-station-registration",
            "residence registration",
            "police station registration",
            "paichusuo",
            "\u6d3e\u51fa\u6240",
            "\u767b\u8bb0",
        ],
    ):
        return "visa_overstay_registration"

    if _contains_any(
        combined,
        [
            "hospital-registration",
            "hospital",
            "medical",
            "fever",
            "injury",
            "\u533b\u9662",
            "\u53d1\u70e7",
        ],
    ):
        return "medical_hospital"

    if _contains_any(
        combined,
        [
            "payment-scam",
            "payment",
            "scam",
            "fraud",
            "bank card",
            "wechat pay",
            "alipay",
            "sim card",
            "verification code",
        ],
    ):
        return "payment_scam"

    if _contains_any(
        combined,
        [
            "housing-registration",
            "housing",
            "landlord",
            "rental",
            "apartment",
            "address registration",
        ],
    ):
        return "housing_registration"

    if _contains_any(
        combined,
        [
            "study-registration",
            "university-dormitory",
            "study",
            "student",
            "university",
            "dormitory",
            "international office",
        ],
    ):
        return "study_university"

    if _contains_any(combined, ["emergency", "immediate danger", "urgent"]):
        return "emergency"

    return "general_life"


def build_retrieval_source_policy(
    domain: str,
    risk_level: str | None = None,
) -> RetrievalSourcePolicy:
    is_sensitive = _is_sensitive_risk(risk_level)

    if domain in {"passport_document_loss", "emergency"}:
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=False,
            allow_community=False,
            require_freshness_check=True,
            needs_human_escalation_context=True,
        )

    if domain == "visa_overstay_registration":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=False,
            allow_verified_experience=False,
            allow_community=False,
            require_freshness_check=True,
            needs_human_escalation_context=True,
        )

    if domain == "work_contract_status":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=True,
            allow_community=False,
            require_freshness_check=True,
            needs_human_escalation_context=True,
        )

    if domain == "medical_hospital":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=True,
            allow_community=False,
            require_freshness_check=is_sensitive,
            needs_human_escalation_context=True,
        )

    if domain == "payment_scam":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=True,
            allow_community=True,
            require_freshness_check=is_sensitive,
            needs_human_escalation_context=True,
        )

    if domain == "housing_registration":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=True,
            allow_community=not is_sensitive,
            require_freshness_check=is_sensitive,
            needs_human_escalation_context=is_sensitive,
        )

    if domain == "study_university":
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=True,
            allow_verified_experience=True,
            allow_community=not is_sensitive,
            require_freshness_check=is_sensitive,
            needs_human_escalation_context=is_sensitive,
        )

    if is_sensitive:
        return RetrievalSourcePolicy(
            require_official=True,
            allow_curated=True,
            allow_verified_institutional=False,
            allow_verified_experience=False,
            allow_community=False,
            require_freshness_check=True,
            needs_human_escalation_context=True,
        )

    return RetrievalSourcePolicy(
        require_official=False,
        allow_curated=True,
        allow_verified_institutional=True,
        allow_verified_experience=True,
        allow_community=True,
    )


def build_retrieval_queries(
    input: RetrievalPlanningInput,
    domain: str,
) -> list[RetrievalQuery]:
    language = input.language
    city_terms = f" {input.city}" if input.city else ""
    query_terms = {
        "passport_document_loss": [
            (
                f"{input.user_message} lost passport document loss police report "
                f"embassy consulate emergency document{city_terms}",
                "official_document_loss_steps",
                [OFFICIAL_SOURCE, CURATED_SOURCE],
            ),
            (
                f"passport loss consular appointment replacement document {input.country or 'CN'}",
                "human_escalation_context",
                [OFFICIAL_SOURCE, CURATED_SOURCE, VERIFIED_INSTITUTIONAL_SOURCE],
            ),
        ],
        "visa_overstay_registration": [
            (
                f"{input.user_message} visa overstay residence registration public security "
                f"legal requirement{city_terms}",
                "official_visa_registration_rules",
                [OFFICIAL_SOURCE, CURATED_SOURCE],
            )
        ],
        "work_contract_status": [
            (
                f"{input.user_message} work permit work authorization contract employer "
                "tourist visa paid work status",
                "official_work_status_rules",
                [OFFICIAL_SOURCE, CURATED_SOURCE],
            ),
            (
                "work contract practical document preparation verified worker experience",
                "practical_context_only",
                [VERIFIED_INSTITUTIONAL_SOURCE, VERIFIED_EXPERIENCED_SOURCE],
            ),
        ],
        "medical_hospital": [
            (
                f"{input.user_message} hospital registration medical visit passport insurance "
                f"payment emergency symptoms{city_terms}",
                "official_medical_preparation",
                [OFFICIAL_SOURCE, CURATED_SOURCE],
            )
        ],
        "payment_scam": [
            (
                f"{input.user_message} payment scam fraud verification code WeChat Pay Alipay "
                "bank card SIM card security",
                "platform_security_and_scam_pattern",
                [OFFICIAL_SOURCE, CURATED_SOURCE, COMMUNITY_SOURCE],
            )
        ],
        "housing_registration": [
            (
                f"{input.user_message} housing rental address registration landlord police "
                f"station{city_terms}",
                "housing_registration_rules_and_practice",
                [
                    OFFICIAL_SOURCE,
                    CURATED_SOURCE,
                    VERIFIED_EXPERIENCED_SOURCE,
                    COMMUNITY_SOURCE,
                ],
            )
        ],
        "study_university": [
            (
                f"{input.user_message} university registration dormitory residence permit "
                "international office student checklist",
                "university_registration_steps",
                [
                    OFFICIAL_SOURCE,
                    CURATED_SOURCE,
                    VERIFIED_INSTITUTIONAL_SOURCE,
                    VERIFIED_EXPERIENCED_SOURCE,
                ],
            )
        ],
        "emergency": [
            (
                f"{input.user_message} emergency official help escalation safe steps{city_terms}",
                "official_emergency_escalation",
                [OFFICIAL_SOURCE, CURATED_SOURCE],
            )
        ],
        "general_life": [
            (
                f"{input.user_message} China life practical checklist official guidance",
                "general_life_context",
                [CURATED_SOURCE, OFFICIAL_SOURCE, COMMUNITY_SOURCE],
            )
        ],
    }

    query_entries = list(query_terms[domain])
    expanded_query = _build_expanded_source_coverage_query(input, domain)
    if expanded_query:
        query_entries.append(
            (
                expanded_query,
                "scenario_expanded_source_coverage",
                query_entries[0][2],
            )
        )

    return [
        RetrievalQuery(
            query=query,
            intent=intent,
            language=language,
            source_type_preference=source_type_preference,
        )
        for query, intent, source_type_preference in query_entries
    ]


def build_retrieval_plan(input: RetrievalPlanningInput) -> RetrievalPlan:
    domain = classify_retrieval_domain(input.user_message, input.scenario)
    policy = build_retrieval_source_policy(domain, input.risk_level)
    queries = build_retrieval_queries(input, domain)
    warnings = _policy_warnings(domain, policy)

    return RetrievalPlan(
        scenario=input.scenario or domain,
        risk_level=input.risk_level,
        source_policy=policy,
        queries=queries,
        required_source_types=_required_source_types(policy),
        excluded_source_types=_excluded_source_types(policy),
        warnings=warnings,
        web_discovery_recommended=False,
        web_discovery_reason=(
            "Future web discovery may be needed only if reviewed local registry sources are "
            "missing required official coverage."
            if policy.require_official
            else None
        ),
    )


def explain_retrieval_plan(plan: RetrievalPlan) -> str:
    policy = plan.source_policy
    lines = [
        f"Scenario/domain: {plan.scenario or 'unknown'}",
        f"Risk level: {plan.risk_level or 'unspecified'}",
        (
            "Source hierarchy: official > curated guide > verified institutional contributor "
            "> verified experienced contributor > approved ordinary community."
        ),
        (
            "Excluded content: pending, rejected, flagged, unsafe, retrieval-disallowed, "
            "or unverified high-trust claims."
        ),
        (
            "Official published sources outrank individual comments, including verified "
            "consul or consular worker comments."
        ),
        f"Official source required: {policy.require_official}",
        f"Curated guides allowed: {policy.allow_curated}",
        f"Verified institutional context allowed: {policy.allow_verified_institutional}",
        f"Verified experience context allowed: {policy.allow_verified_experience}",
        f"Community context allowed: {policy.allow_community}",
        f"Freshness check required: {policy.require_freshness_check}",
        f"Human escalation context needed: {policy.needs_human_escalation_context}",
        f"Required source types: {', '.join(plan.required_source_types) or 'none'}",
        f"Excluded source types: {', '.join(plan.excluded_source_types) or 'none'}",
    ]

    if plan.web_discovery_reason:
        lines.append(plan.web_discovery_reason)

    if plan.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan.warnings)

    query_summary = ", ".join(query.intent for query in plan.queries)
    lines.append(f"Query intents: {query_summary}")
    return "\n".join(lines)


def _required_source_types(policy: RetrievalSourcePolicy) -> list[str]:
    if policy.require_official:
        return [OFFICIAL_SOURCE]

    required = [CURATED_SOURCE]
    if policy.allow_community:
        required.append(COMMUNITY_SOURCE)
    return required


def _excluded_source_types(policy: RetrievalSourcePolicy) -> list[str]:
    excluded = [UNTRUSTED_SOURCE]
    if not policy.allow_curated:
        excluded.append(CURATED_SOURCE)
    if not policy.allow_verified_institutional:
        excluded.append(VERIFIED_INSTITUTIONAL_SOURCE)
    if not policy.allow_verified_experience:
        excluded.append(VERIFIED_EXPERIENCED_SOURCE)
    if not policy.allow_community:
        excluded.append(COMMUNITY_SOURCE)
    return list(dict.fromkeys(excluded))


def _policy_warnings(domain: str, policy: RetrievalSourcePolicy) -> list[str]:
    warnings: list[str] = [
        "Official sources outrank community and verified contributor comments.",
        "Unverified, pending, rejected, flagged, or unsafe content must not be retrieved.",
    ]

    if policy.allow_community:
        warnings.append(
            "Community content may provide practical examples only when approved and AI "
            "retrievable; it must not be treated as official law."
        )
    else:
        warnings.append("Community content must not be used as official instruction.")

    if domain == "work_contract_status":
        warnings.append(
            "Verified work experience may add practical context, but work-status rules require "
            "official or curated support."
        )

    if domain == "payment_scam":
        warnings.append(
            "Community examples are allowed only for scam-pattern context, not for payment "
            "platform rules or guarantees."
        )

    if policy.needs_human_escalation_context:
        warnings.append("Plan retrieval for human or official escalation context.")

    return warnings


def _is_sensitive_risk(risk_level: str | None) -> bool:
    return (risk_level or "").casefold() in SENSITIVE_RISK_LEVELS


def _build_expanded_source_coverage_query(
    input: RetrievalPlanningInput,
    domain: str,
) -> str | None:
    terms = [
        normalize_query_text(input.user_message),
        *scenario_keyword_hints(domain)[:5],
        *multilingual_keyword_hints(domain, input.language)[:3],
    ]
    if input.city:
        terms.append(input.city)

    normalized_terms = [term for term in (normalize_query_text(term) for term in terms) if term]
    if not normalized_terms:
        return None

    return " ".join(dict.fromkeys(normalized_terms))


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)
