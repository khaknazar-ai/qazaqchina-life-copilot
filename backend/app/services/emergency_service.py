from uuid import NAMESPACE_URL, uuid5

from backend.app.domain.enums import RiskLevel
from backend.app.schemas.emergency import EmergencyHelpRequest, EmergencyHelpResponse
from backend.app.services.emergency_copy import emergency_copy, emergency_specific_step
from backend.app.services.trace_service import TraceService

LOST_PASSPORT_PHRASE_ZH = (
    "\u6211\u7684\u62a4\u7167\u4e22\u4e86\uff0c"
    "\u8bf7\u95ee\u6211\u5e94\u8be5\u53bb\u54ea\u91cc\u62a5\u6848\uff1f"
)


class EmergencyService:
    def __init__(self, trace_service: TraceService | None = None) -> None:
        self.trace_service = trace_service

    def classify_emergency_type(self, message: str) -> str:
        normalized = message.casefold()

        if _contains_any(normalized, ["passport", "паспорт", "护照"]) and _contains_any(
            normalized, ["lost", "потер", "丢", "жоғ"]
        ):
            return "lost_passport"
        if _contains_any(
            normalized,
            [
                "hospital",
                "doctor",
                "больниц",
                "врач",
                "医院",
                "病",
                "аурухана",
                "дәрігер",
            ],
        ):
            return "hospital_visit"
        if _contains_any(normalized, ["phone", "телефон", "手机"]) and _contains_any(
            normalized, ["lost", "потер", "丢", "жоғ"]
        ):
            return "lost_phone"
        if _contains_any(normalized, ["work", "работ", "безвиз", "tourist visa"]):
            return "work_status_problem"
        if _contains_any(normalized, ["document", "документ", "visa", "签证"]):
            return "document_problem"

        return "unknown_emergency"

    def create_help_response(self, request: EmergencyHelpRequest) -> EmergencyHelpResponse:
        trace_id = self._stable_trace_id(request)
        if self.trace_service:
            self.trace_service.log_service_start(
                service_name="emergency",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "language": request.language.value,
                },
            )

        emergency_type = self.classify_emergency_type(request.user_message)
        risk_level = self._risk_for_emergency_type(emergency_type)
        steps, disclaimer = emergency_copy(request.language)
        specific = emergency_specific_step(request.language, emergency_type)
        if specific:
            steps.append(specific)
        phrase = {
            "lost_passport": LOST_PASSPORT_PHRASE_ZH,
            "hospital_visit": "我需要医疗帮助，请帮我联系当地急救服务。",
            "lost_phone": "我的手机丢了，请帮我联系相关工作人员。",
        }.get(emergency_type, "我需要帮助，请帮我联系相关工作人员。")

        response = EmergencyHelpResponse(
            trace_id=trace_id,
            emergency_type=emergency_type,
            risk_level=risk_level,
            immediate_steps=steps,
            chinese_phrase=phrase,
            escalation_required=True,
            disclaimer=disclaimer,
        )

        if self.trace_service:
            self.trace_service.log_service_end(
                service_name="emergency",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "emergency_type": emergency_type,
                    "risk_level": risk_level.value,
                    "escalation_required": response.escalation_required,
                },
            )

        return response

    @staticmethod
    def _risk_for_emergency_type(emergency_type: str) -> RiskLevel:
        if emergency_type == "hospital_visit":
            return RiskLevel.medical_sensitive
        return RiskLevel.emergency

    @staticmethod
    def _stable_trace_id(request: EmergencyHelpRequest) -> str:
        raw = f"{request.user_message}|{request.city}|{request.language.value}"
        return str(uuid5(NAMESPACE_URL, raw))


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)
