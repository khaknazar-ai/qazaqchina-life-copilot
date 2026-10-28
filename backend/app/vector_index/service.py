from backend.app.embeddings.models import (
    EmbeddingBuildManifest,
    EmbeddingProviderConfig,
    EmbeddingRequest,
)
from backend.app.embeddings.providers import FakeEmbeddingProvider
from backend.app.embeddings.service import EmbeddingService
from backend.app.source_index.service import SourceIndexService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.vector_index.local_index import LocalVectorIndex
from backend.app.vector_index.models import (
    VectorIndexInspectionReport,
    VectorSearchRequest,
)


class VectorIndexService:
    def build_from_embedding_manifest(
        self,
        manifest: EmbeddingBuildManifest,
    ) -> LocalVectorIndex:
        return LocalVectorIndex(manifest.records)

    def inspect_index_from_source_registry(
        self,
        top_k: int = 5,
        dimensions: int = 16,
        sample_query: str = "lost passport in China",
    ) -> VectorIndexInspectionReport:
        registry = SourceRegistry.from_data_dir()
        source_index = SourceIndexService().build_index_from_sources(registry.all_sources())
        embedding_manifest = EmbeddingService().embed_chunks(
            source_index.chunks,
            config=EmbeddingProviderConfig(dimensions=dimensions),
            include_non_indexable=True,
        )
        vector_index = self.build_from_embedding_manifest(embedding_manifest)
        query_response = FakeEmbeddingProvider().embed_texts(
            EmbeddingRequest(texts=[sample_query], dimensions=dimensions)
        )
        sample_results = vector_index.search(
            VectorSearchRequest(
                query_vector=query_response.vectors[0],
                top_k=top_k,
            )
        )
        manifest = vector_index.build_manifest()
        return VectorIndexInspectionReport(
            manifest=manifest,
            sample_results=sample_results,
            notes=[
                "Local vector index uses deterministic fake embeddings only.",
                "No network or external embedding provider was used.",
                "No external vector DB used.",
                "No /api/chat integration.",
            ],
        )


def vector_index_report_to_jsonable(report: VectorIndexInspectionReport) -> dict:
    return report.model_dump(mode="json")


def vector_index_report_to_markdown(report: VectorIndexInspectionReport) -> str:
    manifest = report.manifest
    lines = [
        "# Local Vector Index Inspection",
        "",
        f"- Generated at: `{manifest.generated_at.isoformat()}`",
        f"- Total records: {manifest.total_records}",
        f"- Indexed records: {manifest.indexed_records}",
        f"- Skipped records: {manifest.skipped_records}",
        f"- Dimensions: {manifest.dimensions if manifest.dimensions is not None else 'mixed'}",
        f"- Provider: {manifest.provider or 'mixed'}",
        f"- Model: {manifest.model or 'mixed'}",
        f"- Used network: {manifest.used_network}",
        f"- Used external provider: {manifest.used_external_provider}",
        "",
        "No external vector DB used.",
        "No /api/chat integration.",
        "",
        "## Sample Results",
    ]
    if not report.sample_results:
        lines.append("- none")
    else:
        for result in report.sample_results:
            lines.append(
                "- "
                f"rank={result.rank} score={result.score:.6f} "
                f"source_id={result.source_id} chunk_id={result.chunk_id}"
            )
    lines.extend(["", "## Warnings"])
    if manifest.warnings:
        lines.extend(f"- {warning}" for warning in manifest.warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## Notes"])
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"
