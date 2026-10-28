from typing import Any

from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.source_freshness.policies import (
    assess_source_freshness,
    freshness_warning_for_answer,
)
from backend.app.source_index.chunking import (
    make_chunk_id,
    split_text_into_chunks,
    stable_text_hash,
)
from backend.app.source_index.models import (
    SourceChunk,
    SourceIndexBuildRequest,
    SourceIndexBuildResult,
)
from backend.app.source_versioning.models import SourceVersionRecord

_TEXT_FIELDS = ("content", "text", "excerpt", "snippet", "content_preview")
_SOFT_FRESHNESS_STATUSES = {"unknown", "stale", "needs_refresh"}
_BLOCKED_VERSION_STATUSES = {"deprecated", "superseded"}


class SourceIndexService:
    def build_chunks_from_source(
        self,
        source: Any,
        request: SourceIndexBuildRequest | None = None,
    ) -> list[SourceChunk]:
        active_request = request or SourceIndexBuildRequest()
        text, text_warnings = _extract_text(source)
        if not text:
            return []

        source_id = str(_value(source, "source_id", "unknown"))
        freshness_status, freshness_warnings = _source_freshness(source)
        retrievable = _source_is_retrievable(source)
        deprecated = freshness_status == "deprecated"
        if deprecated and not active_request.include_deprecated:
            retrievable = False
        indexable = retrievable and not (deprecated and not active_request.include_deprecated)
        warnings = _unique(
            [
                *text_warnings,
                *freshness_warnings,
                *_freshness_index_warnings(freshness_status),
                *([] if retrievable else ["Source is not retrievable under source policy."]),
            ]
        )
        return self._chunks_for_text(
            text=text,
            source_id=source_id,
            version_id=None,
            request=active_request,
            source_type=_enum_value(_value(source, "source_type", None)),
            trust_level=_enum_value(_value(source, "trust_level", None)),
            language=_enum_value(_value(source, "language", None)),
            country=_string_or_none(_value(source, "country", None)),
            city=_string_or_none(_value(source, "city", None)),
            content_hash=_string_or_none(_value(source, "content_hash", None)),
            freshness_status=freshness_status,
            source_version_status=None,
            retrievable=retrievable,
            indexable=indexable,
            warnings=warnings,
        )

    def build_chunks_from_version(
        self,
        version: SourceVersionRecord,
        request: SourceIndexBuildRequest | None = None,
    ) -> list[SourceChunk]:
        active_request = request or SourceIndexBuildRequest()
        text, text_warnings = _extract_text(version)
        if not text:
            return []

        blocked_by_status = (
            version.status in _BLOCKED_VERSION_STATUSES
            and not active_request.include_deprecated
        )
        retrievable = not blocked_by_status
        indexable = not blocked_by_status
        freshness_status = version.freshness_status or "unknown"
        warnings = _unique(
            [
                *text_warnings,
                *_freshness_index_warnings(freshness_status),
                *(
                    [
                        "Source version is deprecated or superseded; chunk is not "
                        "indexable by default."
                    ]
                    if blocked_by_status
                    else []
                ),
            ]
        )
        return self._chunks_for_text(
            text=text,
            source_id=version.source_id,
            version_id=version.version_id,
            request=active_request,
            source_type=version.source_type,
            trust_level=version.trust_level,
            language=version.language,
            country=version.country,
            city=version.city,
            content_hash=version.content_hash,
            freshness_status=freshness_status,
            source_version_status=version.status,
            retrievable=retrievable,
            indexable=indexable,
            warnings=warnings,
        )

    def build_index_from_sources(
        self,
        sources: list[Any],
        request: SourceIndexBuildRequest | None = None,
    ) -> SourceIndexBuildResult:
        active_request = request or SourceIndexBuildRequest()
        chunks = [
            chunk
            for source in sources
            for chunk in self.build_chunks_from_source(source, active_request)
        ]
        return _build_result(total_sources=len(sources), chunks=chunks)

    def build_index_from_versions(
        self,
        versions: list[SourceVersionRecord],
        request: SourceIndexBuildRequest | None = None,
    ) -> SourceIndexBuildResult:
        active_request = request or SourceIndexBuildRequest()
        chunks = [
            chunk
            for version in versions
            for chunk in self.build_chunks_from_version(version, active_request)
        ]
        return _build_result(total_sources=len(versions), chunks=chunks)

    def _chunks_for_text(
        self,
        text: str,
        source_id: str,
        version_id: str | None,
        request: SourceIndexBuildRequest,
        source_type: str | None,
        trust_level: str | None,
        language: str | None,
        country: str | None,
        city: str | None,
        content_hash: str | None,
        freshness_status: str | None,
        source_version_status: str | None,
        retrievable: bool,
        indexable: bool,
        warnings: list[str],
    ) -> list[SourceChunk]:
        text_chunks = split_text_into_chunks(
            text,
            max_chunk_chars=request.max_chunk_chars,
            overlap_chars=request.overlap_chars,
        )
        chunks: list[SourceChunk] = []
        for chunk_index, chunk_text in enumerate(text_chunks):
            text_hash = stable_text_hash(chunk_text)
            chunks.append(
                SourceChunk(
                    chunk_id=make_chunk_id(
                        source_id=source_id,
                        version_id=version_id,
                        chunk_index=chunk_index,
                        text_hash=text_hash,
                    ),
                    source_id=source_id,
                    version_id=version_id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    text_hash=text_hash,
                    source_type=source_type,
                    trust_level=trust_level,
                    language=language,
                    country=country,
                    city=city,
                    content_hash=content_hash,
                    freshness_status=freshness_status,
                    source_version_status=source_version_status,
                    retrievable=retrievable,
                    indexable=indexable,
                    warnings=warnings,
                )
            )
        return chunks


def _extract_text(source: Any) -> tuple[str | None, list[str]]:
    for field_name in _TEXT_FIELDS:
        value = _value(source, field_name, None)
        if _string_or_none(value):
            return _string_or_none(value), []
    title = _string_or_none(_value(source, "title", None))
    if title:
        return title, ["No body content found; using title fallback only."]
    return None, ["No source text was available for chunking."]


def _source_freshness(source: Any) -> tuple[str | None, list[str]]:
    explicit_status = _string_or_none(_value(source, "freshness_status", None))
    if explicit_status:
        return explicit_status, []
    assessment = assess_source_freshness(source)
    warning = freshness_warning_for_answer(assessment)
    warnings = [warning] if warning else []
    return assessment.status, warnings


def _freshness_index_warnings(freshness_status: str | None) -> list[str]:
    if freshness_status in _SOFT_FRESHNESS_STATUSES:
        return [
            f"Source freshness is {freshness_status}; keep chunk index tied to review metadata."
        ]
    if freshness_status == "deprecated":
        return ["Source freshness is deprecated; chunk is not indexable by default."]
    return []


def _source_is_retrievable(source: Any) -> bool:
    if isinstance(source, SourceReference):
        return is_retrievable_source(source)
    explicit = _value(source, "allow_ai_retrieval", None)
    if explicit is not None:
        return bool(explicit)
    return bool(_value(source, "retrievable", True))


def _build_result(
    total_sources: int,
    chunks: list[SourceChunk],
) -> SourceIndexBuildResult:
    warnings = _unique([warning for chunk in chunks for warning in chunk.warnings])
    return SourceIndexBuildResult(
        total_sources=total_sources,
        total_chunks=len(chunks),
        indexable_chunks=sum(chunk.indexable for chunk in chunks),
        non_indexable_chunks=sum(not chunk.indexable for chunk in chunks),
        chunks=chunks,
        warnings=warnings,
    )


def _value(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
