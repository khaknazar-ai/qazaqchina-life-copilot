from pathlib import Path

from backend.app.domain.enums import SourceType
from backend.app.domain.sources import is_retrievable_source
from backend.app.schemas.sources import CommunitySourceListResponse, SourceListResponse
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry

DEFAULT_DATA_DIR = Path("data/sources")


class SourceService:
    def __init__(
        self,
        data_dir: Path = DEFAULT_DATA_DIR,
        trace_service: TraceService | None = None,
        source_registry: SourceRegistry | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.trace_service = trace_service
        self.source_registry = source_registry

    def list_sources(self) -> SourceListResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="source.list_sources",
                trace_id=trace_id,
                payload={},
            )

        registry = self.source_registry or SourceRegistry.from_data_dir(self.data_dir)
        source_pool = [*registry.official_sources(), *registry.curated_guides()]
        sources = [
            source
            for source in source_pool
            if source.source_type in {SourceType.official, SourceType.curated_guide}
            and is_retrievable_source(source)
        ]
        response = SourceListResponse(sources=sources)

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="source.list_sources",
                trace_id=trace_id,
                payload={"returned_source_count": len(response.sources)},
            )

        return response

    def list_community_sources(self) -> CommunitySourceListResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="source.list_community_sources",
                trace_id=trace_id,
                payload={},
            )

        registry = self.source_registry or SourceRegistry.from_data_dir(self.data_dir)
        response = CommunitySourceListResponse(posts=registry.retrievable_community_posts())

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="source.list_community_sources",
                trace_id=trace_id,
                payload={"returned_community_count": len(response.posts)},
            )

        return response
