import re
from hashlib import sha256

_BOUNDARY_PATTERN = re.compile(r"[.!?;:]\s+")


def normalize_chunk_text(text: str) -> str:
    return " ".join(text.split())


def stable_text_hash(text: str) -> str:
    return sha256(normalize_chunk_text(text).encode("utf-8")).hexdigest()


def make_chunk_id(
    source_id: str,
    version_id: str | None,
    chunk_index: int,
    text_hash: str,
) -> str:
    version_part = version_id or "unversioned"
    return f"{source_id}::{version_part}::chunk-{chunk_index:04d}::{text_hash[:12]}"


def split_text_into_chunks(
    text: str,
    max_chunk_chars: int = 900,
    overlap_chars: int = 120,
) -> list[str]:
    normalized = normalize_chunk_text(text)
    if not normalized:
        return []

    max_chars = max(1, int(max_chunk_chars))
    overlap = max(0, min(int(overlap_chars), max_chars - 1))
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            end = _preferred_boundary(normalized, start, end) or end

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break

        next_start = max(end - overlap, start + 1)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def _preferred_boundary(text: str, start: int, end: int) -> int | None:
    minimum = start + max(1, int((end - start) * 0.5))
    boundary_end: int | None = None
    for match in _BOUNDARY_PATTERN.finditer(text, start, end):
        if match.end() >= minimum:
            boundary_end = match.end()
    if boundary_end is None or boundary_end <= start:
        return None
    return boundary_end
