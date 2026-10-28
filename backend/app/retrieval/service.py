from pathlib import Path

from backend.app.domain.enums import UserScenario
from backend.app.retrieval.keyword import LocalKeywordRetriever
from backend.app.retrieval.models import RetrievalQuery, RetrievalResult, RetrieverProtocol
from backend.app.retrieval.planner import (
    RetrievalPlan,
    RetrievalPlanningInput,
    build_retrieval_plan,
)
from backend.app.source_registry.registry import SourceRegistry


class RetrievalService:
    def __init__(
        self,
        source_registry: SourceRegistry | None = None,
        retriever: RetrieverProtocol | None = None,
    ) -> None:
        self.source_registry = source_registry or SourceRegistry.from_data_dir(Path("data/sources"))
        self.retriever = retriever or LocalKeywordRetriever(self.source_registry)

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        if query.source_pool == "community":
            return self.retriever.retrieve(query)
        authoritative = query.model_copy(update={
            "source_pool": "official_curated", "include_community": False,
            **({"language": None} if query.cross_language_official else {}),
        })
        if query.source_pool == "official_curated":
            return self.retriever.retrieve(authoritative)
        if not query.include_community:
            effective = authoritative if query.cross_language_official else query
            return self.retriever.retrieve(effective)
        # Candidate limits are applied independently. A large experience corpus
        # cannot consume the authoritative pool before the answer sees it.
        authoritative = self.retriever.retrieve(authoritative)
        community = self.retriever.retrieve(query.model_copy(update={"source_pool": "community"}))
        return [
            result.model_copy(update={"rank": rank})
            for rank, result in enumerate(
                [*authoritative, *community][:query.max_results], start=1,
            )
        ]

    def plan_retrieval(self, input: RetrievalPlanningInput) -> RetrievalPlan:
        return build_retrieval_plan(input)

    def retrieve_for_text(
        self,
        text: str,
        scenario: UserScenario | None = None,
        city: str | None = None,
        include_community: bool = True,
        max_results: int = 5,
    ) -> list[RetrievalResult]:
        return self.retrieve(
            RetrievalQuery(
                query=text,
                scenario=scenario,
                city=city,
                include_community=include_community,
                max_results=max_results,
            )
        )
