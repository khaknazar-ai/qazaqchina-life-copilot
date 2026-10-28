import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.app.admin.models import AdminDecision, AdminReviewType
from backend.app.admin.service import AdminReviewService
from backend.app.admin_auth.dependencies import (
    get_admin_auth_service,
    get_bearer_token_from_authorization_header,
    require_admin_permission,
)
from backend.app.admin_auth.models import AdminAuthDecision, AdminAuthReadinessReport
from backend.app.admin_auth.permissions import (
    PERMISSION_ADMIN_READ,
    PERMISSION_SOURCE_CANDIDATES_CREATE,
    PERMISSION_SOURCE_CANDIDATES_READ,
    PERMISSION_SOURCE_CANDIDATES_REVIEW,
    PERMISSION_SOURCE_INGESTION_DRY_RUN,
    PERMISSION_SOURCE_PUBLISH_PREVIEW,
    PERMISSION_SOURCE_REVIEW_OPERATIONS_READ,
    PERMISSION_SOURCE_VERSIONS_CREATE,
    PERMISSION_SOURCE_VERSIONS_READ,
)
from backend.app.admin_auth.readiness import build_admin_auth_readiness_report
from backend.app.config import get_settings
from backend.app.durable_storage.models import SourceReviewAuditRecord
from backend.app.durable_storage.repositories import SourceReviewAuditRepository
from backend.app.persistence.errors import RecordNotFoundError
from backend.app.persistence.factory import build_community_post_repository
from backend.app.persistence.runtime_sources import build_runtime_source_registry
from backend.app.schemas.admin import (
    AdminURLPreviewRequest,
    AdminURLPreviewResponse,
    CommunityPostAdminReviewRequest,
    CommunityPostAdminReviewResponse,
    RegistryReadyPreviewResponse,
    RoleVerificationAdminReviewRequest,
    RoleVerificationAdminReviewResponse,
    SourceCandidateCreateRequest,
    SourceCandidateListResponse,
    SourceCandidateReviewRequest,
    SourceCandidateReviewResponse,
    SourceGovernanceAdminReviewRequest,
    SourceGovernanceAdminReviewResponse,
    SourceIngestionDryRunRequest,
    SourceIngestionDryRunResponse,
    SourcePublishingPreviewRequest,
    SourceVersionCreateRequest,
    SourceVersionListResponse,
)
from backend.app.schemas.admin_source_review_operations import (
    ADMIN_SOURCE_REVIEW_OPERATIONS_WARNING,
    AdminSourceReviewOperationsResponse,
)
from backend.app.schemas.community import CommunityPostListResponse
from backend.app.source_candidates.models import SourceCandidate
from backend.app.source_conflicts import ConflictIntegrityError, ConflictNotFoundError
from backend.app.source_ingestion.validation import normalize_source_id
from backend.app.source_publishing.models import SourcePublishManifest, SourcePublishRequest
from backend.app.source_publishing.service import SourcePublishingService
from backend.app.source_review_operations.service import (
    SourceReviewOperationsDashboardService,
)
from backend.app.source_versioning.models import SourcePublishPreview, SourceVersionRecord

router = APIRouter(prefix="/api/admin", tags=["admin"])
_ADMIN_REVIEW_SERVICE = AdminReviewService()
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SOURCE_REVIEW_INTAKE_PATH = (
    _PROJECT_ROOT / "configs" / "source_review" / "official_source_candidate_intake.local.json"
)
ReviewAccess = Annotated[
    AdminAuthDecision, Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_REVIEW))
]
VersionCreateAccess = Annotated[
    AdminAuthDecision, Depends(require_admin_permission(PERMISSION_SOURCE_VERSIONS_CREATE))
]
PublishAccess = Annotated[
    AdminAuthDecision, Depends(require_admin_permission(PERMISSION_SOURCE_PUBLISH_PREVIEW))
]
IngestionAccess = Annotated[
    AdminAuthDecision, Depends(require_admin_permission(PERMISSION_SOURCE_INGESTION_DRY_RUN))
]


def _actor_id(access: AdminAuthDecision) -> str:
    if not access.authenticated or access.actor is None or not access.actor.actor_id.strip():
        raise HTTPException(403, "An administrator principal is required.")
    return access.actor.actor_id


def _bound_decision(decision: AdminDecision, access: AdminAuthDecision) -> AdminDecision:
    return decision.model_copy(update={"admin_id": _actor_id(access)})


@router.get("/auth/readiness", response_model=AdminAuthReadinessReport)
def admin_auth_readiness(request: Request) -> AdminAuthReadinessReport:
    service = get_admin_auth_service(request)
    return build_admin_auth_readiness_report(config=service.config)


@router.get("/auth/check", response_model=AdminAuthDecision)
def check_admin_auth(
    request: Request,
    permission: str = PERMISSION_ADMIN_READ,
    authorization: str | None = Header(default=None),
) -> AdminAuthDecision:
    service = get_admin_auth_service(request)
    token = get_bearer_token_from_authorization_header(authorization)
    decision = service.require_permission(token, permission)
    if not decision.authenticated:
        status_code = 403
        if decision.reason in {
            "missing_bearer_token",
            "invalid_bearer_token",
            "inactive_token",
        }:
            status_code = 401
        raise HTTPException(
            status_code=status_code,
            detail={
                "reason": decision.reason,
                "required_permission": decision.required_permission,
                "warnings": decision.warnings,
            },
        )
    return decision


@router.get(
    "/source-review/operations",
    response_model=AdminSourceReviewOperationsResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_REVIEW_OPERATIONS_READ))],
)
def source_review_operations_dashboard(
    include_local_intake: bool = False,
) -> AdminSourceReviewOperationsResponse:
    intake_path = _DEFAULT_SOURCE_REVIEW_INTAKE_PATH if include_local_intake else None
    report = SourceReviewOperationsDashboardService(
        _PROJECT_ROOT,
        intake_path=intake_path,
    ).build_report()
    return AdminSourceReviewOperationsResponse(
        **report.model_dump(),
        warning=ADMIN_SOURCE_REVIEW_OPERATIONS_WARNING,
    )


@router.post(
    "/community/review",
    response_model=CommunityPostAdminReviewResponse,
)
def review_community_post(
    http_request: Request,
    request: CommunityPostAdminReviewRequest,
    access: ReviewAccess,
) -> CommunityPostAdminReviewResponse:
    repository = _community_repository(http_request)
    post = request.post
    if repository is not None:
        try:
            post = repository.get_post(request.post.post_id)
        except RecordNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Community post not found.") from exc
    try:
        result = _get_admin_service(http_request).review_community_post(
            post=post,
            decision=_bound_decision(request.decision, access),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if repository is not None:
        repository.save_post(result.post)
    return CommunityPostAdminReviewResponse(result=result)


@router.post(
    "/verification/review",
    response_model=RoleVerificationAdminReviewResponse,
)
def review_role_verification(
    http_request: Request,
    request: RoleVerificationAdminReviewRequest,
    access: ReviewAccess,
) -> RoleVerificationAdminReviewResponse:
    repository = _community_repository(http_request)
    matching_posts = []
    profile = request.contributor
    if repository is not None:
        matching_posts = [
            post
            for post in repository.list_posts()
            if post.author.contributor_id == request.contributor.contributor_id
        ]
        if not matching_posts:
            raise HTTPException(status_code=404, detail="Contributor not found.")
        profile = matching_posts[0].author
    if request.decision.target_id != profile.contributor_id:
        raise HTTPException(
            status_code=400, detail="Verification target does not match contributor."
        )
    try:
        result = _get_admin_service(http_request).review_role_verification(
            profile=profile,
            decision=_bound_decision(request.decision, access),
            requested_role=request.requested_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if repository is not None:
        for post in matching_posts:
            repository.save_post(post.model_copy(update={"author": result.contributor}))
    return RoleVerificationAdminReviewResponse(result=result)


@router.post(
    "/source-governance/review",
    response_model=SourceGovernanceAdminReviewResponse,
)
def review_source_governance(
    http_request: Request,
    request: SourceGovernanceAdminReviewRequest,
    access: ReviewAccess,
) -> SourceGovernanceAdminReviewResponse:
    _require_governance_target(http_request, request.decision)
    try:
        result = _get_admin_service(http_request).review_source_governance(
            decision=_bound_decision(request.decision, access),
            recommended_actions=request.recommended_actions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SourceGovernanceAdminReviewResponse(result=result)


@router.get(
    "/source-candidates",
    response_model=SourceCandidateListResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_READ))],
)
def list_source_candidates(
    http_request: Request, status: str | None = None
) -> SourceCandidateListResponse:
    candidates = _get_admin_service(http_request).list_source_candidates(status=status)
    return SourceCandidateListResponse(
        candidates=candidates,
        total=len(candidates),
        warnings=["admin_auth_not_implemented_demo_only"],
    )


@router.post(
    "/source-candidates",
    response_model=SourceCandidate,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_CREATE))],
)
def create_source_candidate(
    http_request: Request,
    request: SourceCandidateCreateRequest,
) -> SourceCandidate:
    return _get_admin_service(http_request).add_source_candidate(
        title=request.title,
        url=request.url,
        snippet=request.snippet,
        source_type_guess=request.source_type_guess,
        trust_guess=request.trust_guess,
        language=request.language,
        country=request.country,
        city=request.city,
        scenario=request.scenario,
        risk_level=request.risk_level,
        official_domain_hint=request.official_domain_hint,
        warnings=request.warnings,
    )


@router.post(
    "/source-url/preview",
    response_model=AdminURLPreviewResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_CREATE))],
)
def preview_source_url(
    http_request: Request, request: AdminURLPreviewRequest
) -> AdminURLPreviewResponse:
    result = _get_admin_service(http_request).preview_source_url(
        url=request.url,
        scenario=request.scenario,
        risk_level=request.risk_level,
        language=request.language,
        city=request.city,
        allow_network=request.allow_network,
        confirm_network=request.confirm_network,
    )
    return AdminURLPreviewResponse(**result)


@router.get(
    "/source-candidates/registry-ready/list",
    response_model=RegistryReadyPreviewResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_PUBLISH_PREVIEW))],
)
def preview_registry_ready_sources(
    http_request: Request,
) -> RegistryReadyPreviewResponse:
    sources = _get_admin_service(http_request).registry_ready_sources()
    return RegistryReadyPreviewResponse(
        sources=sources,
        total=len(sources),
        warnings=[
            "Registry-ready preview only; trusted source registry files were not modified.",
            "admin_auth_not_implemented_demo_only",
        ],
    )


@router.get(
    "/source-candidates/{candidate_id}",
    response_model=SourceCandidate,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_READ))],
)
def get_source_candidate(http_request: Request, candidate_id: str) -> SourceCandidate:
    try:
        return _get_admin_service(http_request).get_source_candidate(candidate_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/source-candidates/{candidate_id}/review",
    response_model=SourceCandidateReviewResponse,
)
def review_source_candidate(
    http_request: Request,
    candidate_id: str,
    request: SourceCandidateReviewRequest,
    access: ReviewAccess,
) -> SourceCandidateReviewResponse:
    try:
        result = _get_admin_service(http_request).review_source_candidate(
            candidate_id=candidate_id,
            action=request.action,
            reviewer_id=_actor_id(access),
            reason=request.reason,
            assigned_source_type=request.assigned_source_type,
            assigned_trust_level=request.assigned_trust_level,
            allow_retrieval=request.allow_retrieval,
            freshness_note=request.freshness_note,
            notes=request.notes,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SourceCandidateReviewResponse(
        candidate=result.candidate,
        changed=result.changed,
        warnings=result.warnings,
    )


@router.post(
    "/source-candidates/{candidate_id}/create-version",
    response_model=SourceVersionRecord,
)
def create_source_version_from_candidate(
    http_request: Request,
    candidate_id: str,
    request: SourceVersionCreateRequest,
    access: VersionCreateAccess,
) -> SourceVersionRecord:
    try:
        return _get_admin_service(http_request).create_source_version_from_candidate(
            candidate_id=candidate_id,
            reviewer_id=_actor_id(access),
            reason=request.reason,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/source-versions",
    response_model=SourceVersionListResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_VERSIONS_READ))],
)
def list_source_versions(
    http_request: Request, status: str | None = None
) -> SourceVersionListResponse:
    versions = _get_admin_service(http_request).list_source_versions(status=status)
    return SourceVersionListResponse(
        versions=versions,
        total=len(versions),
        warnings=[
            "Source versioning is local/demo only.",
            "Trusted source registry files were not modified.",
            "admin_auth_not_implemented_demo_only",
        ],
    )


@router.get(
    "/source-versions/publish-preview",
    response_model=SourcePublishPreview,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_PUBLISH_PREVIEW))],
)
def source_publish_preview(
    http_request: Request,
) -> SourcePublishPreview:
    preview = _get_admin_service(http_request).source_publish_preview()
    return preview.model_copy(
        update={
            "registry_modified": False,
            "warnings": [
                *preview.warnings,
                "API preview only; data/sources/*.jsonl was not modified.",
                "admin_auth_not_implemented_demo_only",
            ],
        }
    )


@router.post(
    "/source-ingestion/prepare-dry-run",
    response_model=SourceIngestionDryRunResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_SOURCE_INGESTION_DRY_RUN))],
)
def prepare_source_ingestion_dry_run(
    http_request: Request,
    request: SourceIngestionDryRunRequest,
) -> SourceIngestionDryRunResponse:
    manifest = _get_admin_service(http_request).prepare_source_ingestion_dry_run(
        target_registry_file=request.target_registry_file,
    )
    return SourceIngestionDryRunResponse(
        dry_run=manifest.dry_run,
        registry_modified=False,
        total_records=manifest.total_records,
        valid_records=manifest.valid_records,
        invalid_records=manifest.invalid_records,
        issues=manifest.issues,
        records=manifest.records,
        notes=[
            *manifest.notes,
            "API dry run only; data/sources/*.jsonl was not modified.",
            "admin_auth_not_implemented_demo_only",
        ],
        target_registry_file=manifest.target_registry_file,
    )


@router.post(
    "/source-publishing/preview",
    response_model=SourcePublishManifest,
)
def source_publishing_preview(
    http_request: Request,
    request: SourcePublishingPreviewRequest,
    access: PublishAccess,
) -> SourcePublishManifest:
    return _build_source_publishing_manifest(http_request, request, _actor_id(access))


@router.post(
    "/source-publishing/apply-dry-run",
    response_model=SourcePublishManifest,
)
def source_publishing_apply_dry_run(
    http_request: Request,
    request: SourcePublishingPreviewRequest,
    access: IngestionAccess,
) -> SourcePublishManifest:
    service = SourcePublishingService(
        _get_admin_service(http_request).source_versioning_service,
    )
    manifest = _build_source_publishing_manifest(http_request, request, _actor_id(access))
    return service.apply_publish_manifest(manifest, confirm_registry_write=False)


def reset_admin_source_candidate_demo_state_for_tests() -> None:
    _ADMIN_REVIEW_SERVICE.reset_source_candidates_for_tests()


def _build_source_publishing_manifest(
    http_request: Request,
    request: SourcePublishingPreviewRequest,
    actor_id: str,
) -> SourcePublishManifest:
    service = SourcePublishingService(
        _get_admin_service(http_request).source_versioning_service,
    )
    versions = _get_admin_service(http_request).list_source_versions()
    candidates = _get_admin_service(http_request).list_source_candidates()
    if request.requests:
        requests = request.requests
    elif request.include_approved_versions:
        requests = [
            SourcePublishRequest(
                source_id=version.source_id,
                version_id=version.version_id,
                reason="Publish preview for approved source version.",
            )
            for version in versions
            if version.status == "approved"
        ]
    else:
        requests = []
    requests = _bound_publish_requests(requests, versions, candidates, actor_id)
    manifest = service.build_publish_manifest(requests, versions=versions, candidates=candidates)
    store = getattr(http_request.app.state, "durable_store", None)
    if store is not None:
        audit = SourceReviewAuditRepository(store)
        for plan in manifest.plans:
            audit.add(
                SourceReviewAuditRecord(
                    source_id=plan.source_id,
                    version_id=plan.version_id,
                    reviewer_id=actor_id,
                    decision="publish_preview",
                    reason="Source publish manifest preview generated.",
                    metadata={
                        "request_id": plan.request_id,
                        "status": plan.status,
                        "registry_modified": plan.registry_modified,
                        "planned_action": plan.planned_action,
                    },
                )
            )
    return manifest


def _bound_publish_requests(
    requests: list[SourcePublishRequest],
    versions: list[SourceVersionRecord],
    candidates: list[SourceCandidate],
    actor_id: str,
) -> list[SourcePublishRequest]:
    version_map = {version.version_id: version for version in versions}
    candidate_map = {candidate.candidate_id: candidate for candidate in candidates}
    bound: list[SourcePublishRequest] = []
    for request in requests:
        version = version_map.get(request.version_id) if request.version_id else max(
            (value for value in versions if value.source_id == request.source_id),
            key=lambda value: value.created_at,
            default=None,
        )
        candidate = candidate_map.get(request.candidate_id) if request.candidate_id else None
        if (request.version_id and version is None) or (
            request.candidate_id and candidate is None
        ):
            raise HTTPException(404, "Publish target was not found.")
        if version is None and candidate is None:
            raise HTTPException(404, "Publish target was not found.")
        if version is not None and request.source_id != version.source_id:
            raise HTTPException(400, "Publish source does not match its version.")
        if candidate is not None:
            candidate_source_id = normalize_source_id(candidate.title, candidate.candidate_id)
            if request.source_id != candidate_source_id:
                raise HTTPException(400, "Publish source does not match its candidate.")
        bound.append(
            request.model_copy(
                update={
                    "requested_by": actor_id,
                    "version_id": version.version_id if version else None,
                }
            )
        )
    return bound


def _require_governance_target(request: Request, decision: AdminDecision) -> None:
    if decision.review_type == AdminReviewType.source_registry_record:
        settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
        try:
            registry = build_runtime_source_registry(
                settings, getattr(request.app.state, "source_corpus_service", None)
            )
        except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
            raise HTTPException(503, "Reviewed source storage is unavailable.") from None
        if registry.get_source_by_id(decision.target_id) is None:
            raise HTTPException(404, "Source review target was not found.")
    elif decision.review_type == AdminReviewType.source_conflict:
        service = getattr(request.app.state, "source_conflict_service", None)
        if service is None:
            raise HTTPException(409, "A persisted conflict target is required.")
        try:
            service.get(decision.target_id)
        except ConflictNotFoundError:
            raise HTTPException(404, "Conflict review target was not found.") from None
        except ConflictIntegrityError:
            raise HTTPException(503, "Conflict review history failed verification.") from None
    else:
        raise HTTPException(409, "This review type has no persisted target in the legacy API.")


def _get_admin_service(request: Request) -> AdminReviewService:
    return getattr(request.app.state, "admin_review_service", None) or _ADMIN_REVIEW_SERVICE


def _community_repository(request: Request):
    settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
    if settings.ENABLE_LOCAL_PERSISTENCE:
        return build_community_post_repository(settings.LOCAL_DATA_DIR)
    return None


@router.get(
    "/community/posts",
    response_model=CommunityPostListResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_ADMIN_READ))],
)
def list_community_moderation_queue(http_request: Request) -> CommunityPostListResponse:
    repository = _community_repository(http_request)
    return CommunityPostListResponse(posts=repository.list_posts() if repository else [])
