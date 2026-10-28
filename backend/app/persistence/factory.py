from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.app.persistence.jsonl_store import JsonlRecordStore
from backend.app.persistence.repositories import (
    JsonlAdminDecisionRepository,
    JsonlCaseRepository,
    JsonlCommunityPostRepository,
    JsonlVerificationRecordRepository,
)

if TYPE_CHECKING:
    from backend.app.admin.service import AdminReviewService


def build_local_record_store(
    base_dir: Path | str,
    filename: str = "records.jsonl",
) -> JsonlRecordStore:
    return JsonlRecordStore(Path(base_dir) / filename)


def build_case_repository(base_dir: Path | str) -> JsonlCaseRepository:
    return JsonlCaseRepository(build_local_record_store(base_dir, "cases.jsonl"))


def build_community_post_repository(base_dir: Path | str) -> JsonlCommunityPostRepository:
    return JsonlCommunityPostRepository(build_local_record_store(base_dir, "community_posts.jsonl"))


def build_admin_decision_repository(base_dir: Path | str) -> JsonlAdminDecisionRepository:
    return JsonlAdminDecisionRepository(build_local_record_store(base_dir, "admin_decisions.jsonl"))


def build_verification_record_repository(
    base_dir: Path | str,
) -> JsonlVerificationRecordRepository:
    return JsonlVerificationRecordRepository(
        build_local_record_store(base_dir, "verification_records.jsonl")
    )


def build_admin_review_service(base_dir: Path | str | None = None) -> AdminReviewService:
    from backend.app.admin.service import AdminReviewService
    from backend.app.source_candidates.service import SourceCandidateQueueService
    from backend.app.source_versioning.service import SourceVersioningService
    from backend.app.verification.service import ContributorVerificationService

    if base_dir is None:
        return AdminReviewService()
    return AdminReviewService(
        admin_decision_repository=build_admin_decision_repository(base_dir),
        verification_service=ContributorVerificationService(
            verification_repository=build_verification_record_repository(base_dir)
        ),
        source_candidate_queue_service=SourceCandidateQueueService(
            repository=build_local_record_store(base_dir, "source_candidates.jsonl")
        ),
        source_versioning_service=SourceVersioningService(
            store_path=Path(base_dir) / "source_versions.jsonl"
        ),
    )
