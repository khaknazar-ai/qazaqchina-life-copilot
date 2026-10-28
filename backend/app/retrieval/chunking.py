from backend.app.domain.sources import SourceReference
from backend.app.retrieval.models import DocumentChunk


def chunk_source(
    source: SourceReference,
    content: str,
    max_chars: int = 700,
) -> list[DocumentChunk]:
    if not content.strip():
        return []

    chunks: list[DocumentChunk] = []
    paragraphs = [paragraph.strip() for paragraph in content.splitlines() if paragraph.strip()]

    for paragraph in paragraphs:
        for piece in _split_paragraph(paragraph, max_chars=max_chars):
            chunk_index = len(chunks)
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{source.source_id}::chunk-{chunk_index}",
                    source=source,
                    content=piece,
                    chunk_index=chunk_index,
                    metadata=_source_metadata(source),
                )
            )

    return chunks


def _split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    return [
        paragraph[index : index + max_chars].strip()
        for index in range(0, len(paragraph), max_chars)
        if paragraph[index : index + max_chars].strip()
    ]


def _source_metadata(source: SourceReference) -> dict[str, str]:
    metadata = {
        "source_id": source.source_id,
        "title": source.title,
        "source_type": source.source_type.value,
        "trust_level": source.trust_level.value,
        "language": source.language.value,
    }
    if source.city:
        metadata["city"] = source.city
    if source.scenario:
        metadata["scenario"] = source.scenario.value
    return metadata
