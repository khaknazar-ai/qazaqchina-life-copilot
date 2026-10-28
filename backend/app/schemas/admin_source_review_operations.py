from backend.app.source_review_operations.models import (
    SourceReviewOperationAction,
    SourceReviewOperationCandidateStatus,
    SourceReviewOperationsDashboardReport,
)

ADMIN_SOURCE_REVIEW_OPERATIONS_WARNING = (
    "Admin source review operations status is not citizen-facing source authority."
)


class AdminSourceReviewOperationsResponse(SourceReviewOperationsDashboardReport):
    warning: str = ADMIN_SOURCE_REVIEW_OPERATIONS_WARNING


__all__ = [
    "ADMIN_SOURCE_REVIEW_OPERATIONS_WARNING",
    "AdminSourceReviewOperationsResponse",
    "SourceReviewOperationAction",
    "SourceReviewOperationCandidateStatus",
]
