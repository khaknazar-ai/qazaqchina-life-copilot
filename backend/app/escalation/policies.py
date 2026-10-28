from backend.app.domain.enums import RiskLevel, UserScenario

ESCALATION_RISK_LEVELS = {
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
}

ESCALATION_SAFETY_FLAGS = {
    "source_governance_failed",
    "source_conflict",
    "prompt_injection",
    "unsafe_request",
    "unsafe_work_advice",
    "emergency",
    "missing_official_source",
    "high_risk_without_official_source",
    "citation_verification_failed",
}

HIGH_PRIORITY_FLAGS = {
    "source_governance_failed",
    "source_conflict",
    "prompt_injection",
    "unsafe_request",
    "unsafe_work_advice",
    "missing_official_source",
    "high_risk_without_official_source",
    "citation_verification_failed",
}


def risk_level_requires_escalation(risk_level: RiskLevel) -> bool:
    return risk_level in ESCALATION_RISK_LEVELS


def risk_level_priority(risk_level: RiskLevel) -> str:
    if risk_level == RiskLevel.emergency:
        return "urgent"
    if risk_level in {
        RiskLevel.unsafe,
        RiskLevel.prompt_injection,
        RiskLevel.legal_sensitive,
        RiskLevel.work_status_sensitive,
        RiskLevel.medical_sensitive,
    }:
        return "high"
    if risk_level == RiskLevel.medium:
        return "medium"
    return "low"


def safety_flag_requires_escalation(flag: str) -> bool:
    return flag in ESCALATION_SAFETY_FLAGS


def safety_flag_priority(flag: str) -> str:
    if flag == "emergency":
        return "urgent"
    if flag in HIGH_PRIORITY_FLAGS:
        return "high"
    return "low"


def scenario_default_escalation_reason(
    scenario: UserScenario,
    risk_level: RiskLevel,
) -> str:
    if risk_level == RiskLevel.emergency or scenario == UserScenario.emergency:
        return "emergency"
    if risk_level == RiskLevel.work_status_sensitive or scenario == UserScenario.work:
        return "work_status_sensitive"
    if risk_level == RiskLevel.medical_sensitive or scenario == UserScenario.medical:
        return "medical_sensitive"
    if risk_level == RiskLevel.legal_sensitive:
        return "legal_sensitive"
    if risk_level in {RiskLevel.unsafe, RiskLevel.prompt_injection}:
        return "safety_risk"
    return "human_review"


def escalation_reason_to_action(reason: str) -> str:
    if reason == "emergency":
        return "Advise immediate local emergency or consular contact and create urgent case."
    if reason in {"legal_sensitive", "work_status_sensitive"}:
        return "Escalate to verified legal, consular, or admin review."
    if reason == "medical_sensitive":
        return "Escalate to medical professional or emergency care guidance."
    if reason in {"prompt_injection", "unsafe", "safety_risk"}:
        return "Refuse unsafe part and flag for human review."
    if reason in {
        "source_governance_failed",
        "source_conflict",
        "missing_official_source",
        "high_risk_without_official_source",
        "citation_verification_failed",
    }:
        return "Admin/source review required before relying on the answer."
    if reason == "missing_information":
        return "Ask for missing critical information before final guidance."
    return "Create human review handoff."
