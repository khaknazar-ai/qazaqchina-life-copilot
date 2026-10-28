from backend.app.domain.agent import AgentState
from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.escalation.models import CaseDraft, EscalationPlan, EscalationTrigger
from backend.app.escalation.policies import (
    escalation_reason_to_action,
    risk_level_priority,
    risk_level_requires_escalation,
    safety_flag_priority,
    safety_flag_requires_escalation,
    scenario_default_escalation_reason,
)

PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
SOURCE_GOVERNANCE_MARKERS = (
    "source_governance",
    "source_conflict",
    "citation",
    "missing_official_source",
    "high_risk_without_official_source",
)


class EscalationService:
    def build_plan_from_state(self, state: AgentState) -> EscalationPlan:
        return self.build_plan(
            user_message=state.user_message,
            scenario=state.scenario,
            risk_level=state.risk_level,
            safety_flags=state.safety_flags,
            missing_information=state.missing_information,
            selected_source_ids=_selected_source_ids_from_state(state),
            errors=state.errors,
        )

    def build_plan(
        self,
        user_message: str,
        scenario: UserScenario,
        risk_level: RiskLevel,
        safety_flags: list[str] | None = None,
        missing_information: list[str] | None = None,
        selected_source_ids: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> EscalationPlan:
        safety_flags = safety_flags or []
        missing_information = missing_information or []
        selected_source_ids = selected_source_ids or []
        errors = errors or []

        triggers = self._build_triggers(
            scenario=scenario,
            risk_level=risk_level,
            safety_flags=safety_flags,
            missing_information=missing_information,
            errors=errors,
        )
        priority = _highest_priority([trigger.severity for trigger in triggers] or ["low"])
        escalation_required = bool(triggers)
        requires_human_review = escalation_required or priority in {"high", "urgent"}
        recommended_actions = list(
            dict.fromkeys(trigger.recommended_action for trigger in triggers)
        )
        handoff_summary = self.handoff_summary(
            user_message=user_message,
            scenario=scenario,
            risk_level=risk_level,
            triggers=triggers,
            missing_information=missing_information,
            selected_source_ids=selected_source_ids,
            safety_flags=safety_flags,
        )
        return EscalationPlan(
            escalation_required=escalation_required,
            requires_human_review=requires_human_review,
            priority=priority,
            triggers=triggers,
            recommended_actions=recommended_actions,
            handoff_summary=handoff_summary,
        )

    def create_case_draft_from_state(self, state: AgentState) -> CaseDraft:
        plan = self.build_plan_from_state(state)
        return self.create_case_draft(
            user_id=state.user_id,
            session_id=state.session_id,
            user_message=state.user_message,
            scenario=state.scenario,
            risk_level=state.risk_level,
            escalation_plan=plan,
            selected_source_ids=_selected_source_ids_from_state(state),
            safety_flags=state.safety_flags,
        )

    def create_case_draft(
        self,
        user_id: str | None,
        session_id: str | None,
        user_message: str,
        scenario: UserScenario,
        risk_level: RiskLevel,
        escalation_plan: EscalationPlan,
        selected_source_ids: list[str] | None = None,
        safety_flags: list[str] | None = None,
    ) -> CaseDraft:
        selected_source_ids = selected_source_ids or []
        safety_flags = safety_flags or []
        summary = escalation_plan.handoff_summary or self.handoff_summary(
            user_message=user_message,
            scenario=scenario,
            risk_level=risk_level,
            triggers=escalation_plan.triggers,
            selected_source_ids=selected_source_ids,
            safety_flags=safety_flags,
        )
        return CaseDraft(
            user_id=user_id,
            session_id=session_id,
            scenario=scenario,
            risk_level=risk_level,
            title=f"{scenario.value} case - {risk_level.value}",
            summary=summary,
            priority=escalation_plan.priority,
            escalation_reasons=[trigger.reason for trigger in escalation_plan.triggers],
            recommended_actions=escalation_plan.recommended_actions,
            source_ids=selected_source_ids,
            safety_flags=safety_flags,
        )

    def handoff_summary(
        self,
        user_message: str,
        scenario: UserScenario,
        risk_level: RiskLevel,
        triggers: list[EscalationTrigger],
        missing_information: list[str] | None = None,
        selected_source_ids: list[str] | None = None,
        safety_flags: list[str] | None = None,
    ) -> str:
        message_preview = " ".join(user_message.split())[:180]
        trigger_reasons = ", ".join(trigger.reason for trigger in triggers) or "none"
        missing_text = ", ".join(missing_information or []) or "none"
        source_text = ", ".join(selected_source_ids or []) or "none"
        flag_text = ", ".join(safety_flags or []) or "none"
        return (
            f"Scenario: {scenario.value}. Risk level: {risk_level.value}. "
            f"Message preview: {message_preview}. Triggers: {trigger_reasons}. "
            f"Missing information: {missing_text}. Selected sources: {source_text}. "
            f"Safety flags: {flag_text}."
        )

    def _build_triggers(
        self,
        scenario: UserScenario,
        risk_level: RiskLevel,
        safety_flags: list[str],
        missing_information: list[str],
        errors: list[str],
    ) -> list[EscalationTrigger]:
        triggers: list[EscalationTrigger] = []
        if risk_level_requires_escalation(risk_level):
            reason = scenario_default_escalation_reason(scenario, risk_level)
            triggers.append(
                EscalationTrigger(
                    trigger_type="risk_level",
                    severity=risk_level_priority(risk_level),
                    reason=reason,
                    recommended_action=escalation_reason_to_action(reason),
                    source="risk_classifier",
                )
            )

        for flag in safety_flags:
            if not safety_flag_requires_escalation(flag):
                continue
            triggers.append(
                EscalationTrigger(
                    trigger_type="safety_flag",
                    severity=safety_flag_priority(flag),
                    reason=flag,
                    recommended_action=escalation_reason_to_action(flag),
                    source="safety_flags",
                )
            )

        if risk_level_requires_escalation(risk_level) and missing_information:
            triggers.append(
                EscalationTrigger(
                    trigger_type="missing_information",
                    severity="medium",
                    reason="missing_information",
                    recommended_action=escalation_reason_to_action("missing_information"),
                    source="agent_state",
                )
            )

        for error in errors:
            if not _is_source_governance_error(error):
                continue
            triggers.append(
                EscalationTrigger(
                    trigger_type="source_governance",
                    severity="high",
                    reason="source_governance_failed",
                    recommended_action=escalation_reason_to_action(
                        "source_governance_failed"
                    ),
                    source="source_governance",
                )
            )

        return _dedupe_triggers(triggers)


def _selected_source_ids_from_state(state: AgentState) -> list[str]:
    source_ids: list[str] = []
    seen: set[str] = set()
    for retrieved_source in state.selected_sources:
        source_id = retrieved_source.source.source_id
        if source_id in seen:
            continue
        source_ids.append(source_id)
        seen.add(source_id)
    return source_ids


def _highest_priority(priorities: list[str]) -> str:
    return max(priorities, key=lambda priority: PRIORITY_ORDER[priority])


def _is_source_governance_error(error: str) -> bool:
    normalized = error.casefold()
    return any(marker in normalized for marker in SOURCE_GOVERNANCE_MARKERS)


def _dedupe_triggers(triggers: list[EscalationTrigger]) -> list[EscalationTrigger]:
    unique_triggers: list[EscalationTrigger] = []
    seen: set[tuple[str, str]] = set()
    for trigger in triggers:
        key = (trigger.trigger_type, trigger.reason)
        if key in seen:
            continue
        unique_triggers.append(trigger)
        seen.add(key)
    return unique_triggers
