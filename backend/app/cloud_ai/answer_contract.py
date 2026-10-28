"""Evidence selection plus bounded claims requiring a separate semantic review.

Exact quotes alone do not verify paraphrase or applicability. The legacy selection
mode stays deterministic; every new prose item needs a bound original passage,
semantic model review, and the existing safety gate before delivery.
"""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.sources import SourceReference
from backend.app.memory.redaction import redact_sensitive_text

StepId = Literal[
    "clarify_goal",
    "clarify_city",
    "clarify_timing",
    "clarify_context",
    "prepare_questions",
    "verify_official",
    "human_help",
    "check_original",
]
LANGUAGES = ("ru", "kk", "zh", "en")
COPY = {
    "grounded": (
        "Ниже приведены выдержки из доступных источников на языке оригинала. "
        "Уточните в официальной службе, применимы ли они к вашей ситуации.",
        "Төменде қолжетімді дереккөздерден түпнұсқа тіліндегі үзінділер берілген. "
        "Олардың жағдайыңызға қатысты екенін ресми қызметтен нақтылаңыз.",
        "以下是可用来源的原文摘录。请向官方机构核实是否适用于您的情况。",
        "Below are excerpts from available sources in their original language. "
        "Confirm with the official service whether they apply to your situation.",
    ),
    "clarification": (
        "Пока недостаточно подтверждённых сведений для конкретного ответа. Уточним ваш вопрос.",
        "Нақты жауап беру үшін расталған мәлімет жеткіліксіз. Сұрағыңызды нақтылайық.",
        "目前没有足够的已核实信息提供具体答复。请补充您的问题。",
        "There is not enough verified information for a specific answer yet. "
        "Let us clarify your question.",
    ),
    "clarify_goal": (
        "Что именно вы хотите узнать или сделать?",
        "Нені білгіңіз немесе жасағыңыз келеді?",
        "您具体想了解或办理什么？",
        "What exactly would you like to know or do?",
    ),
    "clarify_city": (
        "В каком городе нужна помощь? Точный адрес не указывайте.",
        "Қай қалада көмек керек? Нақты мекенжайды жазбаңыз.",
        "您需要在哪个城市获得帮助？请勿提供详细住址。",
        "Which city do you need help in? Do not include a street address.",
    ),
    "clarify_timing": (
        "Насколько срочен ваш вопрос?",
        "Сұрағыңыз қаншалықты шұғыл?",
        "您的问题有多紧急？",
        "How urgent is your question?",
    ),
    "clarify_context": (
        "Опишите нужные обстоятельства без имён, номеров документов и контактов.",
        "Қажетті жағдайларды аты-жөнсіз, құжат нөмірлерінсіз "
        "және байланыс деректерінсіз сипаттаңыз.",
        "请描述相关情况，不要提供姓名、证件号码或联系方式。",
        "Describe the relevant circumstances without names, document numbers or contact details.",
    ),
    "prepare_questions": (
        "Запишите вопросы, которые хотите уточнить в соответствующей службе.",
        "Тиісті қызметтен нақтылағыңыз келетін сұрақтарды жазып алыңыз.",
        "列出您想向相关机构核实的问题。",
        "List the questions you want to clarify with the relevant service.",
    ),
    "verify_official": (
        "Перед действием уточните актуальные условия в соответствующей официальной службе.",
        "Әрекет етпес бұрын тиісті ресми қызметтен өзекті шарттарды нақтылаңыз.",
        "采取行动前，请向相关官方机构核实最新条件。",
        "Before acting, verify current conditions with the relevant official service.",
    ),
    "human_help": (
        "Если информации недостаточно или она противоречива, обратитесь к профильному специалисту.",
        "Ақпарат жеткіліксіз немесе қайшы болса, тиісті маманға жүгініңіз.",
        "如果信息不足或相互矛盾，请联系相关专业人员。",
        "If information is insufficient or conflicting, contact a qualified person for help.",
    ),
    "check_original": (
        "Сверьте распознанный текст с оригиналом, особенно даты, суммы и отрицания.",
        "Танылған мәтінді түпнұсқамен, әсіресе күндер, сомалар және терістеулерді салыстырыңыз.",
        "请将识别文本与原件核对，尤其是日期、金额和否定词。",
        "Compare the extracted text with the original, especially dates, amounts and negations.",
    ),
}


def localized(key: str, language: str) -> str:
    return COPY[key][LANGUAGES.index(language) if language in LANGUAGES else 3]


class GroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^claim-[1-6]$")
    kind: Literal["fact", "action"]
    text: str = Field(min_length=1, max_length=900)
    passage_ids: list[str] = Field(min_length=1, max_length=3)


class CloudAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passage_ids: list[str] = Field(default_factory=list, max_length=5)
    next_step_ids: list[StepId] = Field(default_factory=list, max_length=4)
    claims: list[GroundedClaim] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def meaningful_answer(self) -> "CloudAnswer":
        if not self.passage_ids and not self.next_step_ids and not self.claims:
            raise ValueError("An answer needs evidence, a supported claim or a clarification step")
        return self


class SourcePassage(BaseModel):
    passage_id: str
    source_id: str
    text: str


def source_passages(sources: list[SourceReference]) -> list[SourcePassage]:
    result = []
    for source in sources:
        # A paragraph can depend on an exception, cancellation or condition in a
        # later paragraph. Only a complete bounded source entry is eligible here;
        # official-source ingestion must prepare reviewed self-contained entries
        # instead of letting generation isolate a convenient paragraph.
        for text in answer_texts(source):
            digest = hashlib.sha256((source.source_id + "\0" + text).encode()).hexdigest()[:24]
            result.append(
                SourcePassage(
                    passage_id="passage-" + digest,
                    source_id=source.source_id,
                    text=text,
                )
            )
            if len(result) >= 8:
                return result
    return result


def answer_texts(source: SourceReference) -> list[str]:
    """Use a complete entry or exact passages explicitly reviewed with its full body."""
    body = source.content or ""
    if source.reviewed_answer_passages_complete:
        # An explicit current publication review can attest a self-contained unit
        # even when unrelated sections make the complete parent short enough to fit.
        # Legacy passage lists never imply that the omitted conditions were checked.
        if not _current_passage_attestation(source):
            return []
        return _reviewed_passages(source, require_boundaries=True)
    safe, findings = redact_sensitive_text(body)
    complete = safe.strip()
    # A privacy match can span a later exception or prohibition. A changed
    # original cannot be treated as complete evidence; use only unchanged
    # passages that were explicitly reviewed against the preserved parent.
    if not findings and complete == body.strip() and 12 <= len(complete) <= 2400:
        return [complete]
    return _reviewed_passages(source)


def _current_passage_attestation(source: SourceReference) -> bool:
    from datetime import UTC, datetime

    from backend.app.agent.classification import (
        has_active_prompt_injection,
        requests_document_forgery,
    )
    from backend.app.embeddings.safety import eligible_cloud_source

    reviewed = source.last_reviewed_at or source.reviewed_at
    expires = source.expires_at
    now = datetime.now(UTC)
    if (
        source.status_override != "published" or source.moderation_status != "approved"
        or reviewed is None or reviewed.tzinfo is None or reviewed > now
        or expires is None or expires.tzinfo is None or expires <= now
        or not (source.reviewed_by or "").strip()
        or has_active_prompt_injection(source.content or "")
        or requests_document_forgery(source.content or "")
    ):
        return False
    risk = next((item.value for item in source.risk_tags if item not in {"normal", "medium"}), None)
    return eligible_cloud_source(
        source, scenario=source.scenario.value if source.scenario else None, risk_level=risk,
    ) and source.source_type.value in {"official", "curated_guide"}


def _reviewed_passages(source: SourceReference, *, require_boundaries: bool = False) -> list[str]:
    body = source.content or ""
    if not source.reviewed_answer_passages or len(source.reviewed_answer_passages) > 12:
        return []
    # This ties the server-controlled review to the preserved parent text. A stale
    # passage list cannot survive a content edit or be used as a stand-alone source.
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != source.content_hash:
        return []
    result = []
    for passage in source.reviewed_answer_passages:
        if not 12 <= len(passage) <= 2400 or passage != passage.strip() or passage not in body:
            return []
        safe, findings = redact_sensitive_text(passage)
        if findings or safe != passage:
            return []
        if require_boundaries:
            from backend.app.source_corpus.service import SourceCorpusService

            try:
                SourceCorpusService._verify_passage(body, passage)
            except ValueError:
                return []
        if passage not in result:
            result.append(passage)
    return result
