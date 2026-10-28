from backend.app.admin.models import (
    AdminDecision,
    AdminDecisionAction,
    AdminReviewResult,
    AdminReviewType,
    CommunityModerationAdminResult,
    RoleVerificationAdminResult,
    SourceGovernanceAdminResult,
)
from backend.app.admin.policies import (
    action_requires_reason,
    admin_action_is_valid_for_review_type,
    can_action_enable_ai_retrieval,
    safe_ai_retrieval_after_admin_action,
)

__all__ = [
    "AdminDecision",
    "AdminDecisionAction",
    "AdminReviewResult",
    "AdminReviewService",
    "AdminReviewType",
    "CommunityModerationAdminResult",
    "RoleVerificationAdminResult",
    "SourceGovernanceAdminResult",
    "action_requires_reason",
    "admin_action_is_valid_for_review_type",
    "can_action_enable_ai_retrieval",
    "safe_ai_retrieval_after_admin_action",
]


def __getattr__(name: str):
    if name == "AdminReviewService":
        from backend.app.admin.service import AdminReviewService

        return AdminReviewService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
