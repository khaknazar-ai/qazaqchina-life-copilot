"""Local authenticated evaluation-review wiring; preflight never creates storage."""

from pathlib import Path

from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CORPUS_REVIEW,
    permissions_for_roles,
)
from backend.app.admin_auth.service import AdminAuthService, build_admin_auth_service
from backend.app.config import Settings
from backend.app.real_eval.dataset import load_real_material_cases
from backend.app.real_eval.review_service import EvaluationReviewService
from backend.app.source_corpus.intake import load_prepared_packets, repository_path


def build_evaluation_review_service(
    settings: Settings,
    *,
    project_root: Path | None = None,
    admin_auth_service: AdminAuthService | None = None,
    dataset_path: Path | str = "data/evals/real_material_cases.json",
    readonly: bool = False,
) -> EvaluationReviewService | None:
    auth = admin_auth_service or build_admin_auth_service(settings)
    if not auth.is_enabled() or not settings.ENABLE_LOCAL_PERSISTENCE:
        return None
    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    dataset = repository_path(root, dataset_path)
    directory = repository_path(root, settings.LOCAL_DATA_DIR)

    def materials():
        return (
            load_real_material_cases(dataset),
            load_prepared_packets(root, directory / "source_corpus/packets"),
        )

    def reviewers():
        return {
            (token.actor_id, token.token_id)
            for token in auth.config.tokens
            if auth.is_enabled()
            and token.active
            and PERMISSION_SOURCE_CORPUS_REVIEW in permissions_for_roles(token.roles)
        }

    return EvaluationReviewService(
        root,
        directory / "evaluation_reviews.sqlite3",
        load_materials=materials,
        active_reviewer_keys=reviewers,
        readonly=readonly,
    )
