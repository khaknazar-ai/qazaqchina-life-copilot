from typing import Any

from backend.app.safety_policy.models import SafetyPolicyDecision


def localize_safety_policy_display(
    required_warnings: list[str],
    recommended_next_steps: list[str],
    language: str,
) -> tuple[list[str], list[str]]:
    from backend.app.safety_policy.localization import localize_messages

    return (
        localize_messages(required_warnings, language),
        localize_messages(recommended_next_steps, language),
    )


def safety_policy_decision_to_chat_metadata(
    decision: SafetyPolicyDecision,
) -> dict[str, Any]:
    return {
        "domain": decision.domain,
        "answer_level": decision.answer_level,
        "high_risk": decision.high_risk,
        "requires_official_source": decision.requires_official_source,
        "requires_human_escalation": decision.requires_human_escalation,
        "requires_emergency_authority": decision.requires_emergency_authority,
        "not_emergency_dispatch": decision.not_emergency_dispatch,
        "uncertainty_required": decision.uncertainty_required,
        "community_sources_allowed": decision.community_sources_allowed,
        "unreviewed_sources_allowed": decision.unreviewed_sources_allowed,
        "required_warnings": decision.required_warnings,
        "blocked_claim_types": decision.blocked_claim_types,
        "recommended_next_steps": decision.recommended_next_steps,
        "used_network": decision.used_network,
        "used_external_provider": decision.used_external_provider,
    }


def build_escalation_prefill_from_safety_decision(
    decision: SafetyPolicyDecision,
    user_text: str,
    *,
    scenario: str | None = None,
    risk_level: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    reason = _reason_for_domain(decision.domain)
    urgency = "urgent" if decision.requires_emergency_authority else "high"
    if not decision.high_risk and not decision.requires_human_escalation:
        urgency = "normal"
    summary = _trim_summary(user_text)
    return {
        "user_id": user_id,
        "session_id": session_id,
        "scenario": scenario or decision.domain,
        "risk_level": risk_level or decision.answer_level,
        "summary": summary,
        "reason": reason,
        "urgency": urgency,
        "not_emergency_dispatch": decision.not_emergency_dispatch,
        "safety_warning": _prefill_warning(decision),
        "metadata": {
            "source": "chat_safety_policy",
            "safety_domain": decision.domain,
            "answer_level": decision.answer_level,
            "requires_official_source": decision.requires_official_source,
            "requires_human_escalation": decision.requires_human_escalation,
            "requires_emergency_authority": decision.requires_emergency_authority,
            "not_emergency_dispatch": decision.not_emergency_dispatch,
            "not_trusted_source_evidence": True,
        },
    }


def should_recommend_escalation(decision: SafetyPolicyDecision) -> bool:
    return (
        decision.requires_human_escalation
        or decision.requires_emergency_authority
        or decision.answer_level == "human_escalation_recommended"
    )


def _reason_for_domain(domain: str) -> str:
    if domain == "emergency":
        return "emergency"
    if domain == "medical":
        return "medical_risk"
    if domain == "scam_or_payment":
        return "scam_or_payment_risk"
    if domain in {
        "passport_or_document_loss",
        "visa_or_residence",
        "legal_or_police",
        "work_contract",
        "housing",
    }:
        return "legal_or_visa_risk"
    if domain == "misinformation_or_source_conflict":
        return "source_conflict"
    return "needs_human_help"


def _prefill_warning(decision: SafetyPolicyDecision) -> str:
    if decision.not_emergency_dispatch:
        return (
            "This queue is not emergency dispatch. Contact local emergency services or "
            "official authorities if immediate danger exists."
        )
    if decision.domain == "medical":
        return "This is not medical diagnosis. Seek professional medical help for urgent symptoms."
    if decision.requires_official_source:
        return "Verify with official authorities or a qualified professional before acting."
    return "Human review queue records are user-provided input, not trusted evidence."


def _trim_summary(value: str, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."
