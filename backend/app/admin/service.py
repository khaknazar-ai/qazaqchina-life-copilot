from hashlib import sha256

from backend.app.admin.models import (
    AdminDecision,
    AdminDecisionAction,
    AdminReviewType,
    CommunityModerationAdminResult,
    RoleVerificationAdminResult,
    SourceGovernanceAdminResult,
)
from backend.app.admin.policies import (
    action_requires_reason,
    admin_action_is_valid_for_review_type,
    safe_ai_retrieval_after_admin_action,
)
from backend.app.domain.community import CommunityPost, ContributorProfile
from backend.app.domain.enums import ModerationStatus, VerificationStatus, VerifiedContributorRole
from backend.app.moderation.service import CommunityModerationService
from backend.app.persistence.base import AdminDecisionRepositoryProtocol
from backend.app.source_candidates.models import (
    RegistryReadySource,
    SourceCandidate,
    SourceCandidateReviewDecision,
    SourceCandidateReviewResult,
)
from backend.app.source_candidates.service import SourceCandidateQueueService
from backend.app.source_ingestion.models import SourceIngestionManifest
from backend.app.source_ingestion.service import SourceIngestionService
from backend.app.source_versioning.models import SourcePublishPreview, SourceVersionRecord
from backend.app.source_versioning.service import SourceVersioningService
from backend.app.tools.policies import infer_domain_from_url
from backend.app.url_fetcher.models import URLFetchRequest
from backend.app.url_fetcher.service import ControlledURLFetcher
from backend.app.verification.models import RoleVerificationDecision
from backend.app.verification.service import ContributorVerificationService


class AdminReviewService:
    def __init__(
        self,
        verification_service: ContributorVerificationService | None = None,
        admin_decision_repository: AdminDecisionRepositoryProtocol | None = None,
        source_candidate_queue_service: SourceCandidateQueueService | None = None,
        source_ingestion_service: SourceIngestionService | None = None,
        source_versioning_service: SourceVersioningService | None = None,
    ) -> None:
        self.verification_service = verification_service or ContributorVerificationService()
        self.admin_decision_repository = admin_decision_repository
        self.source_candidate_queue_service = (
            source_candidate_queue_service or SourceCandidateQueueService()
        )
        self.source_ingestion_service = source_ingestion_service or SourceIngestionService()
        self.source_versioning_service = source_versioning_service or SourceVersioningService()

    def review_community_post(
        self,
        post: CommunityPost,
        decision: AdminDecision,
    ) -> CommunityModerationAdminResult:
        if decision.target_id != post.post_id:
            raise ValueError("Community review target does not match post.")
        self._raise_if_invalid(decision, expected_review_type=AdminReviewType.community_post)
        if (
            decision.action == AdminDecisionAction.approve
            and CommunityModerationService().moderate_post(post).findings
        ):
            raise ValueError("post_requires_safety_revision")
        self._save_decision(decision)
        changed = decision.action != AdminDecisionAction.no_action
        updated_post = post

        if decision.action == AdminDecisionAction.approve:
            updated_post = post.model_copy(
                update={
                    "moderation_status": ModerationStatus.approved,
                    "allow_ai_retrieval": safe_ai_retrieval_after_admin_action(
                        decision.action.value,
                        ModerationStatus.approved,
                    )
                    and post.ai_retrieval_consent is True,
                }
            )
        elif decision.action == AdminDecisionAction.reject:
            updated_post = post.model_copy(
                update={
                    "moderation_status": ModerationStatus.rejected,
                    "allow_ai_retrieval": False,
                }
            )
        elif decision.action == AdminDecisionAction.flag:
            updated_post = post.model_copy(
                update={
                    "moderation_status": ModerationStatus.flagged,
                    "allow_ai_retrieval": False,
                }
            )
        elif decision.action == AdminDecisionAction.request_changes:
            updated_post = post.model_copy(
                update={
                    "moderation_status": ModerationStatus.needs_review,
                    "allow_ai_retrieval": False,
                }
            )

        return CommunityModerationAdminResult(
            post=updated_post,
            decision=decision,
            message=_changed_message("Community post review", changed),
        )

    def review_role_verification(
        self,
        profile: ContributorProfile,
        decision: AdminDecision,
        requested_role: VerifiedContributorRole | None = None,
    ) -> RoleVerificationAdminResult:
        if decision.target_id != profile.contributor_id:
            raise ValueError("Verification target does not match contributor.")
        self._raise_if_invalid(decision, expected_review_type=AdminReviewType.role_verification)
        self._save_decision(decision)

        if decision.action == AdminDecisionAction.no_action:
            return RoleVerificationAdminResult(
                contributor=profile,
                decision=decision,
                message="Role verification review left unchanged.",
            )

        if decision.action == AdminDecisionAction.request_changes:
            updated_profile = profile.model_copy(
                update={"verification_status": VerificationStatus.verification_requested}
            )
            return RoleVerificationAdminResult(
                contributor=updated_profile,
                decision=decision,
                message="Role verification changes requested.",
            )

        verification_decision = _role_verification_decision(
            decision,
            requested_role=requested_role or profile.verified_role,
        )
        verification_result = self.verification_service.apply_decision(
            profile,
            verification_decision,
        )
        return RoleVerificationAdminResult(
            contributor=verification_result.contributor,
            decision=decision,
            message=verification_result.message,
        )

    def review_source_governance(
        self,
        decision: AdminDecision,
        recommended_actions: list[str] | None = None,
    ) -> SourceGovernanceAdminResult:
        if decision.review_type not in {
            AdminReviewType.source_conflict,
            AdminReviewType.citation_issue,
            AdminReviewType.source_registry_record,
        }:
            raise ValueError("Source governance review requires source governance review type.")
        self._raise_if_invalid(decision)
        self._save_decision(decision)
        action_messages = {
            AdminDecisionAction.approve: "Admin accepted current source governance state.",
            AdminDecisionAction.flag: "Admin flagged source governance for high-risk review.",
            AdminDecisionAction.request_changes: "Admin requested answer or source revision.",
            AdminDecisionAction.no_action: "Source governance review left unchanged.",
            AdminDecisionAction.reject: "Admin rejected the source registry record.",
        }
        return SourceGovernanceAdminResult(
            decision=decision,
            message=action_messages[decision.action],
            recommended_actions=recommended_actions or [],
        )

    def add_source_candidate(
        self,
        title: str,
        url: str,
        snippet: str,
        source_type_guess: str | None = None,
        trust_guess: str | None = None,
        language: str | None = None,
        country: str = "CN",
        city: str | None = None,
        scenario: str | None = None,
        risk_level: str | None = None,
        official_domain_hint: bool = False,
        warnings: list[str] | None = None,
    ) -> SourceCandidate:
        candidate = SourceCandidate(
            candidate_id=_source_candidate_id(url=url, title=title),
            title=title,
            url=url,
            snippet=snippet,
            domain=infer_domain_from_url(url),
            source_type_guess=source_type_guess,
            trust_guess=trust_guess,
            language=language,
            country=country,
            city=city,
            scenario=scenario,
            risk_level=risk_level,
            official_domain_hint=official_domain_hint,
            requires_review=True,
            status="pending",
            warnings=list(
                dict.fromkeys(
                    [
                        *(warnings or []),
                        "admin_auth_not_implemented_demo_only",
                        "Created by local/demo admin API; manual review required.",
                    ]
                )
            ),
            discovered_by="admin_api_manual_candidate",
        )
        return self.source_candidate_queue_service.add_candidate(candidate)

    def preview_source_url(
        self,
        url: str,
        scenario: str | None = None,
        risk_level: str | None = None,
        language: str | None = None,
        city: str | None = None,
        allow_network: bool = False,
        confirm_network: bool = False,
    ) -> dict:
        warnings: list[str] = []
        network_allowed = allow_network and confirm_network
        if allow_network and not confirm_network:
            warnings.append(
                "Network requested without confirmation; refused network and used no-fetch mode."
            )
        fetcher = ControlledURLFetcher()
        result = fetcher.fetch_to_source_candidate(
            URLFetchRequest(
                url=url,
                scenario=scenario,
                risk_level=risk_level,
                language=language,
                city=city,
                allow_network=network_allowed,
            )
        )
        candidate = None
        candidate_created = False
        if result.candidate is not None:
            candidate = self.source_candidate_queue_service.add_candidate(result.candidate)
            candidate_created = True
        combined_warnings = list(
            dict.fromkeys(
                [
                    *warnings,
                    *result.warnings,
                    "admin_auth_not_implemented_demo_only",
                    "Fetched or submitted pages are source candidates only, not trusted evidence.",
                    "Trusted registry files were not modified.",
                ]
            )
        )
        return {
            "used_network": result.fetch_result.used_network,
            "fetched": result.fetch_result.fetched,
            "candidate_created": candidate_created,
            "candidate": candidate.model_dump(mode="json") if candidate is not None else None,
            "fetch_result": result.fetch_result.model_dump(mode="json"),
            "warnings": combined_warnings,
            "message": (
                "Pending source candidate created; manual review is required before trust."
                if candidate_created
                else "URL preview did not create a candidate; review warnings before retry."
            ),
        }

    def list_source_candidates(self, status: str | None = None) -> list[SourceCandidate]:
        return self.source_candidate_queue_service.list_candidates(status=status)

    def get_source_candidate(self, candidate_id: str) -> SourceCandidate:
        return self.source_candidate_queue_service.get_candidate(candidate_id)

    def review_source_candidate(
        self,
        candidate_id: str,
        action: str,
        reviewer_id: str,
        reason: str,
        assigned_source_type: str | None = None,
        assigned_trust_level: str | None = None,
        allow_retrieval: bool = False,
        freshness_note: str | None = None,
        notes: str | None = None,
    ) -> SourceCandidateReviewResult:
        decision = SourceCandidateReviewDecision(
            candidate_id=candidate_id,
            action=action,
            reviewer_id=reviewer_id,
            reason=reason,
            assigned_source_type=assigned_source_type,
            assigned_trust_level=assigned_trust_level,
            allow_retrieval=allow_retrieval,
            freshness_note=freshness_note,
            notes=notes,
        )
        return self.source_candidate_queue_service.review_candidate(decision)

    def registry_ready_sources(self) -> list[RegistryReadySource]:
        return self.source_candidate_queue_service.approved_registry_ready_sources()

    def prepare_source_ingestion_dry_run(
        self,
        target_registry_file: str | None = "data/sources/official_sources.jsonl",
    ) -> SourceIngestionManifest:
        return self.source_ingestion_service.build_manifest_from_registry_ready_sources(
            self.registry_ready_sources(),
            target_registry_file=target_registry_file,
            dry_run=True,
        )

    def create_source_version_from_candidate(
        self,
        candidate_id: str,
        reviewer_id: str | None = None,
        reason: str | None = None,
    ) -> SourceVersionRecord:
        candidate = self.get_source_candidate(candidate_id)
        return self.source_versioning_service.create_draft_from_candidate(
            candidate,
            reviewer_id=reviewer_id,
            review_reason=reason,
        )

    def list_source_versions(self, status: str | None = None) -> list[SourceVersionRecord]:
        return self.source_versioning_service.list_versions(status=status)

    def source_publish_preview(self) -> SourcePublishPreview:
        return self.source_versioning_service.build_publish_preview()

    def reset_source_candidates_for_tests(self) -> None:
        self.source_candidate_queue_service = SourceCandidateQueueService()
        self.source_versioning_service = SourceVersioningService()

    def validate_decision(self, decision: AdminDecision) -> list[str]:
        warnings: list[str] = []
        if not admin_action_is_valid_for_review_type(
            decision.action.value,
            decision.review_type.value,
        ):
            warnings.append(
                f"Action {decision.action.value} is invalid for {decision.review_type.value}."
            )
        if action_requires_reason(decision.action.value, decision.review_type.value):
            if not decision.reason or not decision.reason.strip():
                warnings.append(f"Action {decision.action.value} requires a reason.")
        if decision.action == AdminDecisionAction.approve and not decision.admin_id.strip():
            warnings.append("Approve action requires admin_id.")
        return warnings

    def _raise_if_invalid(
        self,
        decision: AdminDecision,
        expected_review_type: AdminReviewType | None = None,
    ) -> None:
        if expected_review_type is not None and decision.review_type != expected_review_type:
            raise ValueError(
                "Expected review_type "
                f"{expected_review_type.value}, got {decision.review_type.value}."
            )
        warnings = self.validate_decision(decision)
        if warnings:
            raise ValueError("; ".join(warnings))

    def _save_decision(self, decision: AdminDecision) -> None:
        if self.admin_decision_repository:
            self.admin_decision_repository.save_decision(decision)


def _role_verification_decision(
    decision: AdminDecision,
    requested_role: VerifiedContributorRole,
) -> RoleVerificationDecision:
    return RoleVerificationDecision(
        contributor_id=decision.target_id,
        requested_role=requested_role,
        decision=_verification_decision_action(decision.action),
        decided_by_admin_id=decision.admin_id,
        reason=decision.reason,
    )


def _verification_decision_action(action: AdminDecisionAction) -> str:
    return {
        AdminDecisionAction.approve: "approved",
        AdminDecisionAction.reject: "rejected",
        AdminDecisionAction.revoke: "revoked",
        AdminDecisionAction.expire: "expired",
    }[action]


def _changed_message(subject: str, changed: bool) -> str:
    if changed:
        return f"{subject} applied."
    return f"{subject} left unchanged."


def _source_candidate_id(url: str, title: str) -> str:
    candidate_key = f"{url}|{title}".encode()
    return f"SRC-CAND-{sha256(candidate_key).hexdigest()[:12].upper()}"
