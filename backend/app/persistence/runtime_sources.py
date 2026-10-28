"""Build per-request source snapshots from reviewed local community state."""

from backend.app.answer_quality.policies import is_synthetic_source
from backend.app.config import Settings
from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import VerificationStatus, VerifiedContributorRole
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.service import CommunityModerationService
from backend.app.persistence.factory import (
    build_community_post_repository,
    build_verification_record_repository,
)
from backend.app.source_corpus.service import SourceCorpusService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.verification.policies import effective_trusted_role

_CONTENT_FIELDS = (
    "title",
    "city",
    "situation",
    "what_happened",
    "what_helped",
    "advice_for_others",
)
_LIST_FIELDS = ("required_documents", "mistakes_to_avoid", "tags")


def build_runtime_source_registry(
    settings: Settings,
    corpus_service: SourceCorpusService | None = None,
) -> SourceRegistry:
    # Flat-file sources are offline demonstration fixtures. Live inference must
    # start from reviewed corpus publications, including when generation fails.
    live = any((settings.OLLAMA_CHAT_ENABLED, settings.QWEN_CHAT_ENABLED,
                settings.CLOUD_RETRIEVAL_ENABLED))
    registry = SourceRegistry([], [], []) if live else SourceRegistry.from_data_dir()
    if corpus_service is not None:
        shadowed, published = corpus_service.runtime_projection()
        registry = SourceRegistry(
            [s for s in registry.official_sources() if s.source_id not in shadowed]
            + [s for s in published if not live or not is_synthetic_source(s)],
            [s for s in registry.curated_guides() if s.source_id not in shadowed],
            registry.retrievable_community_posts(),
        )
    if not settings.ENABLE_LOCAL_PERSISTENCE:
        return registry
    local_posts = build_community_post_repository(settings.LOCAL_DATA_DIR).list_posts()
    # A new blocked state must shadow a formerly retrievable version, including seed IDs.
    local_ids = {post.post_id for post in local_posts}
    posts = [
        post for post in registry.retrievable_community_posts() if post.post_id not in local_ids
    ]
    verification_records = build_verification_record_repository(
        settings.LOCAL_DATA_DIR
    ).list_verification_records()
    latest_verification = {record.contributor_id: record for record in verification_records}
    for post in local_posts:
        # Stored legacy allow flags do not establish explicit author consent.
        if post.ai_retrieval_consent is not True or not post.can_be_used_by_ai:
            continue
        if live and _synthetic_post(post):
            continue
        sanitized = sanitize_community_post(post)
        # Redaction is heuristic. Any remaining moderation finding fails closed for retrieval.
        if CommunityModerationService().moderate_post(sanitized).findings:
            continue
        record = latest_verification.get(sanitized.author.contributor_id)
        active_role = effective_trusted_role(sanitized.author)
        if (
            active_role == VerifiedContributorRole.ordinary_user
            or record is None
            or record.decision != "approved"
            or record.requested_role != active_role.value
        ):
            sanitized.author = sanitized.author.model_copy(
                update={
                    "verified_role": VerifiedContributorRole.ordinary_user,
                    "verification_status": VerificationStatus.unverified,
                }
            )
        posts.append(sanitized)
    return SourceRegistry(registry.official_sources(), registry.curated_guides(), posts)


def _synthetic_post(post: CommunityPost) -> bool:
    # Check the original before sanitizing author display fields. Never turn a
    # fictional preview into community evidence by approving its moderation flag.
    values = [getattr(post, field) for field in _CONTENT_FIELDS]
    values.extend(value for field in _LIST_FIELDS for value in getattr(post, field))
    values.append(post.author.display_name)
    return any("synthetic" in str(value or "").casefold() for value in values)


def sanitize_community_post(post: CommunityPost) -> CommunityPost:
    updates = {
        field: redact_sensitive_text(value)[0] if value is not None else None
        for field in _CONTENT_FIELDS
        if (value := getattr(post, field)) is not None
    }
    updates.update(
        {
            field: [redact_sensitive_text(value)[0] for value in getattr(post, field)]
            for field in _LIST_FIELDS
        }
    )
    updates["author"] = post.author.model_copy(
        update={
            "display_name": "Community contributor",
            "self_declared_role": None,
            "institution_name": (
                redact_sensitive_text(post.author.institution_name)[0]
                if post.author.institution_name
                else None
            ),
        },
        deep=True,
    )
    return post.model_copy(update=updates, deep=True)
