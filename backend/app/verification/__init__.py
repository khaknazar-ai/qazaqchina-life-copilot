from backend.app.verification.models import (
    AnswerVerificationReport,
    AnswerVerificationRequest,
    RoleVerificationDecision,
    RoleVerificationRequest,
    RoleVerificationResult,
    VerificationIssue,
)
from backend.app.verification.policies import (
    effective_trusted_role,
    is_experienced_community_role,
    is_high_trust_role,
    is_institutional_role,
    role_can_be_self_declared_but_not_trusted,
    role_requires_admin_approval,
    verified_role_is_active,
)

__all__ = [
    "AnswerVerificationReport",
    "AnswerVerificationRequest",
    "ContributorVerificationService",
    "RoleVerificationDecision",
    "RoleVerificationRequest",
    "RoleVerificationResult",
    "VerificationIssue",
    "build_answer_verification_request",
    "effective_trusted_role",
    "is_experienced_community_role",
    "is_high_trust_role",
    "is_institutional_role",
    "role_can_be_self_declared_but_not_trusted",
    "role_requires_admin_approval",
    "verified_role_is_active",
    "verification_report_to_jsonable",
    "verification_report_to_markdown",
    "verify_answer",
]


def __getattr__(name: str):
    if name == "ContributorVerificationService":
        from backend.app.verification.service import ContributorVerificationService

        return ContributorVerificationService
    if name in {
        "build_answer_verification_request",
        "verification_report_to_jsonable",
        "verification_report_to_markdown",
        "verify_answer",
    }:
        from backend.app.verification import answer_verifier

        return getattr(answer_verifier, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
