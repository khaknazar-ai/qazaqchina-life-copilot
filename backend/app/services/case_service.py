from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from backend.app.domain.cases import UserCase
from backend.app.domain.enums import CaseStatus, EscalationReason
from backend.app.escalation.models import CaseDraft
from backend.app.persistence.base import CaseRepositoryProtocol
from backend.app.schemas.cases import CaseCreateRequest, CaseListResponse, CaseResponse
from backend.app.services.trace_service import TraceService


class CaseService:
    def __init__(
        self,
        trace_service: TraceService | None = None,
        case_repository: CaseRepositoryProtocol | None = None,
    ) -> None:
        self.trace_service = trace_service
        self.case_repository = case_repository

    def create_case(self, request: CaseCreateRequest) -> CaseResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="case.create_case",
                trace_id=trace_id,
                payload={
                    "case_type": request.case_type.value,
                    "city": request.city,
                    "has_user_id": request.user_id is not None,
                },
            )

        now = datetime.now(UTC)
        raw_case_key = f"{request.user_id}|{request.case_type.value}|{request.city}"
        case = UserCase(
            case_id=f"CASE-{uuid5(NAMESPACE_URL, raw_case_key).hex[:12].upper()}",
            user_id=request.user_id,
            case_type=request.case_type,
            city=request.city,
            status=CaseStatus.open,
            created_at=now,
            updated_at=now,
        )
        self._save_case(case)
        response = CaseResponse(case=case)

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="case.create_case",
                trace_id=trace_id,
                payload={
                    "case_type": case.case_type.value,
                    "city": case.city,
                    "status": case.status.value,
                    "escalation_required": case.escalation_required,
                },
            )

        return response

    def list_cases(self) -> CaseListResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="case.list_cases",
                trace_id=trace_id,
                payload={},
            )

        response = CaseListResponse(
            cases=self.case_repository.list_cases() if self.case_repository else []
        )

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="case.list_cases",
                trace_id=trace_id,
                payload={"returned_case_count": len(response.cases)},
            )

        return response

    def create_case_from_draft(self, draft: CaseDraft) -> CaseResponse:
        now = datetime.now(UTC)
        raw_case_key = (
            f"{draft.user_id}|{draft.session_id}|{draft.scenario.value}|"
            f"{draft.risk_level.value}|{draft.summary}"
        )
        case = UserCase(
            case_id=f"CASE-{uuid5(NAMESPACE_URL, raw_case_key).hex[:12].upper()}",
            user_id=draft.user_id,
            case_type=draft.scenario,
            risk_level=draft.risk_level,
            status=(
                CaseStatus.escalated
                if draft.priority in {"high", "urgent"}
                else CaseStatus.open
            ),
            escalation_required=bool(draft.escalation_reasons),
            escalation_reasons=_case_escalation_reasons(draft.escalation_reasons),
            created_at=now,
            updated_at=now,
        )
        self._save_case(case)
        return CaseResponse(case=case)

    def _save_case(self, case: UserCase) -> None:
        if self.case_repository:
            self.case_repository.save_case(case)


def _case_escalation_reasons(reasons: list[str]) -> list[EscalationReason]:
    mapped_reasons: list[EscalationReason] = []
    for reason in reasons:
        mapped_reason = _case_escalation_reason(reason)
        if mapped_reason is not None and mapped_reason not in mapped_reasons:
            mapped_reasons.append(mapped_reason)
    return mapped_reasons


def _case_escalation_reason(reason: str) -> EscalationReason | None:
    try:
        return EscalationReason(reason)
    except ValueError:
        pass
    if reason in {"prompt_injection", "unsafe", "unsafe_work_advice", "safety_risk"}:
        return EscalationReason.safety_risk
    if reason in {
        "source_governance_failed",
        "source_conflict",
        "missing_official_source",
        "high_risk_without_official_source",
        "citation_verification_failed",
    }:
        return EscalationReason.source_conflict
    if reason == "missing_information":
        return EscalationReason.missing_critical_info
    return None
