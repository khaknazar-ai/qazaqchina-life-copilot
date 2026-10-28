from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.enums import LanguageCode, RiskLevel


class TranslateExplainRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    target_language: LanguageCode = LanguageCode.ru
    user_context: str | None = Field(default=None, max_length=2000)


class DocumentSegment(BaseModel):
    passage_id: str
    original_quote: str
    translation: str
    required_actions: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    negations: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)


class TranslateExplainResponse(BaseModel):
    detected_language: LanguageCode
    translated_summary: str
    explanation: str
    required_actions: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    suggested_reply_zh: str | None = None
    key_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str | None = None
    mode: Literal["cloud_verified", "document_limited"] = "document_limited"
    original_text: str = ""
    segments: list[DocumentSegment] = Field(default_factory=list)
    verification_status: str = "not_semantically_verified"
    limitations: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
