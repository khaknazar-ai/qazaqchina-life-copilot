from typing import Literal, Protocol

from pydantic import BaseModel, Field

from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference


class DocumentChunk(BaseModel):
    chunk_id: str
    source: SourceReference
    content: str
    chunk_index: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalQuery(BaseModel):
    query: str
    scenario: UserScenario | None = None
    city: str | None = None
    language: LanguageCode | None = None
    cross_language_official: bool = False
    risk_level: RiskLevel | None = None
    include_community: bool = True
    source_pool: Literal["official_curated", "community"] | None = None
    max_results: int = Field(default=5, gt=0)


class RetrievalResult(BaseModel):
    chunk: DocumentChunk
    score: float
    rank: int | None = None
    match_reasons: list[str] = Field(default_factory=list)


class RetrieverProtocol(Protocol):
    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """Retrieve ranked chunks for a deterministic local query."""
