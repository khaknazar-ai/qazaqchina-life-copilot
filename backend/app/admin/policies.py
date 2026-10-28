from backend.app.admin.models import AdminDecisionAction, AdminReviewType
from backend.app.domain.enums import ModerationStatus

REASON_REQUIRED_ACTIONS = {
    AdminDecisionAction.reject,
    AdminDecisionAction.flag,
    AdminDecisionAction.revoke,
    AdminDecisionAction.expire,
    AdminDecisionAction.request_changes,
}

VALID_ACTIONS_BY_REVIEW_TYPE = {
    AdminReviewType.community_post: {
        AdminDecisionAction.approve,
        AdminDecisionAction.reject,
        AdminDecisionAction.flag,
        AdminDecisionAction.request_changes,
        AdminDecisionAction.no_action,
    },
    AdminReviewType.role_verification: {
        AdminDecisionAction.approve,
        AdminDecisionAction.reject,
        AdminDecisionAction.revoke,
        AdminDecisionAction.expire,
        AdminDecisionAction.request_changes,
        AdminDecisionAction.no_action,
    },
    AdminReviewType.source_conflict: {
        AdminDecisionAction.approve,
        AdminDecisionAction.flag,
        AdminDecisionAction.request_changes,
        AdminDecisionAction.no_action,
    },
    AdminReviewType.citation_issue: {
        AdminDecisionAction.approve,
        AdminDecisionAction.flag,
        AdminDecisionAction.request_changes,
        AdminDecisionAction.no_action,
    },
    AdminReviewType.source_registry_record: {
        AdminDecisionAction.approve,
        AdminDecisionAction.reject,
        AdminDecisionAction.flag,
        AdminDecisionAction.request_changes,
        AdminDecisionAction.no_action,
    },
}


def action_requires_reason(action: str, review_type: str | None = None) -> bool:
    parsed_action = AdminDecisionAction(action)
    if parsed_action in REASON_REQUIRED_ACTIONS:
        return True
    return parsed_action == AdminDecisionAction.approve and review_type in {
        AdminReviewType.role_verification.value,
        AdminReviewType.source_conflict.value,
    }


def can_action_enable_ai_retrieval(action: str) -> bool:
    return AdminDecisionAction(action) == AdminDecisionAction.approve


def admin_action_is_valid_for_review_type(action: str, review_type: str) -> bool:
    parsed_action = AdminDecisionAction(action)
    parsed_review_type = AdminReviewType(review_type)
    return parsed_action in VALID_ACTIONS_BY_REVIEW_TYPE[parsed_review_type]


def safe_ai_retrieval_after_admin_action(
    action: str,
    moderation_status: ModerationStatus,
) -> bool:
    return (
        AdminDecisionAction(action) == AdminDecisionAction.approve
        and moderation_status == ModerationStatus.approved
    )
