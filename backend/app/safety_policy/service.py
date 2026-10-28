from backend.app.safety_policy.models import (
    SafetyPolicyDecision,
    SafetyPolicyEvaluationRequest,
)
from backend.app.safety_policy.rules import (
    COMMUNITY_CONFLICT_WARNING,
    EMERGENCY_WARNING,
    MEDICAL_WARNING,
    OFFICIAL_SOURCE_WARNING,
    SCAM_WARNING,
    UNCERTAINTY_WARNING,
    infer_domain,
    risk_is_high,
)


class SafetyPolicyService:
    def evaluate(
        self,
        request: SafetyPolicyEvaluationRequest | None = None,
        *,
        query: str | None = None,
        scenario: str | None = None,
        risk_level: str | None = None,
        source_counts: dict[str, int] | None = None,
        has_official_source: bool = False,
        has_curated_source: bool = False,
        has_unreviewed_sources: bool = False,
    ) -> SafetyPolicyDecision:
        if request is None:
            request = SafetyPolicyEvaluationRequest(
                query=query,
                scenario=scenario,
                risk_level=risk_level,
                source_counts=source_counts or {},
                has_official_source=has_official_source,
                has_curated_source=has_curated_source,
                has_unreviewed_sources=has_unreviewed_sources,
            )

        domain = infer_domain(query=request.query, scenario=request.scenario)
        trusted_source_available = request.has_official_source or request.has_curated_source
        high_risk = risk_is_high(request.risk_level)

        if domain == "emergency" or request.risk_level == "emergency":
            return self._emergency_decision(domain)
        if domain == "medical":
            return self._medical_decision(domain, high_risk, trusted_source_available)
        if domain == "scam_or_payment":
            from backend.app.agent.classification import payment_intent

            payment_context = f"{request.query or ''} {request.scenario or ''}"
            if payment_intent(payment_context.replace("-", " ").replace("_", " ")) == "scam":
                return self._scam_decision(domain, trusted_source_available)
            if high_risk:
                return self._official_source_decision(domain, high_risk, trusted_source_available)
            return self._general_decision(
                domain, trusted_source_available, request.has_unreviewed_sources
            )
        if domain == "misinformation_or_source_conflict":
            return self._community_conflict_decision(domain, trusted_source_available)
        if domain in {
            "passport_or_document_loss",
            "visa_or_residence",
            "legal_or_police",
            "work_contract",
            "housing",
        }:
            return self._official_source_decision(domain, high_risk, trusted_source_available)
        return self._general_decision(
            domain,
            trusted_source_available,
            request.has_unreviewed_sources,
        )

    def escalation_request_metadata(
        self,
        decision: SafetyPolicyDecision,
    ) -> dict[str, str | bool]:
        return {
            "source": "safety_policy",
            "domain": decision.domain,
            "answer_level": decision.answer_level,
            "requires_human_escalation": decision.requires_human_escalation,
            "requires_emergency_authority": decision.requires_emergency_authority,
            "not_emergency_dispatch": decision.not_emergency_dispatch,
        }

    def _emergency_decision(self, domain: str) -> SafetyPolicyDecision:
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level="emergency_authority_required",
            requires_official_source=True,
            requires_human_escalation=True,
            requires_emergency_authority=True,
            required_warnings=[
                EMERGENCY_WARNING,
                "The app cannot replace police, ambulance, consular, hospital, or other "
                "official emergency response.",
            ],
            blocked_claim_types=[
                "claiming emergency dispatch was created",
                "definitive legal or medical instructions without authority",
                "community-sourced emergency procedures",
            ],
            recommended_next_steps=[
                "Contact local emergency services or official authorities if immediate "
                "danger exists.",
                "Use the human support queue only as a follow-up record, not emergency dispatch.",
                "Preserve key facts and documents if it is safe to do so.",
            ],
            high_risk=True,
            not_emergency_dispatch=True,
            uncertainty_required=True,
            community_sources_allowed=False,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision

    def _official_source_decision(
        self,
        domain: str,
        high_risk: bool,
        trusted_source_available: bool,
    ) -> SafetyPolicyDecision:
        warnings = [OFFICIAL_SOURCE_WARNING]
        if not trusted_source_available:
            warnings.append(UNCERTAINTY_WARNING)
        answer_level = "human_escalation_required" if high_risk else "official_source_required"
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level=answer_level,
            requires_official_source=True,
            requires_human_escalation=high_risk,
            required_warnings=warnings,
            blocked_claim_types=[
                "definitive legal, visa, police, housing, or work-status claims without "
                "trusted source",
                "community claims presented as official requirements",
                "unreviewed source citations",
            ],
            recommended_next_steps=[
                "Verify the requirement with an official or curated source.",
                "Prefer official/curated guidance over community experience.",
                "Create an escalation request when status, deadline, employment, police, "
                "or document risk is high.",
            ],
            high_risk=high_risk,
            uncertainty_required=not trusted_source_available,
            community_sources_allowed=True,
            unreviewed_sources_allowed=False,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision

    def _medical_decision(
        self,
        domain: str,
        high_risk: bool,
        trusted_source_available: bool,
    ) -> SafetyPolicyDecision:
        warnings = [MEDICAL_WARNING]
        if not trusted_source_available:
            warnings.append(UNCERTAINTY_WARNING)
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level="human_escalation_required" if high_risk else "safe_steps_only",
            requires_official_source=True,
            requires_human_escalation=high_risk,
            required_warnings=warnings,
            blocked_claim_types=[
                "diagnosis",
                "dosage or treatment instructions",
                "claims that avoid professional medical evaluation",
                "unreviewed medical source citations",
            ],
            recommended_next_steps=[
                "Give safe administrative steps only, such as preparing documents and "
                "seeking care.",
                "For urgent symptoms, contact qualified medical professionals or official "
                "medical services.",
                "Use human escalation for language, document, or navigation help, not diagnosis.",
            ],
            high_risk=high_risk,
            uncertainty_required=not trusted_source_available,
            community_sources_allowed=False,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision

    def _scam_decision(
        self,
        domain: str,
        trusted_source_available: bool,
    ) -> SafetyPolicyDecision:
        warnings = [SCAM_WARNING]
        if not trusted_source_available:
            warnings.append(UNCERTAINTY_WARNING)
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level="human_escalation_recommended",
            requires_official_source=False,
            requires_human_escalation=False,
            required_warnings=warnings,
            blocked_claim_types=[
                "instruction to send money under pressure",
                "claim that a payment request is safe without verification",
                "unreviewed source citations as official fraud guidance",
            ],
            recommended_next_steps=[
                "Do not send more money while the request is unclear.",
                "Preserve screenshots, receipts, usernames, phone numbers, and "
                "transaction records.",
                "Ask for human review when money, landlord, employer, or account access "
                "risk is involved.",
            ],
            high_risk=True,
            uncertainty_required=not trusted_source_available,
            community_sources_allowed=True,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision

    def _community_conflict_decision(
        self,
        domain: str,
        trusted_source_available: bool,
    ) -> SafetyPolicyDecision:
        warnings = [COMMUNITY_CONFLICT_WARNING]
        if not trusted_source_available:
            warnings.append(UNCERTAINTY_WARNING)
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level="official_source_required",
            requires_official_source=True,
            requires_human_escalation=not trusted_source_available,
            required_warnings=warnings,
            blocked_claim_types=[
                "community claim overriding official or curated guidance",
                "unverified source presented as authoritative",
            ],
            recommended_next_steps=[
                "Compare the claim against official or curated sources.",
                "Warn the user when community information is unverified or conflicts with "
                "higher-trust sources.",
                "Escalate source conflicts for human review.",
            ],
            high_risk=True,
            uncertainty_required=not trusted_source_available,
            community_sources_allowed=True,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision

    def _general_decision(
        self,
        domain: str,
        trusted_source_available: bool,
        has_unreviewed_sources: bool,
    ) -> SafetyPolicyDecision:
        warnings: list[str] = []
        if has_unreviewed_sources:
            warnings.append("Unreviewed sources cannot be used as trusted evidence.")
        if not trusted_source_available:
            warnings.append(UNCERTAINTY_WARNING)
        decision = SafetyPolicyDecision(
            domain=domain,
            answer_level="direct_answer_allowed" if trusted_source_available else "safe_steps_only",
            requires_official_source=False,
            requires_human_escalation=False,
            required_warnings=warnings,
            blocked_claim_types=[
                "unreviewed source citations",
                "official-sounding claims without trusted support",
            ],
            recommended_next_steps=[
                "Answer only within the available trusted evidence.",
                "Recommend official verification when sources are missing or uncertain.",
            ],
            high_risk=False,
            uncertainty_required=not trusted_source_available,
            community_sources_allowed=True,
            unreviewed_sources_allowed=False,
        )
        decision.escalation_metadata = self.escalation_request_metadata(decision)
        return decision
