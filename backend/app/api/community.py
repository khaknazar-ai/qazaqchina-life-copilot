from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_community_service
from backend.app.schemas.community import (
    CommunityPostCreateRequest,
    CommunityPostListResponse,
    CommunityPostResponse,
)
from backend.app.services.community_service import CommunityService

router = APIRouter(prefix="/api", tags=["community"])


@router.post("/community/posts", response_model=CommunityPostResponse)
def create_community_post(
    request: CommunityPostCreateRequest,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> CommunityPostResponse:
    return service.create_post(request)


@router.get("/community/posts", response_model=CommunityPostListResponse)
def list_community_posts(
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> CommunityPostListResponse:
    return service.list_posts()
