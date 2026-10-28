from backend.app.embeddings.models import (
    EmbeddingBuildManifest,
    EmbeddingProviderConfig,
    EmbeddingRecord,
    EmbeddingRequest,
)
from backend.app.embeddings.providers import EmbeddingProvider, create_embedding_provider
from backend.app.source_index.models import SourceChunk


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider

    def embed_chunks(
        self,
        chunks: list[SourceChunk],
        config: EmbeddingProviderConfig | None = None,
        include_non_indexable: bool = False,
    ) -> EmbeddingBuildManifest:
        active_config = config or EmbeddingProviderConfig()
        embeddable_chunks = [
            chunk
            for chunk in chunks
            if (chunk.indexable or include_non_indexable)
            and (active_config.provider == "fake" or chunk.retrievable)
        ]
        if active_config.provider != "fake" and include_non_indexable:
            raise ValueError("External providers cannot include non-indexable chunks.")
        provider = self.provider or create_embedding_provider(active_config)
        vectors: list[list[float]] = []
        response_warnings: list[str] = []
        used_network = False
        used_external = False
        batch_size = 10 if active_config.provider == "qwen" else max(len(embeddable_chunks), 1)
        for start in range(0, len(embeddable_chunks), batch_size):
            response = provider.embed_texts(
                EmbeddingRequest(
                    texts=[chunk.text for chunk in embeddable_chunks[start : start + batch_size]],
                    provider=active_config.provider,
                    model=active_config.model,
                    dimensions=active_config.dimensions,
                )
            )
            if (
                response.provider != active_config.provider
                or response.model != active_config.model
                or response.dimensions != active_config.dimensions
                or len(response.vectors) != len(embeddable_chunks[start : start + batch_size])
            ):
                raise ValueError("Embedding response does not match the configured vector space.")
            vectors.extend(response.vectors)
            response_warnings.extend(response.warnings)
            used_network |= response.used_network
            used_external |= response.used_external_provider
        records = [
            self.build_embedding_record(
                chunk=chunk,
                vector=vector,
                provider=active_config.provider,
                model=active_config.model,
                dimensions=active_config.dimensions,
            )
            for chunk, vector in zip(embeddable_chunks, vectors, strict=True)
        ]
        warnings = _unique(
            [
                *response_warnings,
                *[warning for chunk in embeddable_chunks for warning in chunk.warnings],
                *(
                    ["Non-indexable chunks were skipped by default."]
                    if len(embeddable_chunks) != len(chunks)
                    else []
                ),
                "No vector DB write was performed.",
            ]
        )
        return EmbeddingBuildManifest(
            provider=active_config.provider,
            model=active_config.model,
            dimensions=active_config.dimensions,
            total_chunks=len(chunks),
            embedded_chunks=len(records),
            skipped_chunks=len(chunks) - len(records),
            used_network=used_network,
            used_external_provider=used_external,
            records=records,
            warnings=warnings,
        )

    def build_embedding_record(
        self,
        chunk: SourceChunk,
        vector: list[float],
        provider: str,
        model: str,
        dimensions: int,
    ) -> EmbeddingRecord:
        return EmbeddingRecord(
            embedding_id=_embedding_id(provider, model, chunk.chunk_id, chunk.text_hash),
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            version_id=chunk.version_id,
            text_hash=chunk.text_hash,
            provider=provider,
            model=model,
            dimensions=dimensions,
            vector=vector,
            indexable=chunk.indexable,
            retrievable=chunk.retrievable,
            source_type=chunk.source_type,
            trust_level=chunk.trust_level,
            freshness_status=chunk.freshness_status,
            source_version_status=chunk.source_version_status,
            warnings=list(chunk.warnings),
        )


def embedding_manifest_to_jsonable(manifest: EmbeddingBuildManifest) -> dict:
    return manifest.model_dump(mode="json")


def embedding_manifest_to_markdown(manifest: EmbeddingBuildManifest) -> str:
    lines = [
        "# Embedding Adapter Manifest",
        "",
        f"- Generated at: `{manifest.generated_at.isoformat()}`",
        f"- Provider: {manifest.provider}",
        f"- Model: {manifest.model}",
        f"- Dimensions: {manifest.dimensions}",
        f"- Total chunks: {manifest.total_chunks}",
        f"- Embedded chunks: {manifest.embedded_chunks}",
        f"- Skipped chunks: {manifest.skipped_chunks}",
        f"- Used network: {manifest.used_network}",
        f"- Used external provider: {manifest.used_external_provider}",
        "",
        "No vector DB write was performed.",
        "",
        "## Warnings",
    ]
    if manifest.warnings:
        lines.extend(f"- {warning}" for warning in manifest.warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## Records"])
    if not manifest.records:
        lines.append("- none")
    else:
        for record in manifest.records:
            lines.append(
                "- "
                f"{record.embedding_id}: {record.chunk_id} "
                f"({record.dimensions} dimensions, indexable={record.indexable})"
            )
    return "\n".join(lines) + "\n"


def _embedding_id(provider: str, model: str, chunk_id: str, text_hash: str) -> str:
    return f"emb::{provider}::{model}::{chunk_id}::{text_hash}"


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
