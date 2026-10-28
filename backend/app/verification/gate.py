"""Fail-closed delivery gate shared by both offline agent runtimes."""

from typing import Any

from backend.app.answer_quality.composer import render_grounded_answer_markdown
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.answer_quality.models import GroundedAnswerDraft, GroundedAnswerSection
from backend.app.cloud_ai.grounded_review import BoundClaimReview
from backend.app.domain.agent import AgentState
from backend.app.domain.enums import RiskLevel
from backend.app.verification.answer_verifier import (
    build_answer_verification_request,
    verify_answer,
)

FALLBACK_COPY = {
    "en": (
        "I cannot confirm the details of this answer from the available evidence.",
        "Verify the current requirements with the relevant official service before acting.",
        "Contact an official service or a qualified human for help.",
        "If you are in immediate danger, contact local emergency services now. "
        "This app is not an official authority, a lawyer or a doctor.",
    ),
    "ru": (
        "Я не могу подтвердить детали ответа доступными источниками.",
        "Перед действием уточните актуальные требования в соответствующей официальной службе.",
        "Обратитесь в официальную службу или к профильному специалисту.",
        "При непосредственной опасности немедленно обратитесь в местную экстренную службу. "
        "Приложение не является официальным органом, юристом или врачом.",
    ),
    "kk": (
        "Жауаптың егжей-тегжейін қолжетімді дереккөздермен растай алмаймын.",
        "Әрекет етпес бұрын тиісті ресми қызметтен өзекті талаптарды нақтылаңыз.",
        "Ресми қызметке немесе тиісті маманға жүгініңіз.",
        "Тікелей қауіп болса, жергілікті шұғыл көмек қызметіне дереу хабарласыңыз. "
        "Қосымша ресми орган, заңгер немесе дәрігер емес.",
    ),
    "zh": (
        "现有证据无法确认该回答中的具体信息。",
        "采取行动前，请向相关官方机构核实最新要求。",
        "请联系官方机构或合格的专业人员寻求帮助。",
        "如有紧急危险，请立即联系当地应急服务。本应用不是官方机构、律师或医生。",
    ),
}


def verify_agent_answer(
    state: AgentState,
    *,
    evidence: list[Any] | None = None,
    domain: str | None = None,
    coverage_warnings: list[str] | None = None,
    reviewed_claims: BoundClaimReview | None = None,
) -> AgentState:
    request = build_answer_verification_request(
        answer_text=state.final_answer or state.draft_answer or "",
        scenario=state.scenario.value,
        risk_level=state.risk_level.value,
        domain=domain or state.scenario.value,
        evidence=state.selected_sources if evidence is None else evidence,
        source_notes=(state.grounded_answer or {}).get("source_notes", []),
        unreviewed_candidate_count=state.unreviewed_source_candidate_count,
        coverage_warnings=coverage_warnings or [],
    )
    report = verify_answer(request, reviewed_claims=reviewed_claims, citations=state.citations)
    state.answer_verification_report = report.model_dump(mode="json")
    for issue in report.issues:
        if issue.severity in {"warning", "error"}:
            # Never copy a rejected claim or its potentially private text into the trace.
            state.errors.append(f"answer_verification: {issue.code}")
    if report.passed:
        if report.max_severity == "warning":
            state.safety_flags.append("answer_verification_warning")
        return state

    state.safety_flags.extend(["answer_verification_failed", "unverified_answer_withheld"])
    if report.unsupported_claim_count:
        state.safety_flags.append("unsupported_claim_warning")
    state.escalation_required = True
    language = state.response_language.value
    direct, step, human, emergency = FALLBACK_COPY.get(language, FALLBACK_COPY["en"])
    steps = [GroundedAnswerSection(heading="", body=step)]
    if state.risk_level == RiskLevel.emergency:
        direct = emergency
        steps.insert(0, GroundedAnswerSection(heading="", body=emergency))
        steps.append(GroundedAnswerSection(heading="中文", body="请帮我联系急救服务。"))
    safe = GroundedAnswerDraft(
        scenario=state.scenario.value,
        risk_level=state.risk_level.value,
        language=language,
        direct_answer=direct,
        recommended_steps=steps,
        escalation=[human],
        uncertainty=[FALLBACK_COPY.get(language, FALLBACK_COPY["en"])[0]],
    )
    state.grounded_answer = safe.model_dump(mode="json")
    state.answer_quality_report = build_answer_quality_report(safe).model_dump(mode="json")
    state.citations = []
    state.checklist = None
    state.draft_answer = render_grounded_answer_markdown(safe)
    state.final_answer = state.draft_answer
    state.answer_verification_report["original_answer_withheld"] = True
    return state
