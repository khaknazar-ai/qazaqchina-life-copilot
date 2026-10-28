from uuid import uuid4

from backend.app.admin.models import AdminDecision
from backend.app.domain.cases import UserCase
from backend.app.domain.community import CommunityPost
from backend.app.persistence.jsonl_store import JsonlRecordStore
from backend.app.persistence.models import (
    AdminDecisionRecord,
    PersistenceWriteResult,
    VerificationRecord,
    utc_now,
)
from backend.app.verification.models import (
    RoleVerificationDecision,
    RoleVerificationRequest,
)

CASE_RECORD_TYPE = "case"
COMMUNITY_POST_RECORD_TYPE = "community_post"
ADMIN_DECISION_RECORD_TYPE = "admin_decision"
VERIFICATION_RECORD_TYPE = "verification_record"


class JsonlCaseRepository:
    def __init__(self, store: JsonlRecordStore) -> None:
        self.store = store

    def save_case(self, case: UserCase) -> PersistenceWriteResult:
        return self.store.append(
            record_type=CASE_RECORD_TYPE,
            payload=case.model_dump(mode="json"),
            record_id=case.case_id,
        )

    def list_cases(self) -> list[UserCase]:
        latest = {record.record_id: record for record in self.store.list_records(CASE_RECORD_TYPE)}
        return [UserCase.model_validate(record.payload) for record in latest.values()]

    def get_case(self, case_id: str) -> UserCase:
        return UserCase.model_validate(self.store.get(case_id).payload)


class JsonlCommunityPostRepository:
    def __init__(self, store: JsonlRecordStore) -> None:
        self.store = store

    def save_post(self, post: CommunityPost) -> PersistenceWriteResult:
        return self.store.append(
            record_type=COMMUNITY_POST_RECORD_TYPE,
            payload=post.model_dump(mode="json"),
            record_id=post.post_id,
        )

    def list_posts(self) -> list[CommunityPost]:
        latest = {
            record.record_id: record
            for record in self.store.list_records(COMMUNITY_POST_RECORD_TYPE)
        }
        return [CommunityPost.model_validate(record.payload) for record in latest.values()]

    def get_post(self, post_id: str) -> CommunityPost:
        return CommunityPost.model_validate(self.store.get(post_id).payload)


class JsonlAdminDecisionRepository:
    def __init__(self, store: JsonlRecordStore) -> None:
        self.store = store

    def save_decision(self, decision: AdminDecision) -> PersistenceWriteResult:
        record = AdminDecisionRecord(
            decision_id=f"ADMIN-DEC-{uuid4().hex[:12].upper()}",
            review_type=decision.review_type.value,
            action=decision.action.value,
            admin_id=decision.admin_id,
            target_id=decision.target_id,
            reason=decision.reason,
            notes=decision.notes,
            created_at=utc_now(),
        )
        return self.store.append(
            record_type=ADMIN_DECISION_RECORD_TYPE,
            payload=record.model_dump(mode="json"),
            record_id=record.decision_id,
        )

    def list_decisions(self) -> list[AdminDecisionRecord]:
        return [
            AdminDecisionRecord.model_validate(record.payload)
            for record in self.store.list_records(ADMIN_DECISION_RECORD_TYPE)
        ]


class JsonlVerificationRecordRepository:
    def __init__(self, store: JsonlRecordStore) -> None:
        self.store = store

    def save_verification_request(
        self,
        request: RoleVerificationRequest,
    ) -> PersistenceWriteResult:
        record = VerificationRecord(
            record_id=f"VERIF-REQ-{uuid4().hex[:12].upper()}",
            contributor_id=request.contributor_id,
            requested_role=request.requested_role.value,
            decision=None,
            admin_id=None,
            reason=request.evidence_summary,
            created_at=utc_now(),
        )
        return self._save_record(record)

    def save_verification_decision(
        self,
        decision: RoleVerificationDecision,
    ) -> PersistenceWriteResult:
        record = VerificationRecord(
            record_id=f"VERIF-DEC-{uuid4().hex[:12].upper()}",
            contributor_id=decision.contributor_id,
            requested_role=decision.requested_role.value,
            decision=decision.decision,
            admin_id=decision.decided_by_admin_id,
            reason=decision.reason,
            created_at=utc_now(),
        )
        return self._save_record(record)

    def list_verification_records(self) -> list[VerificationRecord]:
        return [
            VerificationRecord.model_validate(record.payload)
            for record in self.store.list_records(VERIFICATION_RECORD_TYPE)
        ]

    def _save_record(self, record: VerificationRecord) -> PersistenceWriteResult:
        return self.store.append(
            record_type=VERIFICATION_RECORD_TYPE,
            payload=record.model_dump(mode="json"),
            record_id=record.record_id,
        )
