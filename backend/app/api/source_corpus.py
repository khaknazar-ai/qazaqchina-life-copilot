"""Authenticated source publication from server-prepared evidence packets."""

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.admin_auth.dependencies import get_admin_auth_service, require_admin_permission
from backend.app.admin_auth.models import AdminAuthDecision, AuthenticatedAdmin
from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CORPUS_PUBLISH,
    PERMISSION_SOURCE_CORPUS_READ,
    PERMISSION_SOURCE_CORPUS_REVIEW,
    PERMISSION_SOURCE_CORPUS_REVOKE,
    PERMISSION_SOURCE_CORPUS_STAGE,
)
from backend.app.cloud_ai.client import PROJECT_ROOT
from backend.app.source_corpus.intake import load_prepared_packets
from backend.app.source_corpus.models import CorpusPacket, PublicationReview
from backend.app.source_corpus.service import SourceCorpusService

router = APIRouter(prefix="/api/admin/source-corpus", tags=["source-corpus"])


class StageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(pattern=r"^[A-Z][A-Z0-9-]{1,60}$")


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RevokeRequest(RevisionRequest):
    reason: str = Field(min_length=1, max_length=1000)


def _service(request: Request) -> SourceCorpusService:
    if not get_admin_auth_service(request).is_enabled():
        raise HTTPException(403, "Source review requires an enabled authenticated account")
    service = getattr(request.app.state, "source_corpus_service", None)
    if service is None:
        raise HTTPException(503, "Source corpus is unavailable")
    return service


def _actor(request: Request, decision: AdminAuthDecision) -> AuthenticatedAdmin:
    settings = request.app.state.runtime_settings
    if not get_admin_auth_service(request).is_enabled() or not settings.ENABLE_LOCAL_PERSISTENCE:
        raise HTTPException(403, "Source publication requires authenticated, persistent review")
    if decision.actor is None or not decision.actor.token_id:
        raise HTTPException(403, "An authenticated review account is required")
    return decision.actor


def _packets(request: Request) -> list[CorpusPacket]:
    _service(request)
    directory = (
        PROJECT_ROOT
        / Path(request.app.state.runtime_settings.LOCAL_DATA_DIR)
        / "source_corpus"
        / "packets"
    ).resolve()
    if not directory.is_relative_to(PROJECT_ROOT):
        raise HTTPException(503, "Corpus packet storage is invalid")
    try:
        return load_prepared_packets(PROJECT_ROOT, directory)
    except (ValueError, OSError, KeyError, TypeError):
        raise HTTPException(503, "Prepared corpus packets failed validation") from None


def _call(operation):
    try:
        return operation()
    except LookupError:
        raise HTTPException(404, "Corpus revision was not found") from None
    except PermissionError:
        raise HTTPException(403, "Review permission is required") from None
    except sqlite3.Error:
        raise HTTPException(503, "Source review storage is unavailable") from None
    except (ValueError, OSError, TypeError, KeyError):
        raise HTTPException(
            409,
            "Evidence or review state changed; reload and verify the packet",
        ) from None


@router.get("/packets")
def packets(
    request: Request,
    _decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_READ),
        ),
    ],
) -> dict:
    return {
        "packets": _packets(request),
        "published_sources": _call(lambda: len(_service(request).active_sources())),
    }


@router.get("/access")
def access(
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_READ),
        ),
    ],
) -> dict:
    _service(request)
    return {
        "actor": decision.actor,
        "publication_enabled": get_admin_auth_service(request).is_enabled()
        and request.app.state.runtime_settings.ENABLE_LOCAL_PERSISTENCE,
    }


@router.get("")
def states(
    request: Request,
    _decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_READ),
        ),
    ],
) -> dict:
    return {"sources": _call(lambda: _service(request).list_states())}


@router.get("/{source_id}/history")
def history(
    source_id: str,
    request: Request,
    _decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_READ),
        ),
    ],
) -> dict:
    return {"events": _call(lambda: _service(request).history(source_id))}


@router.post("/stage")
def stage(
    body: StageRequest,
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_STAGE),
        ),
    ],
) -> dict:
    actor = _actor(request, decision)
    packet = next((p for p in _packets(request) if p.candidate_id == body.candidate_id), None)
    if packet is None:
        raise HTTPException(404, "Prepared candidate was not found")
    return {"revision": _call(lambda: _service(request).stage(packet, actor))}


@router.post("/{revision_id}/review")
def review(
    revision_id: str,
    body: PublicationReview,
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_REVIEW),
        ),
    ],
) -> dict:
    actor = _actor(request, decision)
    return {"source": _call(lambda: _service(request).review(revision_id, actor, body))}


@router.post("/{revision_id}/publish")
def publish(
    revision_id: str,
    body: RevisionRequest,
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_PUBLISH),
        ),
    ],
) -> dict:
    actor = _actor(request, decision)
    return {
        "source": _call(
            lambda: _service(request).publish(
                revision_id,
                actor,
                body.expected_revision_hash,
            )
        )
    }


@router.post("/{source_id}/revoke")
def revoke(
    source_id: str,
    body: RevokeRequest,
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_REVOKE),
        ),
    ],
) -> dict:
    actor = _actor(request, decision)
    return {
        "source": _call(
            lambda: _service(request).revoke(
                source_id,
                actor,
                body.expected_revision_hash,
                body.reason,
            )
        )
    }


@router.post("/{source_id}/reset-review")
def reset_review(
    source_id: str,
    body: RevokeRequest,
    request: Request,
    decision: Annotated[
        AdminAuthDecision,
        Depends(
            require_admin_permission(PERMISSION_SOURCE_CORPUS_STAGE),
        ),
    ],
) -> dict:
    actor = _actor(request, decision)
    return {
        "revision": _call(
            lambda: _service(request).reset_review(
                source_id,
                actor,
                body.expected_revision_hash,
                body.reason,
            )
        )
    }
