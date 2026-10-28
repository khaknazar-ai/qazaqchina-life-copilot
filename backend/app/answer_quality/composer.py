from typing import Any

from backend.app.answer_quality.localization import copy, localized_scenario
from backend.app.answer_quality.models import (
    AnswerSourceNote,
    GroundedAnswerDraft,
    GroundedAnswerSection,
)
from backend.app.answer_quality.policies import (
    build_source_note,
    default_escalation_messages,
    default_uncertainty_messages,
    is_high_risk_scenario,
    sanitize_answer_text,
    source_can_ground_official_claim,
    source_can_support_practical_context,
)

UNREVIEWED_CANDIDATE_WARNING = (
    "There are unreviewed source candidates, but they are not used as trusted evidence."
)


def compose_grounded_answer(
    user_message: str,
    trusted_sources: list,
    scenario: str | None = None,
    risk_level: str | None = None,
    language: str | None = None,
    checklist_items: list[str] | None = None,
    unreviewed_candidate_count: int = 0,
) -> GroundedAnswerDraft:
    sources = _unique_sources(trusted_sources)
    grounding_sources = [
        source for source in sources
        if source_can_ground_official_claim(source) and _source_snippet(source)
    ]
    practical_sources = [
        source
        for source in sources
        if source_can_support_practical_context(source)
        and not source_can_ground_official_claim(source)
    ]
    source_notes = [build_source_note(source, used_for="grounding") for source in grounding_sources]
    source_notes.extend(
        build_source_note(source, used_for="practical_context") for source in practical_sources
    )
    checklist = [sanitize_answer_text(item) for item in (checklist_items or []) if item.strip()]
    key = _answer_key(user_message, scenario, risk_level)
    direct_answer = copy(key, language)
    if not grounding_sources and key not in {"acute", "loss", "emergency", "unsafe"}:
        direct_answer = copy("no_grounding", language)
    if practical_sources:
        source_notes = [
            note.model_copy(update={"warning": copy("practical", language)})
            if note.used_for == "practical_context"
            else note
            for note in source_notes
        ]
    grounded_facts = _grounded_fact_sections(grounding_sources, language)
    recommended_steps = [
        GroundedAnswerSection(
            heading=copy("safe", language),
            body=copy({"acute": "acute_steps", "loss": "loss_steps"}.get(key, key), language),
            # Template advice is not claimed to be entailed by every retrieved source.
            source_ids=[],
        )
    ]
    if key in {"work", "medical"}:
        recommended_steps.append(
            GroundedAnswerSection(
                heading=copy("checklist", language), body=copy(f"{key}_steps", language)
            )
        )
    if language in {"ru", "kk", "zh"}:
        uncertainty = [copy("verify", language)]
        if not grounding_sources:
            uncertainty.insert(0, copy("no_sources", language))
        escalation = (
            [
                copy("disclaimer", language),
                copy(
                    key if key in {"acute", "emergency", "loss", "medical", "work"} else "verify",
                    language,
                ),
            ]
            if is_high_risk_scenario(scenario, risk_level)
            else []
        )
    else:
        uncertainty = default_uncertainty_messages(
            scenario,
            risk_level,
            trusted_source_count=len(source_notes),
        )
        escalation = default_escalation_messages(scenario, risk_level)
    if key == "acute":
        escalation = [copy("disclaimer", language), copy("acute", language)]
    warnings: list[str] = []
    if unreviewed_candidate_count > 0:
        warnings.append(copy("unreviewed", language))

    if practical_sources and is_high_risk_scenario(scenario, risk_level):
        warnings.append(copy("practical", language))

    return GroundedAnswerDraft(
        scenario=scenario,
        risk_level=risk_level,
        language=language,
        direct_answer=direct_answer,
        grounded_facts=grounded_facts,
        recommended_steps=recommended_steps,
        checklist_items=checklist[:8],
        escalation=escalation,
        uncertainty=uncertainty,
        source_notes=source_notes,
        unreviewed_candidate_count=unreviewed_candidate_count,
        warnings=list(dict.fromkeys(warnings)),
    )


def render_grounded_answer_markdown(draft: GroundedAnswerDraft) -> str:
    language = draft.language

    def label(key: str) -> str:
        return copy(key, language)

    lines = [f"# {label('title')}", ""]
    metadata = []
    if draft.scenario:
        metadata.append(f"{label('scenario')}: {localized_scenario(draft.scenario, language)}")
    if draft.risk_level:
        metadata.append(f"{label('risk')}: {localized_scenario(draft.risk_level, language)}")
    if draft.language:
        metadata.append(f"{label('language')}: {draft.language}")
    lines.extend(["; ".join(metadata), "", f"## {label('short')}", draft.direct_answer, ""])
    if draft.grounded_facts or not any(step.source_ids for step in draft.recommended_steps):
        lines.append(f"## {label('facts')}")
        _append_sections(lines, draft.grounded_facts, label("no_facts"))
    lines.extend(["", f"## {label('steps')}"])
    _append_sections(lines, draft.recommended_steps, label("no_steps"))
    for heading, items, empty in (
        ("checklist", draft.checklist_items, "no_checklist"),
        ("human", draft.escalation, "routine_human"),
        ("uncertainty", draft.uncertainty, "verify"),
    ):
        lines.extend(["", f"## {label(heading)}"])
        lines.extend(f"- {item}" for item in items or [label(empty)])
    official = [note for note in draft.source_notes if note.used_for == "grounding"]
    practical = [note for note in draft.source_notes if note.used_for != "grounding"]
    lines.extend(["", f"## {label('sources')}", source_notes_to_markdown(official, language)])
    if practical:
        lines.extend(
            ["", f"## {label('community')}", source_notes_to_markdown(practical, language)]
        )
    if draft.reviewed_notes:
        heading = {
            "ru": "Пояснение после проверки", "kk": "Тексерілген түсіндірме",
            "zh": "审核后的解释", "en": "Reviewed interpretation",
        }.get(language, "Reviewed interpretation")
        lines.extend(["", f"## {heading}"])
        for note in draft.reviewed_notes:
            lines.append(f"- {note.note}")
    if draft.warnings:
        lines.extend(["", f"## {label('warnings')}"])
        lines.extend(f"- {warning}" for warning in draft.warnings)
    return "\n".join(lines).strip() + "\n"


def source_notes_to_markdown(
    source_notes: list[AnswerSourceNote],
    language: str | None = None,
) -> str:
    if not source_notes:
        return f"- {copy('no_sources', language)}"
    lines = []
    for note in source_notes:
        title = (
            f"[{note.title}]({note.url})"
            if note.url and note.url.startswith(("https://", "http://"))
            else note.title
        )
        line = f"- {note.source_id}: {title}."
        if note.warning:
            line = f"{line} {note.warning}"
        lines.append(line)
    return "\n".join(lines)


def _grounded_fact_sections(
    sources: list[Any],
    language: str | None = None,
) -> list[GroundedAnswerSection]:
    sections: list[GroundedAnswerSection] = []
    for source in sources[:4]:
        source_reference = _source_reference(source)
        source_id = str(getattr(source_reference, "source_id", "unknown"))
        title = str(getattr(source_reference, "title", copy("sources", language)))
        snippet = _source_snippet(source)
        if not snippet:
            continue
        sections.append(
            GroundedAnswerSection(
                heading=f"{copy('quote', language)} — {title}",
                body=sanitize_answer_text(snippet),
                source_ids=[source_id],
            )
        )
    return sections


def _answer_key(user_message: str, scenario: str | None, risk_level: str | None) -> str:
    from backend.app.agent.classification import is_acute_medical, is_document_loss, payment_intent

    normalized = f"{scenario or ''} {risk_level or ''}".casefold().replace("_", "-")
    if "prompt-injection" in normalized or "unsafe" in normalized:
        return "unsafe"
    if is_acute_medical(user_message):
        return "acute"
    if is_document_loss(user_message) or "lost-passport" in normalized:
        return "loss"
    if risk_level == "emergency" or scenario == "emergency":
        return "emergency"
    if "payment" in normalized or "scam" in normalized:
        intent = payment_intent(user_message)
        return "general_payment" if intent == "general" else intent
    for key in ("medical", "work", "study", "documents"):
        if key in normalized:
            return key
    return "generic"


def _append_sections(
    lines: list[str],
    sections: list[GroundedAnswerSection],
    empty_text: str,
) -> None:
    if not sections:
        lines.append(f"- {empty_text}")
        return
    for section in sections:
        source_suffix = f" [{', '.join(section.source_ids)}]" if section.source_ids else ""
        heading = f"**{section.heading}:** " if section.heading.strip() else ""
        lines.append(f"- {heading}{section.body}{source_suffix}")
        lines.extend(f"  - {warning}" for warning in section.warnings)


def _source_snippet(source: Any) -> str:
    source_reference = _source_reference(source)
    from backend.app.domain.sources import SourceReference
    from backend.app.source_governance.passages import complete_source_text

    if isinstance(source_reference, SourceReference) and source_reference.content:
        return sanitize_answer_text(complete_source_text(source_reference))
    for candidate in [
        getattr(source_reference, "content", None),
        getattr(source, "content", None),
        getattr(getattr(source, "chunk", None), "content", None),
        getattr(source_reference, "excerpt", None),
        getattr(source_reference, "snippet", None),
    ]:
        if candidate:
            complete = sanitize_answer_text(str(candidate))
            return complete if len(complete) <= 2400 else ""
    return ""


def _source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _source_id(source: Any) -> str:
    source_reference = _source_reference(source)
    return str(getattr(source_reference, "source_id", "unknown"))


def _unique_sources(sources: list[Any]) -> list[Any]:
    unique: list[Any] = []
    seen: set[str] = set()
    for source in sources:
        source_id = _source_id(source)
        if source_id in seen:
            continue
        unique.append(source)
        seen.add(source_id)
    return unique
