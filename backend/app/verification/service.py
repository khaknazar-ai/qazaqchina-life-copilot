from datetime import UTC, datetime

from backend.app.domain.community import ContributorProfile
from backend.app.domain.enums import VerificationStatus, VerifiedContributorRole
from backend.app.persistence.base import VerificationRecordRepositoryProtocol
from backend.app.verification.models import (
    RoleVerificationDecision,
    RoleVerificationRequest,
    RoleVerificationResult,
)
from backend.app.verification.policies import is_high_trust_role


class ContributorVerificationService:
    def __init__(
        self,
        verification_repository: VerificationRecordRepositoryProtocol | None = None,
    ) -> None:
        self.verification_repository = verification_repository

    def request_verification(
        self,
        profile: ContributorProfile,
        request: RoleVerificationRequest,
    ) -> RoleVerificationResult:
        self._save_verification_request(request)
        updated_profile = profile.model_copy(
            update={
                "self_declared_role": request.self_declared_role
                if request.self_declared_role is not None
                else profile.self_declared_role,
                "institution_name": request.institution_name
                if request.institution_name is not None
                else profile.institution_name,
                "verification_status": VerificationStatus.verification_requested,
            }
        )
        return RoleVerificationResult(
            contributor=updated_profile,
            message=(
                "Verification request recorded. Self-declared roles are not trusted "
                "until admin approval."
            ),
            changed=True,
        )

    def approve(
        self,
        profile: ContributorProfile,
        decision: RoleVerificationDecision,
    ) -> RoleVerificationResult:
        self._save_verification_decision(decision)
        updated_profile = profile.model_copy(
            update={
                "verified_role": decision.requested_role,
                "verification_status": VerificationStatus.verified,
                "verified_at": datetime.now(UTC),
            }
        )
        message = f"Contributor role approved as {decision.requested_role.value}."
        if is_high_trust_role(decision.requested_role) and not profile.institution_name:
            message += " Institution evidence should be reviewed in production."
        return RoleVerificationResult(
            contributor=updated_profile,
            message=message,
            changed=True,
        )

    def reject(
        self,
        profile: ContributorProfile,
        decision: RoleVerificationDecision,
    ) -> RoleVerificationResult:
        self._save_verification_decision(decision)
        updated_profile = profile.model_copy(
            update={
                "verified_role": VerifiedContributorRole.ordinary_user,
                "verification_status": VerificationStatus.verification_rejected,
            }
        )
        return RoleVerificationResult(
            contributor=updated_profile,
            message="Verification request rejected. Contributor remains ordinary user.",
            changed=True,
        )

    def revoke(
        self,
        profile: ContributorProfile,
        decision: RoleVerificationDecision,
    ) -> RoleVerificationResult:
        self._save_verification_decision(decision)
        updated_profile = profile.model_copy(
            update={
                "verified_role": VerifiedContributorRole.ordinary_user,
                "verification_status": VerificationStatus.revoked,
            }
        )
        return RoleVerificationResult(
            contributor=updated_profile,
            message="Contributor verification revoked.",
            changed=True,
        )

    def expire(
        self,
        profile: ContributorProfile,
        decision: RoleVerificationDecision,
    ) -> RoleVerificationResult:
        self._save_verification_decision(decision)
        updated_profile = profile.model_copy(
            update={
                "verified_role": VerifiedContributorRole.ordinary_user,
                "verification_status": VerificationStatus.verification_expired,
                "verification_expires_at": datetime.now(UTC),
            }
        )
        return RoleVerificationResult(
            contributor=updated_profile,
            message="Contributor verification expired.",
            changed=True,
        )

    def apply_decision(
        self,
        profile: ContributorProfile,
        decision: RoleVerificationDecision,
    ) -> RoleVerificationResult:
        if decision.decision == "approved":
            return self.approve(profile, decision)
        if decision.decision == "rejected":
            return self.reject(profile, decision)
        if decision.decision == "revoked":
            return self.revoke(profile, decision)
        if decision.decision == "expired":
            return self.expire(profile, decision)
        raise ValueError(f"Unknown role verification decision: {decision.decision}")

    def _save_verification_request(self, request: RoleVerificationRequest) -> None:
        if self.verification_repository:
            self.verification_repository.save_verification_request(request)

    def _save_verification_decision(self, decision: RoleVerificationDecision) -> None:
        if self.verification_repository:
            self.verification_repository.save_verification_decision(decision)
