from backend.app.domain.enums import LanguageCode, RiskLevel
from backend.app.multilingual.chinese_explainer import (
    ChineseExplanationResult,
    explain_chinese_text,
)
from backend.app.multilingual.detection import detect_language
from backend.app.multilingual.policies import choose_response_language
from backend.app.multilingual.templates import format_agent_answer


class MultilingualService:
    def detect_language(self, text: str) -> LanguageCode:
        return detect_language(text)

    def choose_response_language(
        self,
        detected_language: LanguageCode | None,
        preferred_language: LanguageCode | None = None,
    ) -> LanguageCode:
        return choose_response_language(detected_language, preferred_language)

    def format_answer(
        self,
        base_answer: str,
        language: LanguageCode,
        risk_level: RiskLevel,
        source_ids: list[str] | None = None,
        community_source_used: bool = False,
        escalation_required: bool = False,
    ) -> str:
        return format_agent_answer(
            base_answer=base_answer,
            language=language,
            risk_level=risk_level,
            source_ids=source_ids,
            community_source_used=community_source_used,
            escalation_required=escalation_required,
        )

    def explain_chinese_text(
        self,
        text: str,
        explanation_language: LanguageCode = LanguageCode.ru,
        risk_level: RiskLevel = RiskLevel.normal,
    ) -> ChineseExplanationResult:
        return explain_chinese_text(
            text=text,
            explanation_language=explanation_language,
            risk_level=risk_level,
        )
