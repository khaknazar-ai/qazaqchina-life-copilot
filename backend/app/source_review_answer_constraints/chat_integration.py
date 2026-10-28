from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.app.schemas.chat import ChatResponse
    from backend.app.source_registry.registry import SourceRegistry

from backend.app.agent.classification import is_kazakhstan_entry_request
from backend.app.source_review_answer_constraints.localization import COPY
from backend.app.source_review_answer_constraints.models import (
    SourceReviewAnswerConstraint,
    SourceReviewAnswerConstraintsReport,
)
from backend.app.source_review_answer_constraints.service import (
    SourceReviewAnswerConstraintsService,
)

VISA_EXTENSION_DOMAIN = "visa_extension"
RESIDENCE_REGISTRATION_DOMAIN = "residence_registration"
KAZAKHSTAN_ENTRY_DOMAIN = "kazakhstan_entry_visa"

VISA_EXTENSION_KEYWORDS = (
    "visa extension",
    "extend visa",
    "extend my visa",
    "visa renewal",
    "visa expired",
    "extend my stay",
    "签证延期",
    "продлить визу",
    "продление визы",
    "визаны ұзарту",
    "визамды ұзарту",
    "签证续签",
)

RESIDENCE_REGISTRATION_KEYWORDS = (
    "residence registration",
    "accommodation registration",
    "register my accommodation",
    "register my accommodation with the police",
    "register accommodation with the police",
    "temporary residence",
    "police registration",
    "registration with police",
    "регистрация проживания",
    "регистрацию проживания",
    "сделать регистрацию проживания",
    "регистрация проживания в полиции",
    "регистрацию проживания в полиции",
    "登记住宿",
    "住宿登记",
    "регистрация проживания",
    "регистрация в полиции",
    "тұрғылықты жер",
    "тұратын жерді тіркеу",
)

UNPUBLISHED_CANDIDATE_REFERENCE_MARKERS = (
    "official-source-candidate",
    "configs/source_review",
    "official_source_candidate_intake",
    "official_source_review_evidence",
    "example.invalid/source-page",
    "example.invalid/regulation",
)

RUNTIME_SUPPORT_NOTICE = {
    "en": "The cited sources support only the facts shown here, not the complete procedure. "
    "Confirm current local requirements with the relevant official service before acting.",
    "ru": "Источники подтверждают только приведённые факты, а не всю процедуру. "
    "Перед действием уточните актуальные местные требования в соответствующей официальной службе.",
    "kk": "Дереккөздер бүкіл рәсімді емес, тек берілген фактілерді растайды. "
    "Әрекет етпес бұрын тиісті ресми қызметтен өзекті жергілікті талаптарды нақтылаңыз.",
    "zh": "所引来源仅支持此处列出的事实，并不涵盖完整办理流程。"
    "采取行动前，请向相关官方机构核实当前当地要求。",
}


def runtime_support_source_ids(
    response: "ChatResponse", registry: "SourceRegistry | None", *,
    domain: str, city: str | None, user_message: str,
) -> list[str]:
    """Qualify delivered facts; the final ledger gate must still admit this snapshot."""
    import hashlib

    from backend.app.answer_quality.composer import (
        compose_grounded_answer,
        render_grounded_answer_markdown,
    )
    from backend.app.answer_quality.localization import copy
    from backend.app.answer_quality.models import GroundedAnswerDraft
    from backend.app.answer_quality.policies import build_source_note
    from backend.app.checklist_engine.service import ChecklistEngineService
    from backend.app.cloud_ai.answer_contract import StepId, localized
    from backend.app.domain.enums import LanguageCode, RiskLevel, SourceType
    from backend.app.embeddings.safety import eligible_cloud_source

    report = response.answer_verification_report or {}
    if (
        registry is None or report.get("passed") is not True or not response.citations
        or report.get("unsupported_claim_count", 0) != 0
        or response.risk_level in {
            RiskLevel.emergency, RiskLevel.unsafe, RiskLevel.prompt_injection,
        }
    ):
        return []
    try:
        draft = GroundedAnswerDraft.model_validate(response.grounded_answer)
    except (ValueError, TypeError):
        return []
    if (
        not draft.grounded_facts
        or render_grounded_answer_markdown(draft) != response.answer
        or draft.scenario != response.scenario.value
        or draft.risk_level != response.risk_level.value
    ):
        return []
    sources = registry.all_sources()
    by_id = {source.source_id: source for source in sources}
    if len(by_id) != len(sources):
        return []
    ids = list(dict.fromkeys(citation.source_id for citation in response.citations))
    if (len(draft.source_notes) != len(ids)
            or {note.source_id for note in draft.source_notes} != set(ids)):
        return []
    for source_id in ids:
        source = by_id.get(source_id)
        if (
            source is None
            or source.source_type not in {SourceType.official, SourceType.curated_guide}
            or source.status_override != "published"
            or source.moderation_status != "approved"
            or source.scenario != response.scenario
            or hashlib.sha256((source.content or "").encode()).hexdigest() != source.content_hash
            or detect_source_review_constraint_domain(
                f"{source.title} {source.content or ''}"
            ) != domain
            or not eligible_cloud_source(
                source, scenario=response.scenario.value, risk_level=response.risk_level.value,
                domain=domain, city=city, enforce_city_scope=True,
            )
        ):
            return []
        note = next(note for note in draft.source_notes if note.source_id == source_id)
        if note != build_source_note(source):
            return []
    sections = [*draft.grounded_facts, *(s for s in draft.recommended_steps if s.source_ids)]
    if any(not section.source_ids or not set(section.source_ids) <= set(ids)
           for section in sections):
        return []
    baseline = compose_grounded_answer(
        user_message, [by_id[sid] for sid in ids], scenario=response.scenario.value,
        risk_level=response.risk_level.value, language=draft.language,
        unreviewed_candidate_count=draft.unreviewed_candidate_count,
    )
    if draft.direct_answer not in {
        baseline.direct_answer, localized("grounded", draft.language),
        *(section.body for section in draft.grounded_facts),
    }:
        return []
    # Unsourced guidance is fixed application copy, never an additional claim
    # smuggled alongside a valid citation and an earlier verification report.
    from typing import get_args

    safe_steps = {(section.heading, section.body) for section in baseline.recommended_steps}
    safe_steps.update(("", localized(step, draft.language)) for step in get_args(StepId))
    if any((section.heading, section.body) not in safe_steps or section.warnings
           for section in draft.recommended_steps if not section.source_ids):
        return []
    checklist = ChecklistEngineService().generate_for_scenario(
        scenario=response.scenario, risk_level=response.risk_level,
        language=LanguageCode(draft.language or "en"), selected_source_ids=ids,
        safety_flags=response.safety_flags,
    ).checklist
    if not set(draft.checklist_items) <= {item.title for item in checklist.items}:
        return []
    for field in ("uncertainty", "escalation", "warnings"):
        allowed = set(getattr(baseline, field))
        if field in {"uncertainty", "warnings"}:
            allowed.add(copy("verify", draft.language))
        if not set(getattr(draft, field)) <= allowed:
            return []
    allowed_headings = {"", *(section.heading for section in baseline.grounded_facts)}
    if (draft.reviewed_notes or any(section.heading not in allowed_headings or section.warnings
                                   for section in sections)):
        return []
    semantic = report.get("semantic_review") or {}
    semantic_passed = report.get("scope") == "semantic_model_review" and (
        semantic.get("passed") is True
        and isinstance(semantic.get("reviewed_claim_count"), int)
        and semantic["reviewed_claim_count"] >= len({section.body for section in sections})
    )
    matched: set[tuple[str, str]] = set()
    legacy_claims = {
        f"Selected source supports the general scenario context for {response.scenario.value}.",
        "Hybrid RAG selected this trusted source for grounded scenario context.",
    }
    for citation in response.citations:
        quote = citation.supporting_quote
        if not quote or quote not in (by_id[citation.source_id].content or ""):
            return []
        supported = [section for section in sections if citation.source_id in section.source_ids
                     and ((" ".join(section.body.split()) == " ".join(quote.split()) and (
                         citation.claim == quote or citation.claim in legacy_claims
                     )) or (section.body == citation.claim and semantic_passed))]
        if not supported:
            return []
        matched.update((section.body, citation.source_id) for section in supported)
    if any((section.body, sid) not in matched
           for section in sections for sid in section.source_ids):
        return []
    return ids


def detect_source_review_constraint_domain(
    user_text: str,
    scenario: str | None = None,
) -> str | None:
    if scenario == "kazakhstan_entry" or is_kazakhstan_entry_request(user_text):
        return KAZAKHSTAN_ENTRY_DOMAIN
    normalized = _normalize(user_text)
    if _contains_any(normalized, VISA_EXTENSION_KEYWORDS):
        return VISA_EXTENSION_DOMAIN
    if _contains_any(normalized, RESIDENCE_REGISTRATION_KEYWORDS):
        return RESIDENCE_REGISTRATION_DOMAIN
    return None


def classify_source_review_chat_constraint(
    user_text: str,
    *,
    scenario: str | None = None,
    project_root: Path | str = ".",
    report: SourceReviewAnswerConstraintsReport | None = None,
    service: SourceReviewAnswerConstraintsService | None = None,
) -> SourceReviewAnswerConstraint | None:
    domain = detect_source_review_constraint_domain(user_text, scenario=scenario)
    if domain is None:
        return None

    constraints_report = report
    if constraints_report is None:
        constraints_report = (
            service or SourceReviewAnswerConstraintsService(project_root)
        ).build_report()

    for constraint in constraints_report.constraints:
        if constraint.domain == domain and constraint.allowed_mode != "direct_answer_allowed":
            return constraint
    return None


def source_review_constraint_to_chat_metadata(
    constraint: SourceReviewAnswerConstraint,
) -> dict[str, Any]:
    return {
        "domain": constraint.domain,
        "allowed_mode": constraint.allowed_mode,
        "prohibited_claim_types": list(constraint.prohibited_claim_types),
        "required_warning": constraint.required_warning,
        "safe_response_guidance": list(constraint.safe_response_guidance),
        "citizen_visible_source_review_disclosure_allowed": False,
        "unpublished_candidates_must_not_be_cited": True,
    }


def source_review_warning_for_chat(
    constraint: SourceReviewAnswerConstraint,
    language: str = "en",
) -> str:
    localized = COPY.get(language, {}).get(constraint.domain)
    if localized:
        return localized[0]
    if constraint.domain == VISA_EXTENSION_DOMAIN:
        return (
            "I cannot verify the current official visa-extension procedure from "
            "approved published sources in this system. Please confirm with the local "
            "Exit-Entry Administration and your university international office before "
            "acting."
        )
    if constraint.domain == RESIDENCE_REGISTRATION_DOMAIN:
        return (
            "I cannot verify the current official residence-registration procedure from "
            "approved published sources in this system. Please confirm with the local "
            "public security authority, your accommodation provider, or your university "
            "before acting."
        )
    return constraint.required_warning


def safe_chat_steps_for_constraint(
    constraint: SourceReviewAnswerConstraint,
    language: str = "en",
) -> list[str]:
    localized = COPY.get(language, {}).get(constraint.domain)
    if localized:
        return list(localized[1])
    if constraint.domain == VISA_EXTENSION_DOMAIN:
        return [
            "Gather your passport, current visa or residence permit, accommodation or "
            "residence documents, and any university or host documents you already have.",
            "Contact the local Exit-Entry Administration before making a deadline-sensitive "
            "decision.",
            "If you are a student, ask your university international office to confirm the "
            "current process.",
            "Avoid overstaying or relying on community advice for legal-status decisions.",
        ]
    if constraint.domain == RESIDENCE_REGISTRATION_DOMAIN:
        return [
            "Ask your hotel, dormitory, landlord, university, or accommodation provider "
            "what local registration support they provide.",
            "Confirm the current local process with public security or the police station "
            "responsible for your accommodation area.",
            "Keep any registration receipt or confirmation record you receive.",
            "Do not rely on community advice for exact deadline, penalty, or city-specific "
            "procedure claims.",
        ]
    return list(constraint.safe_response_guidance)


def apply_source_review_constraint_to_answer(
    answer: str,
    constraint: SourceReviewAnswerConstraint | None,
) -> str:
    if constraint is None:
        return answer

    warning = source_review_warning_for_chat(constraint)
    steps = safe_chat_steps_for_constraint(constraint)
    lines = [
        warning,
        "",
        "Safe general steps:",
        *(f"- {step}" for step in steps),
        "",
        "Unpublished source candidates must not be cited as citizen-answer evidence.",
        "",
        answer,
    ]
    return "\n".join(lines)


def answer_contains_unpublished_candidate_reference(answer: str) -> bool:
    normalized = _normalize(answer)
    return _contains_any(normalized, UNPUBLISHED_CANDIDATE_REFERENCE_MARKERS)


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.casefold() in text for keyword in keywords)
