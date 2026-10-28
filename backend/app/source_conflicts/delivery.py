"""Apply reviewed interpretations at the final chat delivery boundary."""

import hashlib
import json

from backend.app.answer_quality.composer import (
    compose_grounded_answer,
    render_grounded_answer_markdown,
)
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.answer_quality.models import (
    GroundedAnswerDraft,
    GroundedAnswerSection,
    ReviewedAnswerNote,
)
from backend.app.domain.agent import AgentState
from backend.app.domain.enums import RiskLevel
from backend.app.domain.sources import Citation, RetrievedSource
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.source_conflicts.models import ResolutionEvaluation
from backend.app.source_conflicts.registry import full_registry_sources
from backend.app.source_registry.registry import SourceRegistry
from backend.app.verification.gate import verify_agent_answer

MAX_SCOPE_DISCOVERY_SOURCES = 512

COPY = {
    "en": {
        "blocked": (
            "The sources disagree or their reviewed interpretation needs checking. "
            "Confirm this point with an official service or a qualified reviewer before acting."
        ),
        "note": "Reviewed interpretation",
        "incomplete": "Some relevant materials could not be checked automatically. "
        "Ask a reviewer to compare the originals before relying on this point.",
    },
    "ru": {
        "blocked": (
            "Источники расходятся или согласованное пояснение требует повторной проверки. "
            "Перед действием уточните этот пункт в официальной службе или у специалиста."
        ),
        "note": "Пояснение после проверки",
        "incomplete": "Часть относящихся к вопросу материалов не удалось проверить автоматически. "
        "Перед действием попросите специалиста сопоставить оригиналы.",
    },
    "kk": {
        "blocked": (
            "Дереккөздерде қайшылық бар немесе келісілген түсіндірмені қайта тексеру қажет. "
            "Әрекет етпес бұрын ресми қызметке немесе маманға хабарласыңыз."
        ),
        "note": "Тексерілген түсіндірме",
        "incomplete": "Кейбір тиісті материалдарды автоматты түрде тексеру мүмкін болмады. "
        "Әрекет етпес бұрын маманнан түпнұсқаларды салыстыруды сұраңыз.",
    },
    "zh": {
        "blocked": (
            "资料存在冲突，或已审核的解释需要重新核实。采取行动前，请向官方机构或专业审核人员确认。"
        ),
        "note": "审核后的解释",
        "incomplete": "部分相关资料未能完成自动检查。采取行动前，请审核人员比较原始资料。",
    },
}


def response_source_ids(response: ChatResponse) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *(
                    note["source_id"]
                    for note in (response.grounded_answer or {}).get("source_notes", [])
                    if note.get("source_id")
                ),
                *(citation.source_id for citation in response.citations),
            ]
        )
    )


def filtered_registry(registry: SourceRegistry, excluded: list[str]) -> SourceRegistry:
    excluded_ids = set(excluded)
    return SourceRegistry(
        official_sources=[
            s for s in registry.official_sources() if s.source_id not in excluded_ids
        ],
        curated_guides=[s for s in registry.curated_guides() if s.source_id not in excluded_ids],
        community_posts=[
            p for p in registry.approved_community_posts() if p.post_id not in excluded_ids
        ],
    )


def detected_conflict_ids(response: ChatResponse, registry: SourceRegistry) -> list[str]:
    from backend.app.source_conflicts.detection import (
        detect_conflicts_report,
        source_rule_ids,
    )

    selected_ids = set(response_source_ids(response))
    sources = [
        source
        for source in full_registry_sources(registry, retrievable_only=True)
        if source.scenario is None
        or source.scenario == response.scenario
        or source.source_id in selected_ids
    ]
    if selected_ids and len(sources) <= MAX_SCOPE_DISCOVERY_SOURCES:
        selected_sources = [source for source in sources if source.source_id in selected_ids]
        selected_rule_ids = set().union(
            *(source_rule_ids(source) for source in selected_sources)
        )
        if selected_rule_ids:
            sources = [
                source
                for source in sources
                if source.source_id in selected_ids
                or bool(source_rule_ids(source).intersection(selected_rule_ids))
            ]
        else:
            # The detector compares normalized rule claims, not every document in
            # the same scenario. Keep selected evidence in the report when no
            # extractor recognizes a rule in it; unrelated records cannot make
            # that check incomplete.
            sources = selected_sources
    report = detect_conflicts_report(sources, priority_source_ids=selected_ids)
    response.metadata["source_conflict_detection"] = report.model_dump(
        mode="json", exclude={"suggestions"}
    )
    result = []
    if selected_ids and (
        set(report.warnings).intersection(
            {"source_limit_reached", "claim_limit_reached", "suggestion_limit_reached"}
        )
        or selected_ids.intersection(report.skipped_source_ids)
    ):
        result.append("DETECTION-INCOMPLETE")
    for finding in report.suggestions:
        if finding.scenario != response.scenario or not selected_ids.intersection(
            finding.source_ids
        ):
            continue
        identity = finding.conflict_key or json.dumps(
            {
                "rule": finding.rule_id or finding.topic,
                "scope": finding.scope,
                "source_ids": finding.source_ids,
                "quotes": finding.quotes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result.append("DETECTED-" + hashlib.sha256(identity.encode()).hexdigest()[:16])
    return result


def preferred_quotes(evaluation: ResolutionEvaluation) -> dict[str, list[str]]:
    quotes: dict[str, list[str]] = {}
    for item in evaluation.applied:
        for sid in item.preferred_source_ids:
            quote = item.quotes[sid]
            if quote not in quotes.setdefault(sid, []):
                quotes[sid].append(quote)
    return quotes


def recompose_selected(
    request: ChatRequest,
    response: ChatResponse,
    registry: SourceRegistry,
    excluded: list[str],
    preferred: list[str] | None = None,
    quotes: dict[str, list[str]] | None = None,
) -> None:
    sources = []
    for sid in dict.fromkeys([*(preferred or []), *response_source_ids(response)]):
        source = registry.get_source_by_id(sid)
        if sid in excluded or source is None:
            continue
        excerpts = (quotes or {}).get(sid, [])
        if excerpts:
            sources.extend(
                RetrievedSource(
                    source=source,
                    chunk_id=f"review-{sid}-{i}",
                    content=quote,
                )
                for i, quote in enumerate(excerpts)
            )
        else:
            sources.append(source)
    # Regenerate from the remaining originals; never remove just a citation while
    # retaining a claim that was based on the excluded source.
    draft = compose_grounded_answer(
        user_message=request.user_message,
        trusted_sources=sources,
        scenario=response.scenario.value,
        risk_level=response.risk_level.value,
        language=request.preferred_language.value,
    )
    preferred_ids = set(preferred or [])
    preserved = [
        section
        for section in draft.grounded_facts
        if not preferred_ids.intersection(section.source_ids)
    ]
    reviewed_facts = [
        GroundedAnswerSection(
            heading="",
            body=quote,
            source_ids=[sid],
        )
        for sid in dict.fromkeys(preferred or [])
        for quote in (quotes or {}).get(sid, [])
    ]
    draft.grounded_facts = reviewed_facts + preserved
    response.citations = [
        Citation(
            citation_id=f"REVIEW-{i}",
            source_id=sid,
            claim=section.body,
            supporting_quote=section.body,
        )
        for i, section in enumerate(draft.grounded_facts, start=1)
        for sid in section.source_ids
    ]
    state = AgentState(
        trace_id=response.trace_id,
        user_message=request.user_message,
        scenario=response.scenario,
        risk_level=response.risk_level,
        response_language=request.preferred_language,
        draft_answer=render_grounded_answer_markdown(draft),
        grounded_answer=draft.model_dump(mode="json"),
        citations=response.citations,
    )
    verify_agent_answer(state, evidence=sources)
    response.answer_verification_report = state.answer_verification_report
    response.answer_verification_report["scope"] = "quoted_originals_after_source_resolution"
    if not state.answer_verification_report["passed"]:
        response.citations = []
        response.escalation_required = True
        response.safety_flags = list(dict.fromkeys([*response.safety_flags, *state.safety_flags]))
        draft = GroundedAnswerDraft.model_validate(state.grounded_answer)
    _store_draft(response, draft)


def withhold_conflicting_claims(
    request: ChatRequest,
    response: ChatResponse,
    conflict_ids: list[str],
) -> None:
    language = request.preferred_language.value
    copy = COPY.get(language, COPY["en"])
    warning = copy["incomplete"] if conflict_ids == ["DETECTION-INCOMPLETE"] else copy["blocked"]
    draft = compose_grounded_answer(
        user_message=request.user_message,
        trusted_sources=[],
        scenario=response.scenario.value,
        risk_level=response.risk_level.value,
        language=language,
    )
    if response.risk_level in {RiskLevel.emergency, RiskLevel.unsafe, RiskLevel.prompt_injection}:
        # Preserve urgent instructions/refusals, withholding only disputed facts.
        previous = GroundedAnswerDraft.model_validate(response.grounded_answer or draft)
        draft.direct_answer = previous.direct_answer
        draft.recommended_steps = previous.recommended_steps
        draft.escalation = previous.escalation
    else:
        draft.direct_answer = warning
    draft.uncertainty = list(dict.fromkeys([warning, *draft.uncertainty]))
    draft.escalation = list(dict.fromkeys([warning, *draft.escalation]))
    response.citations = []
    response.escalation_required = True
    response.escalation_recommended = True
    response.requires_human_escalation = True
    response.safety_flags = list(dict.fromkeys([*response.safety_flags, "source_conflict"]))
    response.answer_verification_report = {
        "passed": False,
        "scope": "source_conflict_delivery_gate",
        "claims_withheld": True,
    }
    response.metadata["source_resolution"] = {
        "status": "review_required",
        "blocked_conflict_ids": conflict_ids,
        "applied": [],
    }
    _store_draft(response, draft)


def attach_reviewed_notes(response: ChatResponse, evaluation) -> None:
    draft = GroundedAnswerDraft.model_validate(response.grounded_answer)
    draft.reviewed_notes = [
        ReviewedAnswerNote(
            conflict_id=item.conflict_id,
            revision=item.revision,
            note=item.note,
            source_ids=list(item.snapshot_refs),
            snapshot_refs=item.snapshot_refs,
            valid_until=item.valid_until.isoformat(),
        )
        for item in evaluation.applied
    ]
    response.metadata["source_resolution"] = {
        "status": "applied",
        "blocked_conflict_ids": [],
        "applied": [
            {
                "conflict_id": item.conflict_id,
                "revision": item.revision,
                "snapshot_refs": item.snapshot_refs,
            }
            for item in evaluation.applied
        ],
    }
    _store_draft(response, draft)


def verify_reviewed_answer(
    request: ChatRequest,
    response: ChatResponse,
    registry: SourceRegistry,
    evaluation: ResolutionEvaluation,
) -> bool:
    evidence = []
    for sid in response_source_ids(response):
        source = registry.get_source_by_id(sid)
        if source is None:
            return False
        reviewed = [
            item.quotes[sid] for item in evaluation.applied if sid in item.preferred_source_ids
        ]
        if reviewed:
            evidence.extend(
                RetrievedSource(
                    source=source,
                    chunk_id=f"final-review-{sid}-{i}",
                    content=quote,
                )
                for i, quote in enumerate(dict.fromkeys(reviewed))
            )
        else:
            evidence.append(source)
    state = AgentState(
        trace_id=response.trace_id,
        user_message=request.user_message,
        scenario=response.scenario,
        risk_level=response.risk_level,
        response_language=request.preferred_language,
        draft_answer=response.answer,
        grounded_answer=response.grounded_answer,
    )
    verify_agent_answer(state, evidence=evidence)
    response.answer_verification_report = state.answer_verification_report
    response.answer_verification_report["scope"] = "citations_and_reviewed_note_checks"
    return bool(state.answer_verification_report["passed"])


def _store_draft(response: ChatResponse, draft: GroundedAnswerDraft) -> None:
    response.grounded_answer = draft.model_dump(mode="json")
    response.answer = render_grounded_answer_markdown(draft)
    response.answer_quality_report = build_answer_quality_report(draft).model_dump(mode="json")
