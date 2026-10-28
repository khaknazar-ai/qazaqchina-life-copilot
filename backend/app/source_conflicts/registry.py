from backend.app.domain.sources import SourceReference
from backend.app.source_registry.registry import SourceRegistry


def full_registry_sources(
    registry: SourceRegistry,
    *,
    retrievable_only: bool = False,
) -> list[SourceReference]:
    """Use the same complete evidence body in review and delivery checks."""
    sources = registry.retrievable_sources() if retrievable_only else registry.all_sources()
    result = []
    for source in sources:
        if not source.content:
            post = registry.get_community_post_by_id(source.source_id)
            if post is not None:
                body = "\n".join(
                    part
                    for part in (
                        post.title,
                        post.situation,
                        post.what_happened,
                        post.what_helped or "",
                        post.advice_for_others or "",
                    )
                    if part
                )
                source = source.model_copy(update={"content": body})
        result.append(source)
    return result
