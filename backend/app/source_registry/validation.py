from collections.abc import Sequence

from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import (
    ModerationStatus,
    SourceType,
    TrustLevel,
    VerificationStatus,
    VerifiedContributorRole,
)
from backend.app.domain.sources import SourceReference, is_retrievable_source


def validate_source_reference(source: SourceReference) -> list[str]:
    warnings: list[str] = []

    if not source.source_id.strip():
        warnings.append("source_id must not be empty")

    if (
        source.source_type == SourceType.official
        and source.trust_level != TrustLevel.level_1_official
    ):
        warnings.append(f"{source.source_id}: official sources must use level_1_official")

    if (
        source.trust_level == TrustLevel.level_1_official
        and source.source_type != SourceType.official
    ):
        warnings.append(f"{source.source_id}: level_1_official must use source_type official")

    if (
        source.source_type == SourceType.curated_guide
        and source.trust_level != TrustLevel.level_2_curated
    ):
        warnings.append(f"{source.source_id}: curated guides must use level_2_curated")

    if (
        source.trust_level == TrustLevel.level_2_curated
        and source.source_type != SourceType.curated_guide
    ):
        warnings.append(f"{source.source_id}: level_2_curated must use source_type curated_guide")

    is_untrusted = (
        source.source_type == SourceType.untrusted
        or source.trust_level == TrustLevel.level_6_untrusted
    )
    if is_untrusted and source.allow_ai_retrieval:
        warnings.append(f"{source.source_id}: untrusted sources must not allow AI retrieval")

    if is_untrusted and is_retrievable_source(source):
        warnings.append(f"{source.source_id}: untrusted sources must never be retrievable")

    return warnings


def validate_community_post(post: CommunityPost) -> list[str]:
    warnings: list[str] = []

    if not post.post_id.strip():
        warnings.append("post_id must not be empty")

    if post.moderation_status != ModerationStatus.approved:
        warnings.append(f"{post.post_id}: community posts must be approved before AI use")

    if not post.allow_ai_retrieval:
        warnings.append(f"{post.post_id}: community posts need allow_ai_retrieval for AI use")

    if post.moderation_status != ModerationStatus.approved and post.allow_ai_retrieval:
        warnings.append(
            f"{post.post_id}: {post.moderation_status.value} posts must not allow AI retrieval"
        )

    if (
        post.author.verified_role != VerifiedContributorRole.ordinary_user
        and post.author.verification_status != VerificationStatus.verified
    ):
        warnings.append(
            f"{post.post_id}: verified contributor trust requires verification_status verified"
        )

    return warnings


def validate_source_registry_records(
    sources: Sequence[SourceReference],
    community_posts: Sequence[CommunityPost],
) -> list[str]:
    warnings: list[str] = []
    seen_source_ids: set[str] = set()
    seen_post_ids: set[str] = set()

    for source in sources:
        if source.source_id in seen_source_ids:
            warnings.append(f"{source.source_id}: duplicate source_id")
        seen_source_ids.add(source.source_id)
        warnings.extend(validate_source_reference(source))

    for post in community_posts:
        if post.post_id in seen_post_ids:
            warnings.append(f"{post.post_id}: duplicate post_id")
        seen_post_ids.add(post.post_id)
        warnings.extend(validate_community_post(post))

    return warnings
