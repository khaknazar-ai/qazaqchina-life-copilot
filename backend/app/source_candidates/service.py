from typing import Any

from backend.app.persistence.base import RecordStoreProtocol
from backend.app.persistence.errors import RecordNotFoundError
from backend.app.source_candidates.export import candidate_to_registry_ready_source
from backend.app.source_candidates.models import (
    RegistryReadySource,
    SourceCandidate,
    SourceCandidateReviewDecision,
    SourceCandidateReviewResult,
    utc_now,
)
from backend.app.source_candidates.policies import (
    candidate_from_web_search_candidate,
    validate_review_decision,
)
from backend.app.tools.models import WebSearchCandidate

SOURCE_CANDIDATE_RECORD_TYPE = "source_candidate"

_BLOCKING_WARNING_PREFIXES = (
    "Review decision candidate_id does not match candidate.",
    "Review decision requires reviewer_id.",
    "Review decision requires reason.",
    "Approve action requires assigned_source_type.",
    "Approve action requires assigned_trust_level.",
    "Retrieval permission requires assigned source_type and trust_level.",
    "High-risk approval requires reason.",
    "High-risk approval requires freshness_note.",
    "Community, blog, forum, or social candidate assigned official source_type.",
)


class SourceCandidateQueueService:
    def __init__(self, repository: RecordStoreProtocol | None = None) -> None:
        self.repository = repository
        self._candidates: dict[str, SourceCandidate] = {}
        self._load_candidates()

    def add_candidate(self, candidate: SourceCandidate) -> SourceCandidate:
        stored = candidate.model_copy(
            update={
                "warnings": _unique(candidate.warnings),
                "review_notes": _unique(candidate.review_notes),
                "updated_at": candidate.updated_at or utc_now(),
            }
        )
        existing = self._candidates.get(stored.candidate_id)
        if existing is not None and existing.status != "pending":
            return existing
        self._candidates[stored.candidate_id] = stored
        self._save_candidate(stored)
        return stored

    def add_candidates(self, candidates: list[SourceCandidate]) -> list[SourceCandidate]:
        return [self.add_candidate(candidate) for candidate in candidates]

    def add_from_web_candidates(
        self,
        candidates: list[WebSearchCandidate],
        scenario: str | None = None,
        risk_level: str | None = None,
    ) -> list[SourceCandidate]:
        return self.add_candidates(
            [
                candidate_from_web_search_candidate(
                    candidate,
                    scenario=scenario,
                    risk_level=risk_level,
                )
                for candidate in candidates
            ]
        )

    def list_candidates(self, status: str | None = None) -> list[SourceCandidate]:
        candidates = list(self._candidates.values())
        if status is None:
            return candidates
        return [candidate for candidate in candidates if candidate.status == status]

    def get_candidate(self, candidate_id: str) -> SourceCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise RecordNotFoundError(f"Source candidate '{candidate_id}' was not found.") from exc

    def review_candidate(
        self,
        decision: SourceCandidateReviewDecision,
    ) -> SourceCandidateReviewResult:
        candidate = self.get_candidate(decision.candidate_id)
        warnings = validate_review_decision(candidate, decision)
        blocking_warnings = _blocking_warnings(warnings)
        now = utc_now()
        note_values = [
            *candidate.review_notes,
            f"{decision.action} by {decision.reviewer_id}: {decision.reason}",
        ]
        if decision.notes:
            note_values.append(decision.notes)
        review_notes = _unique(note_values)
        combined_warnings = _unique([*candidate.warnings, *warnings])

        if decision.action == "approve" and not blocking_warnings:
            updated_candidate = candidate.model_copy(
                update={
                    "status": "approved",
                    "requires_review": False,
                    "assigned_source_type": decision.assigned_source_type,
                    "assigned_trust_level": decision.assigned_trust_level,
                    "allow_retrieval": decision.allow_retrieval,
                    "freshness_note": decision.freshness_note,
                    "reviewed_by": decision.reviewer_id,
                    "reviewed_at": now,
                    "updated_at": now,
                    "warnings": combined_warnings,
                    "review_notes": review_notes,
                }
            )
        elif decision.action == "reject":
            updated_candidate = candidate.model_copy(
                update={
                    "status": "rejected",
                    "requires_review": False,
                    "allow_retrieval": False,
                    "reviewed_by": decision.reviewer_id,
                    "reviewed_at": now,
                    "updated_at": now,
                    "warnings": combined_warnings,
                    "review_notes": review_notes,
                }
            )
        else:
            updated_candidate = candidate.model_copy(
                update={
                    "status": "needs_review",
                    "requires_review": True,
                    "allow_retrieval": False,
                    "reviewed_by": decision.reviewer_id,
                    "reviewed_at": now,
                    "updated_at": now,
                    "warnings": combined_warnings,
                    "review_notes": review_notes,
                }
            )

        changed = updated_candidate != candidate
        self._candidates[updated_candidate.candidate_id] = updated_candidate
        self._save_candidate(updated_candidate)
        return SourceCandidateReviewResult(
            candidate=updated_candidate,
            decision=decision,
            changed=changed,
            warnings=warnings,
        )

    def approved_registry_ready_sources(self) -> list[RegistryReadySource]:
        sources: list[RegistryReadySource] = []
        for candidate in self.list_candidates(status="approved"):
            try:
                sources.append(candidate_to_registry_ready_source(candidate))
            except ValueError:
                continue
        return sources

    def _load_candidates(self) -> None:
        if self.repository is None:
            return
        for record in self.repository.list_records(SOURCE_CANDIDATE_RECORD_TYPE):
            candidate = SourceCandidate.model_validate(record.payload)
            self._candidates[candidate.candidate_id] = candidate

    def _save_candidate(self, candidate: SourceCandidate) -> None:
        if self.repository is None:
            return
        self.repository.append(
            record_type=SOURCE_CANDIDATE_RECORD_TYPE,
            payload=candidate.model_dump(mode="json"),
            record_id=candidate.candidate_id,
        )


def _blocking_warnings(warnings: list[str]) -> list[str]:
    return [
        warning
        for warning in warnings
        if any(warning.startswith(prefix) for prefix in _BLOCKING_WARNING_PREFIXES)
    ]


def _unique(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
