from collections.abc import Iterable
from typing import Any

from backend.app.durable_storage.models import SourceReviewAuditRecord
from backend.app.durable_storage.repositories import SourceReviewAuditRepository
from backend.app.durable_storage.sqlite_store import SQLiteDurableStore
from backend.app.source_publishing.models import (
    SourcePublishManifest,
    SourcePublishPlan,
    SourcePublishRequest,
)
from backend.app.source_publishing.validation import (
    is_publishable,
    validate_publish_request,
)
from backend.app.source_versioning.models import SourceVersionRecord
from backend.app.source_versioning.service import SourceVersioningService

DEFAULT_TARGET_REGISTRY = "data/sources/official_sources.jsonl"


class SourcePublishingService:
    def __init__(
        self,
        source_versioning_service: SourceVersioningService | None = None,
        durable_store: SQLiteDurableStore | None = None,
    ) -> None:
        self.source_versioning_service = (
            source_versioning_service or SourceVersioningService()
        )
        self.durable_store = durable_store

    def build_publish_plan(
        self,
        request: SourcePublishRequest,
        source_version: SourceVersionRecord | None = None,
        candidate: Any = None,
    ) -> SourcePublishPlan:
        active_version = source_version or self._version_for_request(request)
        target_registry = request.target_registry or DEFAULT_TARGET_REGISTRY
        normalized_request = request.model_copy(update={"target_registry": target_registry})
        issues = validate_publish_request(
            normalized_request,
            source_version=active_version,
            candidate=candidate,
        )
        blocking_issue = any(issue.severity in {"error", "blocker"} for issue in issues)
        planned_action = "blocked"
        status = "blocked"
        if not blocking_issue:
            planned_action = (
                "supersede"
                if active_version is not None and active_version.parent_version_id
                else "create"
            )
            status = "ready_for_publish"
        warnings = _warnings_from_issues(issues)
        if active_version is not None:
            warnings = _unique([*warnings, *active_version.warnings])
        return SourcePublishPlan(
            request_id=request.request_id,
            source_id=request.source_id,
            version_id=(
                active_version.version_id if active_version is not None else request.version_id
            ),
            target_registry=target_registry,
            status=status,
            registry_modified=False,
            planned_action=planned_action,
            changed_fields=_changed_fields(active_version, planned_action),
            issues=issues,
            warnings=warnings,
            rollback_available=bool(active_version and active_version.parent_version_id),
            supersedes_version_id=(
                active_version.parent_version_id if active_version is not None else None
            ),
        )

    def build_publish_manifest(
        self,
        requests: list[SourcePublishRequest],
        versions: Iterable[SourceVersionRecord] | None = None,
        candidates: Iterable[Any] | None = None,
    ) -> SourcePublishManifest:
        version_map = {version.version_id: version for version in versions or []}
        candidate_map = {
            _value(candidate, "candidate_id"): candidate for candidate in candidates or []
        }
        plans = [
            self.build_publish_plan(
                request,
                source_version=version_map.get(request.version_id),
                candidate=candidate_map.get(request.candidate_id),
            )
            for request in requests
        ]
        manifest = _manifest_from_plans(plans)
        self._record_preview_audit(manifest)
        return manifest

    def preview_from_approved_versions(
        self,
        versions: Iterable[SourceVersionRecord],
    ) -> SourcePublishManifest:
        requests = [
            SourcePublishRequest(
                source_id=version.source_id,
                version_id=version.version_id,
                target_registry=DEFAULT_TARGET_REGISTRY,
                reason="Publish preview for approved source version.",
            )
            for version in versions
            if version.status == "approved"
        ]
        return self.build_publish_manifest(requests, versions=versions)

    def apply_publish_manifest(
        self,
        manifest: SourcePublishManifest,
        confirm_registry_write: bool = False,
    ) -> SourcePublishManifest:
        notes = [
            *manifest.notes,
            "apply_publish_manifest is dry-run only in Phase 67.",
            "No trusted registry files were modified.",
        ]
        if confirm_registry_write:
            notes.append(
                "confirm_registry_write=true was supplied, but registry apply is not "
                "implemented in Phase 67."
            )
        else:
            notes.append("confirm_registry_write=false; registry apply was not attempted.")
        return manifest.model_copy(
            update={
                "registry_modified": False,
                "notes": _unique(notes),
            }
        )

    def _version_for_request(
        self,
        request: SourcePublishRequest,
    ) -> SourceVersionRecord | None:
        if request.version_id:
            return self.source_versioning_service.get_version(request.version_id)
        versions = [
            version
            for version in self.source_versioning_service.list_versions()
            if version.source_id == request.source_id
        ]
        if not versions:
            return None
        return max(versions, key=lambda version: version.created_at)

    def _record_preview_audit(self, manifest: SourcePublishManifest) -> None:
        if self.durable_store is None:
            return
        repository = SourceReviewAuditRepository(self.durable_store)
        for plan in manifest.plans:
            repository.add(
                SourceReviewAuditRecord(
                    source_id=plan.source_id,
                    version_id=plan.version_id,
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


def _manifest_from_plans(plans: list[SourcePublishPlan]) -> SourcePublishManifest:
    publishable_count = sum(
        is_publishable(plan.status, plan.issues) for plan in plans
    )
    blocked_count = len(plans) - publishable_count
    return SourcePublishManifest(
        total_requests=len(plans),
        publishable_count=publishable_count,
        blocked_count=blocked_count,
        registry_modified=False,
        plans=plans,
        used_network=False,
        used_external_provider=False,
        notes=[
            "Publish manifest preview only; trusted source registry files were not modified.",
            "registry_modified=false by default.",
            "Rollback and supersede metadata are represented as plan metadata only.",
        ],
    )


def _warnings_from_issues(issues) -> list[str]:
    return [issue.message for issue in issues if issue.severity in {"info", "warning"}]


def _changed_fields(
    version: SourceVersionRecord | None,
    planned_action: str,
) -> list[str]:
    if planned_action == "blocked":
        return []
    fields = ["source_id", "version_id", "title", "url", "source_type", "trust_level"]
    if version and version.content_hash:
        fields.append("content_hash")
    if planned_action == "supersede":
        fields.append("parent_version_id")
    return fields


def _value(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
