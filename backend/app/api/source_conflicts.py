from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.admin_auth.dependencies import (
    get_admin_auth_service,
    get_bearer_token_from_authorization_header,
)
from backend.app.admin_auth.models import AuthenticatedAdmin
from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CONFLICTS_APPROVE,
    PERMISSION_SOURCE_CONFLICTS_CREATE,
    PERMISSION_SOURCE_CONFLICTS_NOTE,
    PERMISSION_SOURCE_CONFLICTS_READ,
    PERMISSION_SOURCE_CONFLICTS_REVOKE,
)
from backend.app.api.dependencies import get_source_registry
from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts import (
    ConflictCase,
    ConflictIntegrityError,
    ConflictNotFoundError,
    ConflictPermissionError,
    ConflictResolutionService,
    ConflictRevisionError,
    ConflictValidationError,
    ResolutionProposal,
)
from backend.app.source_conflicts.detection import detect_conflicts_report
from backend.app.source_conflicts.registry import full_registry_sources
from backend.app.source_conflicts.semantic_review import SemanticConflictReviewer
from backend.app.source_registry.registry import SourceRegistry

router = APIRouter(prefix="/api/admin/source-conflicts", tags=["source-conflicts"])


class CreateConflictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=2, max_length=10)
    quotes: dict[str, str]
    topic: str = Field(min_length=3, max_length=240)
    scenario: UserScenario
    risk_level: RiskLevel
    city: str | None = Field(default=None, max_length=120)
    scope_partitioned: bool = False


class ProposeResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    proposal: ResolutionProposal


class DecideResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    action: Literal["approve", "reject", "revoke"]
    reason: str = Field(min_length=3, max_length=2000)


class RefreshSourcesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    quotes: dict[str, str]


def require_conflict_permission(permission: str) -> Callable:
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedAdmin:
        service = get_admin_auth_service(request)
        if not service.is_enabled():
            raise HTTPException(status_code=403, detail="Authenticated review is required.")
        token = get_bearer_token_from_authorization_header(authorization)
        decision = service.require_permission(token, permission)
        if not decision.authenticated or decision.actor is None:
            status = 401 if decision.reason != "permission_denied" else 403
            raise HTTPException(status_code=status, detail="Review access was not granted.")
        return decision.actor

    return dependency


ReadActor = Annotated[
    AuthenticatedAdmin, Depends(require_conflict_permission(PERMISSION_SOURCE_CONFLICTS_READ))
]
CreateActor = Annotated[
    AuthenticatedAdmin, Depends(require_conflict_permission(PERMISSION_SOURCE_CONFLICTS_CREATE))
]
NoteActor = Annotated[
    AuthenticatedAdmin, Depends(require_conflict_permission(PERMISSION_SOURCE_CONFLICTS_NOTE))
]
Registry = Annotated[SourceRegistry, Depends(get_source_registry)]


def _service(request: Request) -> ConflictResolutionService:
    service = getattr(request.app.state, "source_conflict_service", None)
    if not isinstance(service, ConflictResolutionService):
        raise HTTPException(status_code=503, detail="Source review is unavailable.")
    return service


def _invoke(operation: Callable):
    try:
        return operation()
    except ConflictNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conflict case was not found.") from exc
    except ConflictRevisionError as exc:
        raise HTTPException(
            status_code=409, detail="This case changed. Refresh it before submitting again."
        ) from exc
    except ConflictPermissionError as exc:
        raise HTTPException(status_code=403, detail="This review action is not allowed.") from exc
    except ConflictValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Review input or evidence is invalid. Check quotations, scope and expiry.",
        ) from exc
    except ConflictIntegrityError as exc:
        raise HTTPException(status_code=503, detail="Review history failed verification.") from exc


def _eligible_sources(registry: SourceRegistry) -> list[SourceReference]:
    return [
        source
        for source in full_registry_sources(registry, retrievable_only=True)
        if source.content
    ]


@router.get("/access", response_model=AuthenticatedAdmin)
def access(actor: ReadActor) -> AuthenticatedAdmin:
    return actor


@router.get("/sources")
def sources(request: Request, registry: Registry, _actor: ReadActor) -> dict:
    available = _eligible_sources(registry)
    return {
        "sources": available,
        "total": len(available),
        "used_network": False,
        "semantic_review_enabled": isinstance(
            getattr(request.app.state, "semantic_conflict_reviewer", None), SemanticConflictReviewer
        ),
    }


@router.post("/detect")
def detect(registry: Registry, _actor: CreateActor) -> dict:
    report = detect_conflicts_report(_eligible_sources(registry))
    return {**report.model_dump(mode="json"), "total": len(report.suggestions)}


@router.post("/semantic-detect")
def semantic_detect(request: Request, registry: Registry, _actor: CreateActor) -> dict:
    reviewer = getattr(request.app.state, "semantic_conflict_reviewer", None)
    if not isinstance(reviewer, SemanticConflictReviewer):
        raise HTTPException(status_code=503, detail="Semantic source comparison is disabled.")
    report = reviewer.detect(_eligible_sources(registry))
    return {**report.model_dump(mode="json"), "total": len(report.suggestions)}


@router.get("")
def list_conflicts(request: Request, _actor: ReadActor) -> dict:
    cases = _invoke(lambda: _service(request).list())
    return {"cases": cases, "total": len(cases)}


@router.post("", response_model=ConflictCase, status_code=201)
def create_conflict(
    request: Request, body: CreateConflictRequest, registry: Registry, actor: CreateActor
) -> ConflictCase:
    eligible = {source.source_id: source for source in _eligible_sources(registry)}
    if len(set(body.source_ids)) != len(body.source_ids) or any(
        source_id not in eligible for source_id in body.source_ids
    ):
        raise HTTPException(status_code=400, detail="Select distinct eligible registry sources.")
    return _invoke(
        lambda: _service(request).create_conflict(
            sources=[eligible[source_id] for source_id in body.source_ids],
            quotes=body.quotes,
            topic=body.topic,
            scenario=body.scenario,
            risk_level=body.risk_level,
            city=body.city,
            scope_partitioned=body.scope_partitioned,
            actor=actor,
        )
    )


@router.get("/{conflict_id}", response_model=ConflictCase)
def get_conflict(request: Request, conflict_id: str, _actor: ReadActor) -> ConflictCase:
    return _invoke(lambda: _service(request).get(conflict_id))


@router.get("/{conflict_id}/history")
def history(request: Request, conflict_id: str, _actor: ReadActor) -> dict:
    events = _invoke(lambda: _service(request).history(conflict_id))
    return {"events": events, "total": len(events)}


@router.post("/{conflict_id}/proposals", response_model=ConflictCase)
def propose(
    request: Request, conflict_id: str, body: ProposeResolutionRequest, actor: NoteActor
) -> ConflictCase:
    return _invoke(
        lambda: _service(request).propose(
            conflict_id,
            proposal=body.proposal,
            actor=actor,
            expected_revision=body.expected_revision,
        )
    )


@router.post("/{conflict_id}/sources", response_model=ConflictCase)
def refresh_sources(
    request: Request,
    conflict_id: str,
    body: RefreshSourcesRequest,
    registry: Registry,
    actor: CreateActor,
) -> ConflictCase:
    service = _service(request)
    case = _invoke(lambda: service.get(conflict_id))
    current = {source.source_id: source for source in _eligible_sources(registry)}
    source_ids = [snapshot.source.source_id for snapshot in case.sources]
    if any(source_id not in current for source_id in source_ids):
        raise HTTPException(status_code=400, detail="Current evidence is not eligible for review.")
    return _invoke(
        lambda: service.refresh_sources(
            conflict_id,
            sources=[current[source_id] for source_id in source_ids],
            quotes=body.quotes,
            actor=actor,
            expected_revision=body.expected_revision,
        )
    )


@router.post("/{conflict_id}/decisions", response_model=ConflictCase)
def decide(
    request: Request,
    conflict_id: str,
    body: DecideResolutionRequest,
    authorization: str | None = Header(default=None),
) -> ConflictCase:
    permission = (
        PERMISSION_SOURCE_CONFLICTS_REVOKE
        if body.action == "revoke"
        else PERMISSION_SOURCE_CONFLICTS_APPROVE
    )
    actor = require_conflict_permission(permission)(request, authorization)
    return _invoke(
        lambda: _service(request).decide(
            conflict_id,
            action=body.action,
            reason=body.reason,
            actor=actor,
            expected_revision=body.expected_revision,
        )
    )
