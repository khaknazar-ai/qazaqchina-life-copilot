from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from backend.app.persistence.models import (
    AdminDecisionRecord,
    PersistenceWriteResult,
    StoredRecord,
    VerificationRecord,
)

if TYPE_CHECKING:
    from backend.app.admin.models import AdminDecision
    from backend.app.domain.cases import UserCase
    from backend.app.domain.community import CommunityPost
    from backend.app.verification.models import (
        RoleVerificationDecision,
        RoleVerificationRequest,
    )


class RecordStoreProtocol(Protocol):
    def append(
        self,
        record_type: str,
        payload: dict,
        record_id: str | None = None,
    ) -> PersistenceWriteResult:
        """Append one structured record to local storage."""

    def list_records(self, record_type: str | None = None) -> list[StoredRecord]:
        """List records, optionally filtered by type."""

    def get(self, record_id: str) -> StoredRecord:
        """Return one record by ID."""

    def clear(self) -> None:
        """Clear local records from the store."""


class CaseRepositoryProtocol(Protocol):
    def save_case(self, case: UserCase) -> PersistenceWriteResult:
        """Save a user case."""

    def list_cases(self) -> list[UserCase]:
        """List saved user cases."""

    def get_case(self, case_id: str) -> UserCase:
        """Get one saved user case."""


class CommunityPostRepositoryProtocol(Protocol):
    def save_post(self, post: CommunityPost) -> PersistenceWriteResult:
        """Save a community post."""

    def list_posts(self) -> list[CommunityPost]:
        """List saved community posts."""

    def get_post(self, post_id: str) -> CommunityPost:
        """Get one saved community post."""


class AdminDecisionRepositoryProtocol(Protocol):
    def save_decision(self, decision: AdminDecision) -> PersistenceWriteResult:
        """Save an admin decision audit record."""

    def list_decisions(self) -> list[AdminDecisionRecord]:
        """List admin decision audit records."""


class VerificationRecordRepositoryProtocol(Protocol):
    def save_verification_request(
        self,
        request: RoleVerificationRequest,
    ) -> PersistenceWriteResult:
        """Save a contributor verification request audit record."""

    def save_verification_decision(
        self,
        decision: RoleVerificationDecision,
    ) -> PersistenceWriteResult:
        """Save a contributor verification decision audit record."""

    def list_verification_records(self) -> list[VerificationRecord]:
        """List contributor verification audit records."""
