from pathlib import Path

from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CORPUS_REVIEW,
    permissions_for_roles,
)
from backend.app.admin_auth.service import AdminAuthService, build_admin_auth_service
from backend.app.config import Settings
from backend.app.source_corpus.intake import repository_path
from backend.app.source_corpus.service import SourceCorpusService


def build_source_corpus_service(
    settings: Settings,
    *,
    project_root: Path | None = None,
    admin_auth_service: AdminAuthService | None = None,
) -> SourceCorpusService:
    root = project_root or Path(__file__).resolve().parents[3]
    auth = admin_auth_service or build_admin_auth_service(settings)
    if settings.SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED:
        # Separate trust projection from API authority. Citizen local sign-in must
        # retain disabled admin auth; this private service only checks reviewers.
        auth = build_admin_auth_service(settings.model_copy(update={"ADMIN_AUTH_ENABLED": True}))
    def reviewers() -> set[str]:
        return {
            token.actor_id
            for token in auth.config.tokens
            if auth.is_enabled()
            and token.active
            and PERMISSION_SOURCE_CORPUS_REVIEW in permissions_for_roles(token.roles)
        }

    path = (
        Path(settings.LOCAL_DATA_DIR) / "source_corpus.sqlite3"
        if settings.ENABLE_LOCAL_PERSISTENCE
        else ":memory:"
    )
    if settings.SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED:
        if path == ":memory:":
            raise ValueError(
                "Reviewed-source reading requires an existing persistent corpus ledger"
            )
        path = repository_path(root, path)
        if not path.is_file():
            raise ValueError(
                "Reviewed-source reading requires an existing persistent corpus ledger"
            )
    return SourceCorpusService(
        root, path, active_reviewer_ids=reviewers,
        readonly=settings.SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED,
    )
