import re
from typing import TYPE_CHECKING

from pydantic import ValidationError

from backend.app.agent.classification import classify_risk
from backend.app.cloud_ai.client import CloudAIError, QwenCloudClient
from backend.app.cloud_ai.documents import CloudDocumentService
from backend.app.cloud_ai.semantic_review import CloudOperation
from backend.app.domain.enums import LanguageCode, RiskLevel
from backend.app.multilingual.detection import contains_chinese, detect_language
from backend.app.multilingual.service import MultilingualService
from backend.app.schemas.translate import TranslateExplainRequest, TranslateExplainResponse
from backend.app.services.trace_service import TraceService

if TYPE_CHECKING:
    from backend.app.llm.ollama import OllamaClient


class TranslationService:
    def __init__(
        self,
        trace_service: TraceService | None = None,
        multilingual_service: MultilingualService | None = None,
        cloud_client: QwenCloudClient | None = None,
        local_client: "OllamaClient | None" = None,
    ) -> None:
        self.trace_service = trace_service
        self.multilingual_service = multilingual_service or MultilingualService()
        self.local_inference = local_client is not None
        if local_client is not None:
            from backend.app.llm.ollama import OllamaClient, validate_ollama_settings

            if not isinstance(local_client, OllamaClient) or validate_ollama_settings(
                local_client.settings
            ) != local_client.base_url:
                raise ValueError("Local translation requires validated loopback Ollama")
        self.cloud_client = local_client if local_client is not None else cloud_client

    def explain(self, request: TranslateExplainRequest) -> TranslateExplainResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="translation",
                trace_id=trace_id,
                payload={
                    "text_length": len(request.text),
                    "target_language": request.target_language.value,
                    "has_user_context": request.user_context is not None,
                },
            )

        detected_language = self.detect_language(request.text)
        risk_level = self.classify_translation_risk(
            request.text + "\n" + (request.user_context or "")
        )
        chinese_explanation = self.multilingual_service.explain_chinese_text(
            text=request.text,
            explanation_language=request.target_language,
            risk_level=risk_level,
        )
        suggested_reply = "请确认这条信息的意思和需要我做的事。谢谢。" if (
            detected_language == LanguageCode.zh
        ) else None

        response = TranslateExplainResponse(
            detected_language=detected_language,
            translated_summary=chinese_explanation.summary,
            explanation=chinese_explanation.summary,
            # Keyword matching cannot establish an obligation or negate it.
            required_actions=[],
            risk_level=risk_level,
            suggested_reply_zh=suggested_reply,
            key_terms=chinese_explanation.key_terms,
            warnings=chinese_explanation.warnings,
            disclaimer=chinese_explanation.disclaimer,
            original_text=chinese_explanation.original_text,
            limitations=[chinese_explanation.disclaimer],
            metadata={"used_network": False, "used_provider_call": False,
                      "cloud_status": "disabled", "is_official_evidence": False},
        )

        if self.cloud_client and (detected_language == LanguageCode.zh or self.local_inference):
            if risk_level in {RiskLevel.emergency, RiskLevel.unsafe, RiskLevel.prompt_injection}:
                response.metadata["cloud_status"] = "skipped_safety"
            else:
                self._cloud_explain(request, response)
        if self.local_inference:
            response.metadata.update(
                inference_backend="ollama", used_external_network=False,
                ollama_status=response.metadata.get("cloud_status"),
            )

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="translation",
                trace_id=trace_id,
                payload={
                    "text_length": len(request.text),
                    "detected_language": detected_language.value,
                    "risk_level": risk_level.value,
                    "required_action_count": len(response.required_actions),
                    "mode": response.mode,
                    "verification_status": response.verification_status,
                    "inference_backend": "ollama" if self.local_inference else (
                        "cloud" if self.cloud_client else "offline"
                    ),
                    "provider_status": response.metadata.get("cloud_status", "disabled"),
                    "provider_calls": response.metadata.get("provider_calls", 0),
                },
            )

        return response

    def _cloud_explain(
        self, request: TranslateExplainRequest, response: TranslateExplainResponse,
    ) -> None:
        operation = CloudOperation(self.cloud_client)
        try:
            effective = request.model_copy(update={"target_language": LanguageCode.ru}) if (
                request.target_language == LanguageCode.unknown
            ) else request
            language = effective.target_language.value
            segments, usage = CloudDocumentService(operation).explain(effective)
            response.mode = "cloud_verified"
            response.verification_status = "semantic_model_review"
            response.segments = segments
            response.translated_summary = "\n".join(s.translation for s in segments)
            response.explanation = response.translated_summary
            labels = {
                "ru": "В тексте указано", "kk": "Мәтінде көрсетілген",
                "zh": "原文说明", "en": "The document states",
            }
            label = labels[language]
            response.required_actions = [
                f"{label}: {action}" for segment in segments for action in segment.required_actions
            ]
            response.disclaimer = {
                "ru": "Перевод проверен моделью и может содержать ошибки. Это не проверка "
                      "подлинности документа, не официальное требование и не согласие с ним.",
                "kk": "Аударманы модель тексерді, қателер болуы мүмкін. Бұл құжаттың "
                      "түпнұсқалығын растау, ресми талап немесе оған келісім емес.",
                "zh": "翻译经过模型复核，仍可能有误。这不是文件真伪验证、官方要求或对内容的同意。",
                "en": "Translation was reviewed by a model and may contain errors. This does "
                      "not authenticate the document, establish official requirements "
                      "or agree to it.",
            }[language]
            response.limitations = [response.disclaimer]
            response.metadata.update(
                usage, cloud_status="generated", critical_spans_heuristic=True,
            )
        except CloudAIError as exc:
            response.metadata["cloud_status"] = exc.code
            if exc.code == "document_original_requires_review":
                message = {
                    "ru": "Часть исходного текста удалена или помечена как недоступная из-за "
                          "личных данных. Полный смысл и условия не проверены. Перед действиями "
                          "сверьте полный оригинал с человеком, которому доверяете.",
                    "kk": "Жеке деректерге байланысты бастапқы мәтіннің бір бөлігі өшірілген "
                          "немесе қолжетімсіз деп белгіленген. Толық мағынасы мен шарттары "
                          "тексерілмеген. Әрекет етпес бұрын толық түпнұсқаны сенімді "
                          "адаммен тексеріңіз.",
                    "zh": "原文部分内容因个人信息被删除或标记为不可用，完整含义和条件未经核实。"
                          "采取行动前，请与可信赖的人核对完整原文。",
                    "en": "Private material was removed or marked unavailable, so the full "
                          "meaning and conditions are unverified. Check the complete original "
                          "with a trusted person before acting.",
                }[language]
                response.translated_summary = message
                response.explanation = message
                response.warnings.append(message)
                response.limitations.append(message)
                response.metadata["original_requires_review"] = True
        except (ValidationError, ValueError, TypeError):
            # Validation errors contain original provider text; never expose them.
            response.metadata.update(
                cloud_status="cloud_invalid_document",
            )
        finally:
            response.metadata.update(operation.metadata)

    def detect_language(self, text: str) -> LanguageCode:
        return detect_language(text)

    def extract_required_actions(self, text: str) -> list[str]:
        """Legacy local review hints, never interpreted requirements for delivery."""
        actions: list[str] = []

        if "\u767b\u8bb0" in text:
            actions.append("A registration term occurs; verify the full sentence and any negation.")
        if "\u62a4\u7167" in text:
            actions.append(
                "A passport term occurs; verify whether it is required or explicitly not required."
            )
        if re.search(r"(?:三|(?<!\d)3)\s*(?:日|天)(?:内|之内|以内)?", text):
            actions.append("Possible 3-day deadline mentioned; confirm the exact due date.")

        return actions

    def classify_translation_risk(self, text: str) -> RiskLevel:
        # Classification is local and never logs or transmits this value. Masking
        # identifiers first can erase a passport/visa term or an active safety
        # instruction, causing a sensitive document to become ordinary input.
        shared = classify_risk(text)
        if shared != RiskLevel.normal:
            return shared
        if "\u8b66\u5bdf" in text or "\u62a5\u6848" in text:
            return RiskLevel.emergency
        if "\u533b\u9662" in text or "\u75c5" in text:
            return RiskLevel.medical_sensitive
        if self.extract_required_actions(text):
            return RiskLevel.medium
        return RiskLevel.normal
def _contains_chinese(text: str) -> bool:
    return contains_chinese(text)
