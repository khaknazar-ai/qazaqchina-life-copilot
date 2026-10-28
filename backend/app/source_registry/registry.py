from pathlib import Path

from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import (
    ModerationStatus,
    SourceType,
    TrustLevel,
    UserScenario,
    VerifiedContributorRole,
)
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.source_registry.loader import (
    load_community_posts,
    load_curated_guides,
    load_official_sources,
)
from backend.app.verification.policies import effective_trusted_role

DEFAULT_SOURCE_DATA_DIR = Path("data/sources")

_INSTITUTIONAL_ROLES = {
    VerifiedContributorRole.verified_consular_worker,
    VerifiedContributorRole.verified_vice_consul,
    VerifiedContributorRole.verified_consul,
    VerifiedContributorRole.admin_curator,
}

_EXPERIENCED_ROLES = {
    VerifiedContributorRole.verified_student,
    VerifiedContributorRole.verified_worker,
    VerifiedContributorRole.verified_business_visitor,
    VerifiedContributorRole.verified_medical_visitor,
}


class SourceRegistry:
    def __init__(
        self,
        official_sources: list[SourceReference],
        curated_guides: list[SourceReference],
        community_posts: list[CommunityPost],
    ) -> None:
        self._official_sources = official_sources
        self._curated_guides = curated_guides
        self._community_posts = community_posts

    @classmethod
    def from_data_dir(cls, data_dir: Path = DEFAULT_SOURCE_DATA_DIR) -> "SourceRegistry":
        official_sources = load_official_sources(data_dir / "official_sources.jsonl")
        kazakhstan_visa_snapshot = data_dir / "kazakhstan_visa_regime.jsonl"
        if kazakhstan_visa_snapshot.exists():
            official_sources.extend(load_official_sources(kazakhstan_visa_snapshot))
        kazakhstan_foreigner_services = data_dir / "kazakhstan_foreigner_services.jsonl"
        if kazakhstan_foreigner_services.exists():
            official_sources.extend(load_official_sources(kazakhstan_foreigner_services))
        return cls(
            official_sources=official_sources,
            curated_guides=load_curated_guides(data_dir / "curated_guides.jsonl"),
            community_posts=load_community_posts(data_dir / "community_posts.jsonl"),
        )

    def all_sources(self) -> list[SourceReference]:
        return [
            *self._official_sources,
            *self._curated_guides,
            *(self._community_post_to_source(post) for post in self._community_posts),
        ]

    def retrievable_sources(self) -> list[SourceReference]:
        return [source for source in self.all_sources() if is_retrievable_source(source)]

    def official_sources(self) -> list[SourceReference]:
        return list(self._official_sources)

    def curated_guides(self) -> list[SourceReference]:
        return list(self._curated_guides)

    def approved_community_posts(self) -> list[CommunityPost]:
        return [
            post
            for post in self._community_posts
            if post.moderation_status == ModerationStatus.approved
        ]

    def retrievable_community_posts(self) -> list[CommunityPost]:
        return [post for post in self._community_posts if post.can_be_used_by_ai]

    def get_source_by_id(self, source_id: str) -> SourceReference | None:
        return next(
            (source for source in self.all_sources() if source.source_id == source_id),
            None,
        )

    def get_community_post_by_id(self, post_id: str) -> CommunityPost | None:
        return next((post for post in self._community_posts if post.post_id == post_id), None)

    def filter_sources_by_scenario(self, scenario: UserScenario) -> list[SourceReference]:
        return [source for source in self.all_sources() if source.scenario == scenario]

    def filter_community_by_scenario(self, scenario: UserScenario) -> list[CommunityPost]:
        return [post for post in self._community_posts if post.scenario == scenario]

    def filter_sources_by_city(self, city: str) -> list[SourceReference]:
        city_normalized = city.casefold()
        return [
            source
            for source in self.all_sources()
            if source.city is not None and source.city.casefold() == city_normalized
        ]

    @staticmethod
    def _community_post_to_source(post: CommunityPost) -> SourceReference:
        source_type, trust_level = _community_source_type_and_trust(post)

        return SourceReference(
            source_id=post.post_id,
            title=post.title,
            source_type=source_type,
            trust_level=trust_level,
            language=post.language,
            date_published=post.created_at.date(),
            collected_at=post.created_at,
            city=post.city,
            scenario=post.scenario,
            moderation_status=post.moderation_status,
            allow_ai_retrieval=post.can_be_used_by_ai,
        )


def _community_source_type_and_trust(post: CommunityPost) -> tuple[SourceType, TrustLevel]:
    trusted_role = effective_trusted_role(post.author)
    if trusted_role == VerifiedContributorRole.ordinary_user:
        return SourceType.ordinary_community, TrustLevel.level_5_ordinary_community

    if trusted_role in _INSTITUTIONAL_ROLES:
        return (
            SourceType.verified_institutional_contributor,
            TrustLevel.level_3_verified_institutional,
        )

    if trusted_role in _EXPERIENCED_ROLES:
        return (
            SourceType.verified_experienced_contributor,
            TrustLevel.level_4_verified_experienced,
        )

    return SourceType.ordinary_community, TrustLevel.level_5_ordinary_community
