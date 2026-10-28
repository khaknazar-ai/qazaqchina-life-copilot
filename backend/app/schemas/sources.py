from pydantic import BaseModel

from backend.app.domain.community import CommunityPost
from backend.app.domain.sources import SourceReference


class SourceListResponse(BaseModel):
    sources: list[SourceReference]


class CommunitySourceListResponse(BaseModel):
    posts: list[CommunityPost]
