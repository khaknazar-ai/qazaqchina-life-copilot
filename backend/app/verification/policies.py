from datetime import UTC, datetime

from backend.app.domain.community import ContributorProfile
from backend.app.domain.enums import VerificationStatus, VerifiedContributorRole

HIGH_TRUST_ROLES = {
    VerifiedContributorRole.verified_consul,
    VerifiedContributorRole.verified_vice_consul,
    VerifiedContributorRole.verified_consular_worker,
    VerifiedContributorRole.admin_curator,
}

INSTITUTIONAL_ROLES = HIGH_TRUST_ROLES

EXPERIENCED_COMMUNITY_ROLES = {
    VerifiedContributorRole.verified_student,
    VerifiedContributorRole.verified_worker,
    VerifiedContributorRole.verified_business_visitor,
    VerifiedContributorRole.verified_medical_visitor,
}


def is_high_trust_role(role: VerifiedContributorRole) -> bool:
    return role in HIGH_TRUST_ROLES


def is_institutional_role(role: VerifiedContributorRole) -> bool:
    return role in INSTITUTIONAL_ROLES


def is_experienced_community_role(role: VerifiedContributorRole) -> bool:
    return role in EXPERIENCED_COMMUNITY_ROLES


def role_requires_admin_approval(role: VerifiedContributorRole) -> bool:
    return role != VerifiedContributorRole.ordinary_user


def role_can_be_self_declared_but_not_trusted(role: str | None) -> bool:
    return bool(role and role.strip())


def verified_role_is_active(
    profile: ContributorProfile,
    now: datetime | None = None,
) -> bool:
    if profile.verification_status != VerificationStatus.verified:
        return False
    if profile.verified_role == VerifiedContributorRole.ordinary_user:
        return False
    if profile.verification_expires_at is None:
        return True

    current_time = _compatible_now(profile.verification_expires_at, now)
    return profile.verification_expires_at > current_time


def effective_trusted_role(
    profile: ContributorProfile,
    now: datetime | None = None,
) -> VerifiedContributorRole:
    if verified_role_is_active(profile, now=now):
        return profile.verified_role
    return VerifiedContributorRole.ordinary_user


def _compatible_now(expires_at: datetime, now: datetime | None) -> datetime:
    current_time = now or datetime.now(UTC)
    if expires_at.tzinfo is None and current_time.tzinfo is not None:
        return current_time.replace(tzinfo=None)
    if expires_at.tzinfo is not None and current_time.tzinfo is None:
        return current_time.replace(tzinfo=UTC)
    return current_time
