from hashlib import sha256

from backend.app.source_versioning.models import SourceVersionDiff, SourceVersionRecord

_COMPARE_FIELDS = [
    "title",
    "url",
    "source_type",
    "trust_level",
    "language",
    "country",
    "city",
    "content_preview",
    "content_hash",
    "freshness_status",
    "status",
    "parent_version_id",
    "reviewer_id",
    "review_reason",
]


def compute_content_hash(text: str | None) -> str | None:
    if text is None:
        return None
    return sha256(text.encode("utf-8")).hexdigest()


def compare_source_versions(
    previous: SourceVersionRecord | None,
    new: SourceVersionRecord,
) -> list[str]:
    if previous is None:
        return [
            field_name
            for field_name in ["source_id", *_COMPARE_FIELDS]
            if _has_value(getattr(new, field_name))
        ]

    changed_fields: list[str] = []
    if previous.source_id != new.source_id:
        changed_fields.append("source_id")
    for field_name in _COMPARE_FIELDS:
        if getattr(previous, field_name) != getattr(new, field_name):
            changed_fields.append(field_name)
    return changed_fields


def build_source_version_diff(
    previous: SourceVersionRecord | None,
    new: SourceVersionRecord,
) -> SourceVersionDiff:
    warnings: list[str] = []
    if previous is None:
        warnings.append("No previous source version; preview treats this as a new source.")
    elif previous.source_id != new.source_id:
        warnings.append("Compared source versions have different source_id values.")

    return SourceVersionDiff(
        source_id=new.source_id,
        previous_version_id=previous.version_id if previous else None,
        new_version_id=new.version_id,
        changed_fields=compare_source_versions(previous, new),
        content_hash_changed=(
            previous is not None and previous.content_hash != new.content_hash
        ),
        warnings=warnings,
    )


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    return True
