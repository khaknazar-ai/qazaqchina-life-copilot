from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.domain.community import CommunityPost, ContributorProfile
from backend.app.domain.enums import (
    ModerationStatus,
    VerificationStatus,
    VerifiedContributorRole,
)
from backend.app.moderation.service import CommunityModerationService
from backend.app.persistence.base import CommunityPostRepositoryProtocol
from backend.app.schemas.community import (
    CommunityPostCreateRequest,
    CommunityPostListResponse,
    CommunityPostResponse,
)
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry

DEFAULT_DATA_DIR = Path("data/sources")


class CommunityService:
    def __init__(
        self,
        data_dir: Path = DEFAULT_DATA_DIR,
        trace_service: TraceService | None = None,
        moderation_service: CommunityModerationService | None = None,
        post_repository: CommunityPostRepositoryProtocol | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.trace_service = trace_service
        self.moderation_service = moderation_service
        self.post_repository = post_repository

    def create_post(self, request: CommunityPostCreateRequest) -> CommunityPostResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="community.create_post",
                trace_id=trace_id,
                payload={
                    "scenario": request.scenario.value,
                    "city": request.city,
                    "requested_allow_ai_retrieval": request.allow_ai_retrieval,
                },
            )

        contributor = self.create_contributor_profile_from_request(request)
        post = CommunityPost(
            post_id=f"POST-{uuid4().hex.upper()}",
            author=contributor,
            title=request.title,
            city=request.city,
            scenario=request.scenario,
            language=request.language,
            situation=request.situation,
            what_happened=request.what_happened,
            what_helped=request.what_helped,
            required_documents=request.required_documents,
            mistakes_to_avoid=request.mistakes_to_avoid,
            advice_for_others=request.advice_for_others,
            tags=request.tags,
            moderation_status=ModerationStatus.pending,
            allow_ai_retrieval=False,
            ai_retrieval_consent=request.allow_ai_retrieval,
            created_at=datetime.now(UTC),
        )
        moderation_result = (
            self.moderation_service.moderate_post(post) if self.moderation_service else None
        )
        if self.post_repository:
            self.post_repository.save_post(post)

        response = CommunityPostResponse(
            post=post,
            message=(
                "Community post created as pending. It is not available for AI use; "
                "human review is required before retrieval."
            ),
            moderation_result=moderation_result,
        )

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="community.create_post",
                trace_id=trace_id,
                payload={
                    "scenario": post.scenario.value,
                    "city": post.city,
                    "moderation_status": post.moderation_status.value,
                    "allow_ai_retrieval": post.allow_ai_retrieval,
                    "moderation_recommendation": (
                        moderation_result.status_recommendation.value if moderation_result else None
                    ),
                },
            )

        return response

    def create_contributor_profile_from_request(
        self,
        request: CommunityPostCreateRequest,
    ) -> ContributorProfile:
        return ContributorProfile(
            contributor_id=f"CONTR-{uuid4().hex.upper()}",
            display_name="Pending community contributor",
            self_declared_role=request.self_declared_role,
            verified_role=VerifiedContributorRole.ordinary_user,
            verification_status=VerificationStatus.unverified,
        )

    def list_posts(self) -> CommunityPostListResponse:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else None
        if self.trace_service and trace_id:
            self.trace_service.log_service_start(
                service_name="community.list_posts",
                trace_id=trace_id,
                payload={},
            )

        if self.post_repository:
            posts = [
                post
                for post in self.post_repository.list_posts()
                if post.moderation_status == ModerationStatus.approved
            ]
        else:
            registry = SourceRegistry.from_data_dir(self.data_dir)
            posts = registry.approved_community_posts()
        from backend.app.persistence.runtime_sources import sanitize_community_post

        # Legacy approved rows may predate the safety gate. Recheck before display.
        moderator = self.moderation_service or CommunityModerationService()
        posts = [
            sanitize_community_post(post)
            for post in posts
            if not moderator.moderate_post(post).findings
        ]
        response = CommunityPostListResponse(posts=posts)

        if self.trace_service and trace_id:
            self.trace_service.log_service_end(
                service_name="community.list_posts",
                trace_id=trace_id,
                payload={"returned_post_count": len(response.posts)},
            )

        return response
