from backend.app.checklist_engine.models import ChecklistGenerationRequest
from backend.app.checklist_engine.service import ChecklistEngineService
from backend.app.domain.checklists import ChecklistItem
from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.schemas.checklists import ChecklistCreateRequest, ChecklistResponse
from backend.app.services.trace_service import TraceService


class ChecklistService:
    def __init__(
        self,
        trace_service: TraceService | None = None,
        checklist_engine_service: ChecklistEngineService | None = None,
    ) -> None:
        self.trace_service = trace_service
        self.checklist_engine_service = checklist_engine_service or ChecklistEngineService()

    def create_checklist(self, request: ChecklistCreateRequest) -> ChecklistResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="checklist",
                trace_id=trace_id,
                payload={
                    "scenario": request.scenario.value,
                    "city": request.city,
                    "language": request.language.value,
                    "risk_level": (
                        request.risk_level.value if request.risk_level else None
                    ),
                },
            )

        risk_level = request.risk_level or self._risk_for_checklist_item(request.scenario)
        result = self.checklist_engine_service.generate(
            ChecklistGenerationRequest(
                scenario=request.scenario,
                risk_level=risk_level,
                language=request.language,
                selected_source_ids=request.selected_source_ids,
                safety_flags=request.safety_flags,
            )
        )
        response = ChecklistResponse(
            checklist=result.checklist,
            warnings=result.warnings,
            source_ids=result.source_ids,
            escalation_recommended=result.escalation_recommended,
        )

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="checklist",
                trace_id=trace_id,
                payload={
                    "scenario": request.scenario.value,
                    "city": request.city,
                    "item_count": len(result.checklist.items),
                    "warning_count": len(result.warnings),
                    "escalation_recommended": result.escalation_recommended,
                },
            )

        return response

    def _items_for_scenario(self, scenario: UserScenario) -> list[ChecklistItem]:
        result = self.checklist_engine_service.generate_for_scenario(
            scenario=scenario,
            risk_level=self._risk_for_checklist_item(scenario),
        )
        return result.checklist.items

    @staticmethod
    def _risk_for_checklist_item(scenario: UserScenario) -> RiskLevel:
        if scenario == UserScenario.emergency:
            return RiskLevel.emergency
        if scenario == UserScenario.work:
            return RiskLevel.work_status_sensitive
        if scenario == UserScenario.medical:
            return RiskLevel.medical_sensitive
        return RiskLevel.normal
