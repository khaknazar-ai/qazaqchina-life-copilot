import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.app.admin_auth.models import AuthenticatedAdmin
from backend.app.domain.enums import (
    ModerationStatus,
    RiskLevel,
    SourceType,
    TrustLevel,
    UserScenario,
)
from backend.app.domain.sources import SourceReference
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.checks import detect_prompt_injection
from backend.app.source_corpus.extraction import assess_text, bytes_hash, text_hash
from backend.app.source_corpus.intake import repository_path
from backend.app.source_corpus.models import (
    CorpusPacket,
    CorpusRevision,
    CorpusState,
    PublicationReview,
)
from backend.app.source_corpus.store import CorpusStore, digest

_HIGH_RISK_TOPICS = {
    "documents",
    "visa",
    "registration",
    "housing",
    "work",
    "study",
    "medical",
    "emergency",
    "business",
    "payments",
}
_HIGH_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
}
_HIGH_RISK_SCENARIOS = {
    UserScenario.documents,
    UserScenario.kazakhstan_entry,
    UserScenario.housing,
    UserScenario.work,
    UserScenario.business,
    UserScenario.study,
    UserScenario.medical,
    UserScenario.emergency,
    UserScenario.payments,
}


def _authorized(actor: AuthenticatedAdmin, permission: str) -> None:
    if (
        not actor.token_id
        or not actor.actor_id.strip()
        or permission not in actor.permissions
        or actor.auth_mode in {"disabled", "open", "demo"}
    ):
        raise PermissionError("An authenticated account with this permission is required")


def _safe_note(value: str) -> str:
    value = value.strip()
    sanitized, warnings = redact_sensitive_text(value)
    if (
        not value
        or len(value) > 1000
        or warnings
        or sanitized != value
        or detect_prompt_injection(value)
    ):
        raise ValueError(
            "Review notes must be nonblank and contain no private data or instructions"
        )
    return value


class SourceCorpusService:
    """Explicit publication of reviewed full texts; neither fetching nor review publishes."""

    def __init__(
        self,
        project_root: Path,
        database_path: Path | str = ":memory:",
        *,
        active_reviewer_ids: set[str] | Callable[[], set[str]] | None = None,
        readonly: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.active_reviewer_ids = active_reviewer_ids
        if str(database_path) != ":memory:":
            database_path = repository_path(self.project_root, database_path)
        self.store = CorpusStore(database_path, readonly=readonly)

    def stage(self, packet: CorpusPacket, actor: AuthenticatedAdmin) -> CorpusRevision:
        _authorized(actor, "source_corpus:stage")
        if packet.source_id != f"public-{packet.candidate_id}" or packet.allow_ai_retrieval:
            raise ValueError(
                "Staged packets cannot assign runtime identity or retrieval permission"
            )
        packet_value = packet.model_dump(mode="json")
        with self.store.transaction():
            states = self._states()
            old = states.get(packet.source_id)
            if old and old.revision.packet.model_dump(mode="json") == packet_value:
                return old.revision
            revision_id = f"corpus-{uuid4().hex}"
            revision = CorpusRevision(
                revision_id=revision_id,
                revision_hash=digest({"revision_id": revision_id, "packet": packet_value}),
                packet=packet,
                staged_at=datetime.now(UTC),
            )
            self._append(
                packet.source_id,
                "stage",
                actor,
                {
                    "revision": revision.model_dump(mode="json"),
                    "supersedes_revision_id": old.revision.revision_id if old else None,
                },
            )
            return revision

    def review(
        self, revision_id: str, actor: AuthenticatedAdmin, review: PublicationReview
    ) -> CorpusState:
        _authorized(actor, "source_corpus:review")
        active_reviewers = self._active_reviewers()
        if active_reviewers is not None and actor.actor_id not in active_reviewers:
            raise PermissionError("The reviewer account is not currently active")
        now = datetime.now(UTC)
        with self.store.transaction():
            state = self._require_revision(revision_id)
            self._match(state, review.expected_revision_hash)
            packet = state.revision.packet
            self._verify_artifacts(packet)
            if state.status != "pending":
                raise ValueError("Only the current pending revision can be reviewed")
            if review.expected_text_sha256 != packet.text_sha256:
                raise ValueError("Review text hash is stale")
            if review.answer_passages and not review.answer_passages_complete:
                raise ValueError("Answer passages need explicit conditions-and-exceptions review")
            for passage in review.answer_passages:
                self._verify_passage(packet.text, passage)
            if not all(
                (
                    review.publisher_verified,
                    review.full_text_verified,
                    review.applicability_verified,
                    review.dates_verified,
                    review.reuse_verified,
                )
            ):
                raise ValueError("Publisher, full text, applicability, dates and reuse need review")
            if any(item["actor_id"] == actor.actor_id for item in state.approvals):
                raise ValueError("The same reviewer cannot approve a revision twice")
            high_risk = self._high_risk(packet, review)
            max_age = 90 if high_risk else 365
            if not now < review.expires_at <= now + timedelta(days=max_age):
                raise ValueError(f"Expiry must be in the next {max_age} days")
            review.note = _safe_note(review.note)
            if review.city:
                review.city = _safe_note(review.city)
            if state.approvals and self._review_scope(review) != self._review_scope(
                PublicationReview.model_validate(state.approvals[0]["review"])
            ):
                raise ValueError("Reviewers disagree on applicability, risk or expiry")
            self._append(
                packet.source_id,
                "review",
                actor,
                {
                    "revision_id": revision_id,
                    "review": review.model_dump(mode="json"),
                },
            )
            return self._require_revision(revision_id)

    def publish(
        self, revision_id: str, actor: AuthenticatedAdmin, expected_revision_hash: str
    ) -> CorpusState:
        _authorized(actor, "source_corpus:publish")
        with self.store.transaction():
            state = self._require_revision(revision_id)
            self._match(state, expected_revision_hash)
            self._verify_artifacts(state.revision.packet)
            if state.status != "pending" or not state.approvals:
                raise ValueError("Only a reviewed pending revision can be published")
            review = PublicationReview.model_validate(state.approvals[0]["review"])
            required = 2 if self._high_risk(state.revision.packet, review) else 1
            active_reviewers = self._active_reviewers()
            if active_reviewers is not None and any(
                item["actor_id"] not in active_reviewers for item in state.approvals
            ):
                raise ValueError("A review account is no longer active; obtain a fresh revision")
            if len({item["actor_id"] for item in state.approvals}) < required:
                raise ValueError(f"This source requires {required} independent reviewers")
            if review.expires_at <= datetime.now(UTC):
                raise ValueError("Review approval has expired")
            self._append(
                state.revision.packet.source_id, "publish", actor, {"revision_id": revision_id}
            )
            return self._require_revision(revision_id)

    def revoke(
        self, source_id: str, actor: AuthenticatedAdmin, expected_revision_hash: str, reason: str
    ) -> CorpusState:
        _authorized(actor, "source_corpus:revoke")
        with self.store.transaction():
            state = self._states().get(source_id)
            if not state:
                raise LookupError("Source not found")
            self._match(state, expected_revision_hash)
            self._append(
                source_id,
                "revoke",
                actor,
                {
                    "revision_id": state.revision.revision_id,
                    "reason": _safe_note(reason),
                },
            )
            return self._require_revision(state.revision.revision_id)

    def reset_review(
        self, source_id: str, actor: AuthenticatedAdmin, expected_revision_hash: str, reason: str
    ) -> CorpusRevision:
        """Start independent review again without replacing the preserved material."""
        _authorized(actor, "source_corpus:stage")
        with self.store.transaction():
            old = self._states().get(source_id)
            if old is None:
                raise LookupError("Source not found")
            self._match(old, expected_revision_hash)
            self._verify_artifacts(old.revision.packet)
            revision_id = f"corpus-{uuid4().hex}"
            revision = CorpusRevision(
                revision_id=revision_id,
                revision_hash=digest(
                    {
                        "revision_id": revision_id,
                        "packet": old.revision.packet.model_dump(mode="json"),
                    }
                ),
                packet=old.revision.packet,
                staged_at=datetime.now(UTC),
            )
            self._append(
                source_id,
                "stage",
                actor,
                {
                    "revision": revision.model_dump(mode="json"),
                    "supersedes_revision_id": old.revision.revision_id,
                    "reason": _safe_note(reason),
                },
            )
            return revision

    def list_states(self) -> list[CorpusState]:
        with self.store.transaction():
            return list(self._states().values())

    def history(self, source_id: str) -> list[dict]:
        with self.store.transaction():
            return [event for event in self.store.events() if event["source_id"] == source_id]

    def shadowed_source_ids(self) -> set[str]:
        return {state.revision.packet.source_id for state in self.list_states()}

    def active_sources(self, now: datetime | None = None) -> list[SourceReference]:
        return self.runtime_projection(now)[1]

    def runtime_projection(
        self,
        now: datetime | None = None,
    ) -> tuple[set[str], list[SourceReference]]:
        """Read shadowed IDs and published evidence from the same ledger snapshot."""
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Runtime time must include a timezone")
        with self.store.transaction():
            states = list(self._states().values())
            return (
                {state.revision.packet.source_id for state in states},
                self._project_active_sources(states, now),
            )

    def _project_active_sources(
        self,
        states: list[CorpusState],
        now: datetime,
    ) -> list[SourceReference]:
        result: list[SourceReference] = []
        active_reviewers = self._active_reviewers()
        for state in states:
            if state.status != "approved" or not state.approvals:
                continue
            if active_reviewers is not None and any(
                item["actor_id"] not in active_reviewers for item in state.approvals
            ):
                continue
            packet = state.revision.packet
            try:
                self._verify_artifacts(packet)
            except (OSError, ValueError):
                continue
            review = PublicationReview.model_validate(state.approvals[0]["review"])
            if review.expires_at <= now:
                continue
            reviewed_at = datetime.fromisoformat(state.approvals[-1]["at"])
            result.append(
                SourceReference(
                    source_id=packet.source_id,
                    title=packet.title,
                    source_type=SourceType.official,
                    trust_level=TrustLevel.level_1_official,
                    content=packet.text,
                    reviewed_answer_passages=review.answer_passages,
                    reviewed_answer_passages_complete=review.answer_passages_complete,
                    language=packet.language,
                    url=packet.final_url or packet.requested_url,
                    date_published=packet.publication_date,
                    date_accessed=packet.captured_at.date() if packet.captured_at else None,
                    collected_at=packet.captured_at,
                    reviewed_at=reviewed_at,
                    last_reviewed_at=reviewed_at,
                    expires_at=review.expires_at,
                    content_hash=packet.text_sha256,
                    freshness_note=f"Reviewed corpus revision {state.revision.revision_id}; "
                    f"publisher: {packet.publisher}; scope: {packet.jurisdiction_or_scope}",
                    status_override="published",
                    reviewed_by=",".join(item["actor_id"] for item in state.approvals),
                    scenario=review.scenario,
                    city=review.city,
                    risk_tags=review.risk_tags,
                    moderation_status=ModerationStatus.approved,
                    allow_ai_retrieval=True,
                )
            )
        return result

    def _active_reviewers(self) -> set[str] | None:
        if callable(self.active_reviewer_ids):
            return self.active_reviewer_ids()
        return self.active_reviewer_ids

    def _verify_artifacts(self, packet: CorpusPacket) -> None:
        if packet.status != "pending" or not packet.raw_path or not packet.extracted_path:
            raise ValueError("Complete captured source material is required")
        raw = repository_path(self.project_root, packet.raw_path)
        extraction = repository_path(self.project_root, packet.extracted_path)
        if (
            raw.stat().st_size != packet.raw_bytes
            or bytes_hash(raw.read_bytes()) != packet.raw_sha256
        ):
            raise ValueError("Captured original bytes have changed")
        text = extraction.read_text(encoding="utf-8")
        if text_hash(text) != packet.extracted_sha256:
            raise ValueError("Full extracted text has changed")
        derived, blockers, _ = assess_text(text)
        if blockers or derived != packet.text or text_hash(packet.text) != packet.text_sha256:
            raise ValueError("Derived text safety or content hash does not match")
        if not packet.publisher.strip() or not packet.jurisdiction_or_scope.strip():
            raise ValueError("Publisher and applicability metadata are required")

    @staticmethod
    def _high_risk(packet: CorpusPacket, review: PublicationReview) -> bool:
        return bool(
            {topic.casefold() for topic in packet.topics} & _HIGH_RISK_TOPICS
            or set(review.risk_tags) & _HIGH_RISK_LEVELS
            or review.scenario in _HIGH_RISK_SCENARIOS
        )

    @staticmethod
    def _verify_passage(text: str, passage: str) -> None:
        redacted, warnings = redact_sensitive_text(passage)
        if (
            len(passage) < 12
            or len(passage) > 2400
            or warnings
            or redacted != passage
            or detect_prompt_injection(passage)
        ):
            raise ValueError("Answer passage is unsafe or exceeds the excerpt limit")
        start = text.find(passage)
        if start < 0:
            raise ValueError("Answer passage must be an exact source substring")
        prefix = text[:start]
        suffix = text[start + len(passage) :]
        start_ok = (
            not prefix or prefix.endswith("\n") or bool(re.search(r"[.!?。！？]\s*$", prefix))
        )
        end_ok = (
            not suffix or suffix.startswith("\n") or bool(re.search(r"[.!?。！？]\s*$", passage))
        )
        if not start_ok or not end_ok:
            raise ValueError("Answer passages must preserve whole sentences or complete lines")

    @staticmethod
    def _review_scope(review: PublicationReview) -> dict:
        return review.model_dump(mode="json", exclude={"note"})

    @staticmethod
    def _match(state: CorpusState, expected_hash: str) -> None:
        if state.revision.revision_hash != expected_hash:
            raise ValueError("Corpus revision has changed; reload before deciding")

    def _require_revision(self, revision_id: str) -> CorpusState:
        state = next(
            (
                state
                for state in self._states().values()
                if state.revision.revision_id == revision_id
            ),
            None,
        )
        if state is None:
            raise LookupError("The current corpus revision was not found")
        return state

    def _states(self) -> dict[str, CorpusState]:
        states: dict[str, CorpusState] = {}
        for event in self.store.events():
            value = event["value"]
            source_id = event["source_id"]
            if value["action"] == "stage":
                revision = CorpusRevision.model_validate(value["data"]["revision"])
                if revision.revision_hash != digest(
                    {
                        "revision_id": revision.revision_id,
                        "packet": revision.packet.model_dump(mode="json"),
                    }
                ):
                    raise ValueError("Staged corpus revision hash does not match")
                states[source_id] = CorpusState(
                    revision=revision, status=revision.packet.status, event_count=1
                )
                continue
            state = states.get(source_id)
            if state is None or value["data"]["revision_id"] != state.revision.revision_id:
                raise ValueError("Corpus event references an unavailable revision")
            state.event_count += 1
            if value["action"] == "review":
                state.approvals.append(
                    {
                        "actor_id": value["actor_id"],
                        "at": value["at"],
                        "review": value["data"]["review"],
                    }
                )
            elif value["action"] == "publish":
                state.status = "approved"
            elif value["action"] == "revoke":
                state.status = "revoked"
            else:
                raise ValueError("Unknown corpus event")
        return states

    def _append(self, source_id: str, action: str, actor: AuthenticatedAdmin, data: dict) -> None:
        self.store.append(
            source_id,
            {
                "action": action,
                "actor_id": actor.actor_id,
                "actor_roles": list(actor.roles),
                "actor_permissions": [
                    permission
                    for permission in actor.permissions
                    if permission.startswith("source_corpus:")
                ],
                "actor_token_id": actor.token_id,
                "auth_mode": actor.auth_mode,
                "at": datetime.now(UTC).isoformat(),
                "data": data,
            },
        )

    def close(self) -> None:
        self.store.close()
