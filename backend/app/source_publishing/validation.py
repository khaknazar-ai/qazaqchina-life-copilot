from typing import Any

from backend.app.source_publishing.models import (
    SourcePublishRequest,
    SourcePublishValidationIssue,
)


def validate_publish_request(
    request: SourcePublishRequest,
    source_version: Any = None,
    candidate: Any = None,
) -> list[SourcePublishValidationIssue]:
    issues: list[SourcePublishValidationIssue] = []
    if source_version is None and candidate is None:
        issues.append(
            _issue(
                "publish-source-missing",
                "blocker",
                "A publish request must reference an existing reviewed source version or "
                "candidate.",
                "source_id",
            )
        )
    if request.apply and not request.confirm_registry_write:
        issues.append(
            _issue(
                "publish-apply-not-confirmed",
                "blocker",
                "apply=true requires confirm_registry_write=true; Phase 67 stays dry-run "
                "by default.",
                "confirm_registry_write",
            )
        )
    if not (request.target_registry or "").strip():
        issues.append(
            _issue(
                "publish-target-derived",
                "info",
                "No target registry was supplied; a safe default registry path will be used.",
                "target_registry",
            )
        )
    if source_version is not None:
        issues.extend(_validate_source_version(request, source_version))
    if candidate is not None:
        issues.extend(_validate_candidate(candidate))
    return issues


def is_publishable(status: str, issues: list[SourcePublishValidationIssue]) -> bool:
    return status in {"ready_for_publish", "published_preview"} and not any(
        issue.severity in {"error", "blocker"} for issue in issues
    )


def _validate_source_version(
    request: SourcePublishRequest,
    source_version: Any,
) -> list[SourcePublishValidationIssue]:
    issues: list[SourcePublishValidationIssue] = []
    status = _value(source_version, "status")
    freshness_status = _value(source_version, "freshness_status")
    if status not in {"approved", "published_preview", "ready_for_publish"}:
        issues.append(
            _issue(
                "publish-version-status-blocked",
                "blocker",
                f"Source version status is not publishable: {status or 'missing'}.",
                "status",
            )
        )
    if status in {"deprecated", "superseded"}:
        issues.append(
            _issue(
                "publish-version-deprecated",
                "blocker",
                "Deprecated or superseded source versions cannot be published.",
                "status",
            )
        )
    for field in ["source_id", "version_id", "title", "url", "source_type", "trust_level"]:
        if not _value(source_version, field):
            issues.append(
                _issue(
                    f"publish-version-missing-{field}",
                    "error",
                    f"Source version is missing required field: {field}.",
                    field,
                )
            )
    if not _value(source_version, "content_hash"):
        issues.append(
            _issue(
                "publish-version-missing-content-hash",
                "error",
                "Source version must have a content_hash before publishing.",
                "content_hash",
            )
        )
    if freshness_status in {None, "", "unknown", "stale"}:
        issues.append(
            _issue(
                "publish-version-freshness-warning",
                "warning",
                f"Source version freshness is {freshness_status or 'unknown'}.",
                "freshness_status",
            )
        )
    if _is_high_risk_official(source_version) and not (request.reason or "").strip():
        issues.append(
            _issue(
                "publish-reason-required",
                "blocker",
                "A reason is required for high-risk official source publishing changes.",
                "reason",
            )
        )
    return issues


def _validate_candidate(candidate: Any) -> list[SourcePublishValidationIssue]:
    status = _value(candidate, "status")
    if status != "approved":
        return [
            _issue(
                "publish-candidate-status-blocked",
                "blocker",
                f"Source candidate status is not publishable: {status or 'missing'}.",
                "status",
            )
        ]
    if bool(_value(candidate, "requires_review", True)):
        return [
            _issue(
                "publish-candidate-review-required",
                "blocker",
                "Source candidate still requires review and cannot be published.",
                "requires_review",
            )
        ]
    if not bool(_value(candidate, "allow_retrieval", False)):
        return [
            _issue(
                "publish-candidate-retrieval-disabled",
                "blocker",
                "Source candidate is not retrieval-allowed and cannot be published.",
                "allow_retrieval",
            )
        ]
    return []


def _is_high_risk_official(source_version: Any) -> bool:
    source_type = str(_value(source_version, "source_type", "")).casefold()
    trust_level = str(_value(source_version, "trust_level", "")).casefold()
    return "official" in source_type or "official" in trust_level


def _value(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def _issue(
    issue_id: str,
    severity: str,
    message: str,
    field: str | None = None,
) -> SourcePublishValidationIssue:
    return SourcePublishValidationIssue(
        issue_id=issue_id,
        severity=severity,
        message=message,
        field=field,
    )
