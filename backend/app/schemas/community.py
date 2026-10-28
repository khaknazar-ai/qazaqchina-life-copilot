from pydantic import BaseModel, Field

from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import LanguageCode, UserScenario
from backend.app.moderation.models import ModerationResult


class CommunityPostCreateRequest(BaseModel):
    title: str
    city: str | None = None
    scenario: UserScenario
    language: LanguageCode = LanguageCode.ru
    situation: str
    what_happened: str
    what_helped: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    mistakes_to_avoid: list[str] = Field(default_factory=list)
    advice_for_others: str | None = None
    tags: list[str] = Field(default_factory=list)
    allow_ai_retrieval: bool = False
    self_declared_role: str | None = None


class CommunityPostResponse(BaseModel):
    post: CommunityPost
    message: str
    moderation_result: ModerationResult | None = None


class CommunityPostListResponse(BaseModel):
    posts: list[CommunityPost]
