"""Authenticated annotation of fixed evaluation questions; never source publication."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.admin_auth.dependencies import get_admin_auth_service, require_admin_permission
from backend.app.admin_auth.models import AdminAuthDecision
from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CORPUS_READ,
    PERMISSION_SOURCE_CORPUS_REVIEW,
)
from backend.app.cloud_ai.client import PROJECT_ROOT
from backend.app.real_eval.review_models import EvaluationApproval, EvaluationRevocation
from backend.app.real_eval.review_runtime import build_evaluation_review_service
from backend.app.real_eval.review_service import EvaluationReviewService
from backend.app.source_corpus.intake import repository_path

router = APIRouter(tags=["evaluation-review"])
API = "/api/admin/evaluation-review"
_UI = PROJECT_ROOT / "frontend/admin-source-console"
ReadAccess = Annotated[
    AdminAuthDecision,
    Depends(
        require_admin_permission(PERMISSION_SOURCE_CORPUS_READ),
    ),
]
ReviewAccess = Annotated[
    AdminAuthDecision,
    Depends(
        require_admin_permission(PERMISSION_SOURCE_CORPUS_REVIEW),
    ),
]


def _service(request: Request) -> EvaluationReviewService:
    auth = get_admin_auth_service(request)
    if not auth.is_enabled() or not request.app.state.runtime_settings.ENABLE_LOCAL_PERSISTENCE:
        raise HTTPException(403, "Evaluation annotation requires authenticated persistent review")
    service = getattr(request.app.state, "evaluation_review_service", None)
    if service is None:
        service = _call(
            lambda: build_evaluation_review_service(
                request.app.state.runtime_settings,
                admin_auth_service=auth,
            )
        )
        if service is None:
            raise HTTPException(503, "Evaluation review is unavailable")
        request.app.state.evaluation_review_service = service
    return service


def _call(operation):
    try:
        return operation()
    except LookupError:
        raise HTTPException(404, "Evaluation case or review was not found") from None
    except PermissionError:
        raise HTTPException(403, "An active evaluation reviewer is required") from None
    except sqlite3.Error:
        raise HTTPException(503, "Evaluation review storage is unavailable") from None
    except (ValueError, OSError, TypeError, KeyError):
        raise HTTPException(
            409, "Case, evidence or review changed; reload and verify originals"
        ) from None


def _publication(request: Request, records: list[dict]) -> list[dict]:
    corpus = getattr(request.app.state, "source_corpus_service", None)
    published = (
        _call(lambda: {source.source_id: source.content_hash for source in corpus.active_sources()})
        if corpus
        else {}
    )
    for record in records:
        ids = {e["source_id"] for e in record["case"]["evidence"]}
        matches = {
            e["source_id"]
            for e in record["case"]["evidence"]
            if published.get(e["source_id"]) == e["text_sha256"]
        }
        record["published_evidence_count"] = len(matches)
        record["required_evidence_count"] = len(ids)
        record["source_publication_ready"] = bool(ids) and ids <= matches
    return records


@router.get(API + "/access")
def access(request: Request, decision: ReadAccess) -> dict:
    _service(request)
    return {
        "actor": decision.actor,
        "review_enabled": PERMISSION_SOURCE_CORPUS_REVIEW in decision.actor.permissions,
        "source_publication_is_separate": True,
        "human_qualification_verified": False,
    }


@router.get(API)
def cases(request: Request, _decision: ReadAccess) -> dict:
    records = _call(lambda: _service(request).list_records())
    return {"cases": _publication(request, records), "used_network": False}


@router.get(API + "/{case_id}")
def case(case_id: str, request: Request, _decision: ReadAccess) -> dict:
    record = _call(lambda: _service(request).case_record(case_id))
    return {"case": _publication(request, [record])[0]}


@router.get(API + "/{case_id}/history")
def history(case_id: str, request: Request, _decision: ReadAccess) -> dict:
    return {"events": _call(lambda: _service(request).history(case_id))}


@router.get(API + "/{case_id}/material/{source_id}")
def material(case_id: str, source_id: str, request: Request, _decision: ReadAccess) -> dict:
    packet = _call(lambda: _service(request).material(case_id, source_id))
    return {
        "source_id": packet.source_id,
        "title": packet.title,
        "publisher": packet.publisher,
        "url": packet.final_url or packet.requested_url,
        "text": packet.text,
        "text_sha256": packet.text_sha256,
        "raw_sha256": packet.raw_sha256,
        "extracted_sha256": packet.extracted_sha256,
        "captured_at": packet.captured_at,
        "scope": packet.jurisdiction_or_scope,
        "source_publication_is_separate": True,
    }


@router.get(API + "/{case_id}/material/{source_id}/original")
def original(case_id: str, source_id: str, request: Request, _decision: ReadAccess) -> FileResponse:
    service = _service(request)
    packet = _call(lambda: service.material(case_id, source_id))
    return FileResponse(
        repository_path(service.project_root, packet.raw_path),
        media_type="application/octet-stream",
        filename="captured-original.bin",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.post(API + "/{case_id}/approve")
def approve(
    case_id: str, body: EvaluationApproval, request: Request, decision: ReviewAccess
) -> dict:
    record = _call(lambda: _service(request).approve(case_id, body, decision.actor))
    return {"case": _publication(request, [record])[0]}


@router.post(API + "/{case_id}/revoke")
def revoke(
    case_id: str, body: EvaluationRevocation, request: Request, decision: ReviewAccess
) -> dict:
    record = _call(
        lambda: _service(request).revoke(
            case_id,
            body.expected_review_id,
            body.reason,
            decision.actor,
        )
    )
    return {"case": _publication(request, [record])[0]}


@router.get("/admin/evaluation")
def evaluation_console() -> FileResponse:
    return FileResponse(_UI / "evaluation.html", media_type="text/html")


@router.get("/admin/evaluation/evaluation.js")
def evaluation_script() -> FileResponse:
    return FileResponse(_UI / "evaluation.js", media_type="application/javascript")
