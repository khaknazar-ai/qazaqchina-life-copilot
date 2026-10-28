from typing import Any

from backend.app.demo.models import DemoRunResult, DemoScenario
from backend.app.domain.enums import UserScenario
from backend.app.moderation.service import CommunityModerationService
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.checklists import ChecklistCreateRequest
from backend.app.schemas.community import CommunityPostCreateRequest
from backend.app.schemas.translate import TranslateExplainRequest
from backend.app.services.chat_service import ChatService
from backend.app.services.checklist_service import ChecklistService
from backend.app.services.community_service import CommunityService
from backend.app.services.translation_service import TranslationService


class DemoScenarioRunner:
    def __init__(
        self,
        chat_service: ChatService | None = None,
        checklist_service: ChecklistService | None = None,
        translation_service: TranslationService | None = None,
        community_service: CommunityService | None = None,
    ) -> None:
        self.chat_service = chat_service
        self.checklist_service = checklist_service
        self.translation_service = translation_service
        self.community_service = community_service

    def run(self, scenario: DemoScenario) -> DemoRunResult:
        result = DemoRunResult(scenario=scenario)
        self._run_chat(scenario, result)

        if scenario.category in _CHECKLIST_SCENARIOS:
            self._run_checklist(scenario, result)
        else:
            result.notes.append("Scenario category does not have a checklist template.")

        if scenario.scenario_id == "chinese-notice-explanation":
            self._run_translation(scenario, result)

        if scenario.scenario_id in {
            "payment-scam-warning",
            "community-misinformation-conflict",
        }:
            self._run_moderation(scenario, result)

        if not _has_useful_output(result):
            result.notes.append("No optional demo service output was available.")

        result.source_ids = _dedupe(result.source_ids)
        result.safety_flags = _dedupe(result.safety_flags)
        result.notes = _dedupe(result.notes)
        return result

    def _run_chat(self, scenario: DemoScenario, result: DemoRunResult) -> None:
        chat_service = self.chat_service or ChatService(
            trace_service=_DemoTraceService(scenario.scenario_id),
            use_agent_workflow=True,
        )
        if chat_service.trace_service is None:
            chat_service.trace_service = _DemoTraceService(scenario.scenario_id)
        response = chat_service.create_response(
            ChatRequest(
                user_message=scenario.user_message,
                preferred_language=scenario.preferred_language,
            )
        )
        result.chat_response = _model_dump(response)
        result.safety_flags.extend(response.safety_flags)
        result.source_ids.extend(citation.source_id for citation in response.citations)
        if response.escalation_required:
            result.escalation_summary = (
                "Existing chat workflow marked human or official escalation as required."
            )
        if not response.citations:
            result.notes.append("Chat response did not expose citations for this scenario.")

    def _run_checklist(self, scenario: DemoScenario, result: DemoRunResult) -> None:
        checklist_service = self.checklist_service or ChecklistService(
            trace_service=_DemoTraceService(scenario.scenario_id),
        )
        response = checklist_service.create_checklist(
            ChecklistCreateRequest(
                scenario=scenario.category,
                language=scenario.preferred_language,
                risk_level=scenario.risk_hint,
                safety_flags=result.safety_flags,
            )
        )
        result.checklist = _model_dump(response)
        result.source_ids.extend(response.source_ids)
        if response.escalation_recommended and result.escalation_summary is None:
            result.escalation_summary = (
                "Checklist engine recommends human or official escalation."
            )
        if not response.source_ids:
            result.notes.append("Checklist response did not expose source IDs.")

    def _run_translation(self, scenario: DemoScenario, result: DemoRunResult) -> None:
        translation_service = self.translation_service or TranslationService(
            trace_service=_DemoTraceService(scenario.scenario_id),
        )
        response = translation_service.explain(
            TranslateExplainRequest(
                text=scenario.user_message,
                target_language=scenario.preferred_language,
            )
        )
        result.translation_explanation = _model_dump(response)
        if response.risk_level.value not in result.safety_flags:
            result.safety_flags.append(response.risk_level.value)
        if not response.key_terms:
            result.notes.append("Translation explanation did not expose key terms.")

    def _run_moderation(self, scenario: DemoScenario, result: DemoRunResult) -> None:
        community_service = self.community_service or CommunityService(
            trace_service=_DemoTraceService(scenario.scenario_id),
            moderation_service=CommunityModerationService(),
        )
        is_work_conflict = scenario.scenario_id == "community-misinformation-conflict"
        response = community_service.create_post(
            CommunityPostCreateRequest(
                title=(
                    "Synthetic demo work misinformation warning"
                    if is_work_conflict
                    else "Synthetic demo payment scam warning"
                ),
                city="Shanghai",
                scenario=UserScenario.work if is_work_conflict else UserScenario.payments,
                language=scenario.preferred_language,
                situation=(
                    "A community post claims cash work on a tourist visa is acceptable."
                    if is_work_conflict
                    else "A stranger offers guaranteed visa and payment setup help."
                ),
                what_happened=scenario.user_message,
                mistakes_to_avoid=[
                    (
                        "Do not rely on community claims that conflict with official "
                        "work-status requirements."
                    )
                    if is_work_conflict
                    else "Do not send money to unknown agents.",
                    (
                        "Do not start paid work until authorization is clear."
                        if is_work_conflict
                        else "Do not share payment verification codes."
                    ),
                ],
                advice_for_others=(
                    "Prefer official and qualified human guidance over community claims "
                    "for work-status questions."
                    if is_work_conflict
                    else "Use official bank, Alipay, or WeChat Pay channels and request "
                    "human review before trusting agent claims."
                ),
                tags=(
                    ["demo", "work-status", "source-conflict"]
                    if is_work_conflict
                    else ["demo", "payments", "scam-risk"]
                ),
                allow_ai_retrieval=True,
                self_declared_role="visitor",
            )
        )
        if response.moderation_result is None:
            result.notes.append("Community service did not expose moderation result.")
            return
        result.moderation_result = _model_dump(response.moderation_result)
        result.safety_flags.extend(response.moderation_result.review_reasons)


class _DemoTraceService:
    def __init__(self, scenario_id: str) -> None:
        self.trace_id = f"demo-{scenario_id}"

    def generate_trace_id(self) -> str:
        return self.trace_id

    def log_event(
        self,
        event_type: str,
        trace_id: str | None,
        payload: dict,
    ) -> dict[str, Any]:
        return {"event_type": event_type, "trace_id": trace_id or self.trace_id, "payload": payload}

    def log_service_start(
        self,
        service_name: str,
        trace_id: str,
        payload: dict,
    ) -> dict[str, Any]:
        return self.log_event(
            event_type="service.start",
            trace_id=trace_id,
            payload={"service_name": service_name, "status": "started", **payload},
        )

    def log_service_end(
        self,
        service_name: str,
        trace_id: str,
        payload: dict,
    ) -> dict[str, Any]:
        return self.log_event(
            event_type="service.end",
            trace_id=trace_id,
            payload={"service_name": service_name, "status": "completed", **payload},
        )


_CHECKLIST_SCENARIOS = {
    UserScenario.tourism,
    UserScenario.kazakhstan_entry,
    UserScenario.study,
    UserScenario.work,
    UserScenario.medical,
    UserScenario.emergency,
    UserScenario.payments,
    UserScenario.housing,
}


def _model_dump(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def _has_useful_output(result: DemoRunResult) -> bool:
    return any(
        output is not None
        for output in (
            result.chat_response,
            result.checklist,
            result.translation_explanation,
            result.moderation_result,
        )
    ) or bool(result.notes)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
