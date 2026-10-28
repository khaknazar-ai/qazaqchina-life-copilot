"""Copy verified saved actions into the same owned case; no invented action generation."""

import hashlib

from backend.app.embeddings.safety import eligible_cloud_source
from backend.app.source_registry.registry import SourceRegistry
from backend.app.workspace.models import Task, WorkspaceCase


def append_answer_tasks(case: WorkspaceCase, registry: SourceRegistry) -> bool:
    """The caller already resolved this case's owner and holds its mutation lock."""
    changed = False
    for message in case.messages:
        response = message.response
        if (message.kind != "assistant" or response is None or response.scenario != case.scenario
                or message.trace_id != response.trace_id or response.case_id != case.case_id):
            continue
        report = response.answer_verification_report or {}
        if (not report.get("passed") or not report.get("semantic_review", {}).get("passed")
                or response.metadata.get("cloud_answer_mode") != "semantic_grounded"
                or response.metadata.get("source_publication_gate", {}).get("status") != "passed"
                or response.has_source_review_constraints):
            continue
        draft = response.grounded_answer or {}
        notes = {note["source_id"]: note for note in draft.get("source_notes", [])}
        for section in draft.get("recommended_steps", []):
            if not isinstance(section, dict):
                continue
            body = section.get("body", "")
            source_ids = list(dict.fromkeys(section.get("source_ids", [])))
            if not body or not source_ids:
                continue
            matched = [citation for citation in response.citations if citation.claim == body]
            if set(source_ids) != {citation.source_id for citation in matched}:
                continue
            valid = True
            for sid in source_ids:
                source = registry.get_source_by_id(sid)
                digest = notes.get(sid, {}).get("content_hash")
                if (sid not in message.source_ids or source is None or not digest
                        or source.scenario not in {None, case.scenario}
                        or source.content_hash != digest
                        or hashlib.sha256((source.content or "").encode()).hexdigest() != digest
                        or not eligible_cloud_source(
                            source, scenario=case.scenario.value,
                            risk_level=response.risk_level.value,
                            city=case.context.city, enforce_city_scope=True,
                        ) or any(not citation.supporting_quote
                                 or citation.supporting_quote not in (source.content or "")
                                 for citation in matched if citation.source_id == sid)):
                    valid = False
                    break
            if not valid:
                continue
            key = "answer-action:" + response.trace_id + ":" + hashlib.sha256(
                body.encode(),
            ).hexdigest()
            if any(task.template_key == key for task in case.tasks):
                continue
            if len(case.tasks) >= 200:
                # The enclosing generic plan append uses the same case item limit.
                from fastapi import HTTPException

                raise HTTPException(409, "workspace_limit_reached")
            title = body if len(body) <= 200 else {
                "ru": "Действие из сохранённого ответа", "kk": "Сақталған жауаптағы әрекет",
                "zh": "已保存回答中的行动", "en": "Action from the saved answer",
            }.get(case.context.preferred_language.value, "Action from the saved answer")
            case.tasks.append(Task(
                title=title, description=body, priority=2, group="optional", scenario=case.scenario,
                risk_level=response.risk_level.value, source_ids=source_ids,
                origin_trace_id=response.trace_id, template_key=key,
                due_at=None, required_documents=[], estimated_time=None,
            ))
            changed = True
    return changed
