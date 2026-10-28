from pathlib import Path
from typing import Any

from backend.app.persistence.errors import RecordNotFoundError
from backend.app.persistence.jsonl_store import JsonlRecordStore
from backend.app.source_candidates.policies import candidate_can_be_retrievable
from backend.app.source_ingestion.validation import normalize_source_id
from backend.app.source_versioning.diff import (
    build_source_version_diff,
    compute_content_hash,
)
from backend.app.source_versioning.models import (
    SourcePublishPreview,
    SourceVersionRecord,
    utc_now,
)

SOURCE_VERSION_RECORD_TYPE = "source_version"


class SourceVersioningService:
    def __init__(self, store_path: Path | str | None = None) -> None:
        self.store_path = Path(store_path) if store_path is not None else None
        self.store = JsonlRecordStore(self.store_path) if self.store_path is not None else None
        self._versions: dict[str, SourceVersionRecord] = {}
        self._load_versions()

    def create_draft_from_candidate(
        self,
        candidate: Any,
        reviewer_id: str | None = None,
        review_reason: str | None = None,
    ) -> SourceVersionRecord:
        if not _candidate_is_retrievable(candidate):
            raise ValueError(
                "Only approved, reviewed, retrieval-allowed source candidates can create "
                "source version drafts."
            )

        candidate_id = str(_candidate_value(candidate, "candidate_id"))
        title = str(_candidate_value(candidate, "title"))
        source_id = normalize_source_id(title=title, candidate_id=candidate_id)
        previous = self._latest_version_for_source(source_id)
        content_preview = _optional_string(_candidate_value(candidate, "snippet", None))
        content_hash = compute_content_hash(content_preview)
        warnings = _unique(
            [
                *_list_value(_candidate_value(candidate, "warnings", [])),
                "source_versioning_local_demo_only",
                "Trusted source registry files were not modified.",
            ]
        )
        if previous is not None and previous.content_hash == content_hash:
            warnings.append("Content hash matches the previous source version.")

        record = SourceVersionRecord(
            source_id=source_id,
            version_id=self._next_version_id(source_id, content_hash),
            title=title,
            url=_optional_string(_candidate_value(candidate, "url", None)),
            source_type=_optional_string(
                _candidate_value(candidate, "assigned_source_type", None)
            ),
            trust_level=_optional_string(
                _candidate_value(candidate, "assigned_trust_level", None)
            ),
            language=_optional_string(_candidate_value(candidate, "language", None)),
            country=_optional_string(_candidate_value(candidate, "country", None)),
            city=_optional_string(_candidate_value(candidate, "city", None)),
            content_preview=content_preview,
            content_hash=content_hash,
            freshness_status=_optional_string(
                _candidate_value(candidate, "freshness_status", "unknown")
            ),
            status="draft",
            parent_version_id=previous.version_id if previous is not None else None,
            reviewer_id=reviewer_id
            or _optional_string(_candidate_value(candidate, "reviewed_by", None)),
            review_reason=review_reason,
            created_at=utc_now(),
            reviewed_at=_candidate_value(candidate, "reviewed_at", None),
            warnings=warnings,
        )
        self._save_version(record)
        return record

    def approve_version(
        self,
        version_id: str,
        reviewer_id: str,
        reason: str,
    ) -> SourceVersionRecord:
        if not reviewer_id.strip():
            raise ValueError("approve_version requires reviewer_id.")
        if not reason.strip():
            raise ValueError("approve_version requires reason.")
        version = self._require_version(version_id)
        updated = version.model_copy(
            update={
                "status": "approved",
                "reviewer_id": reviewer_id,
                "review_reason": reason,
                "reviewed_at": utc_now(),
                "warnings": _unique(
                    [
                        *version.warnings,
                        "Approved source version remains a publish preview candidate only.",
                    ]
                ),
            }
        )
        self._save_version(updated)
        return updated

    def list_versions(self, status: str | None = None) -> list[SourceVersionRecord]:
        versions = list(self._versions.values())
        if status is None:
            return versions
        return [version for version in versions if version.status == status]

    def get_version(self, version_id: str) -> SourceVersionRecord | None:
        return self._versions.get(version_id)

    def build_publish_preview(self) -> SourcePublishPreview:
        versions = self.list_versions()
        diffs = [
            build_source_version_diff(self._previous_version(version), version)
            for version in versions
        ]
        publishable_versions = [version for version in versions if _is_publishable(version)]
        return SourcePublishPreview(
            total_versions=len(versions),
            draft_versions=sum(version.status == "draft" for version in versions),
            approved_versions=sum(version.status == "approved" for version in versions),
            publishable_versions=len(publishable_versions),
            registry_modified=False,
            versions=versions,
            diffs=diffs,
            warnings=[
                "Publish preview only; trusted source registry files were not modified.",
                "registry_modified=false",
                "Future vector chunks must be tied to published source version metadata.",
            ],
        )

    def mark_published(
        self,
        version_id: str,
        reviewer_id: str | None = None,
    ) -> SourceVersionRecord:
        version = self._require_version(version_id)
        if version.status != "approved":
            raise ValueError("Only approved source versions can be marked published.")
        updated = version.model_copy(
            update={
                "status": "published",
                "published_at": utc_now(),
                "reviewer_id": reviewer_id or version.reviewer_id,
                "warnings": _unique(
                    [
                        *version.warnings,
                        "Published metadata only; data/sources/*.jsonl was not modified.",
                    ]
                ),
            }
        )
        self._save_version(updated)
        return updated

    def deprecate_version(self, version_id: str, reason: str) -> SourceVersionRecord:
        if not reason.strip():
            raise ValueError("deprecate_version requires reason.")
        version = self._require_version(version_id)
        updated = version.model_copy(
            update={
                "status": "deprecated",
                "freshness_status": "deprecated",
                "review_reason": reason,
                "reviewed_at": utc_now(),
                "warnings": _unique([*version.warnings, "Source version was deprecated."]),
            }
        )
        self._save_version(updated)
        return updated

    def supersede_version(
        self,
        old_version_id: str,
        new_version: SourceVersionRecord,
    ) -> tuple[SourceVersionRecord, SourceVersionRecord]:
        old_version = self._require_version(old_version_id)
        superseded = old_version.model_copy(
            update={
                "status": "superseded",
                "reviewed_at": utc_now(),
                "warnings": _unique([*old_version.warnings, "Source version was superseded."]),
            }
        )
        replacement = new_version.model_copy(
            update={
                "parent_version_id": old_version.version_id,
                "warnings": _unique(
                    [
                        *new_version.warnings,
                        "Supersede metadata only; trusted registry files were not modified.",
                    ]
                ),
            }
        )
        self._save_version(superseded)
        self._save_version(replacement)
        return superseded, replacement

    def _load_versions(self) -> None:
        if self.store is None:
            return
        for record in self.store.list_records(SOURCE_VERSION_RECORD_TYPE):
            version = SourceVersionRecord.model_validate(record.payload)
            self._versions[version.version_id] = version

    def _save_version(self, version: SourceVersionRecord) -> None:
        self._versions[version.version_id] = version
        if self.store is None:
            return
        self.store.append(
            record_type=SOURCE_VERSION_RECORD_TYPE,
            payload=version.model_dump(mode="json"),
            record_id=version.version_id,
        )

    def _require_version(self, version_id: str) -> SourceVersionRecord:
        version = self.get_version(version_id)
        if version is None:
            raise RecordNotFoundError(f"Source version '{version_id}' was not found.")
        return version

    def _next_version_id(self, source_id: str, content_hash: str | None) -> str:
        sequence = 1 + sum(
            version.source_id == source_id for version in self._versions.values()
        )
        hash_suffix = (content_hash or "no-content")[:12]
        return f"{source_id}-v{sequence:04d}-{hash_suffix}"

    def _latest_version_for_source(self, source_id: str) -> SourceVersionRecord | None:
        versions = [
            version for version in self._versions.values() if version.source_id == source_id
        ]
        if not versions:
            return None
        return max(versions, key=lambda version: version.created_at)

    def _previous_version(self, version: SourceVersionRecord) -> SourceVersionRecord | None:
        if version.parent_version_id:
            parent = self.get_version(version.parent_version_id)
            if parent is not None:
                return parent
        older_versions = [
            candidate
            for candidate in self._versions.values()
            if candidate.source_id == version.source_id
            and candidate.version_id != version.version_id
            and candidate.created_at <= version.created_at
        ]
        if not older_versions:
            return None
        return max(older_versions, key=lambda candidate: candidate.created_at)


def _candidate_is_retrievable(candidate: Any) -> bool:
    try:
        return candidate_can_be_retrievable(candidate)
    except AttributeError:
        status = _candidate_value(candidate, "status", None)
        requires_review = bool(_candidate_value(candidate, "requires_review", True))
        allow_retrieval = bool(_candidate_value(candidate, "allow_retrieval", False))
        return (
            status == "approved"
            and not requires_review
            and allow_retrieval
            and bool(_candidate_value(candidate, "assigned_source_type", None))
            and bool(_candidate_value(candidate, "assigned_trust_level", None))
        )


def _candidate_value(candidate: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field_name, default)
    return getattr(candidate, field_name, default)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _is_publishable(version: SourceVersionRecord) -> bool:
    return (
        version.status == "approved"
        and bool(version.source_id)
        and bool(version.version_id)
        and bool(version.title)
        and bool(version.url)
        and bool(version.source_type)
        and bool(version.trust_level)
        and bool(version.content_hash)
        and version.reviewed_at is not None
    )
