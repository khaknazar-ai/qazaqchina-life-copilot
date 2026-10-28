"""Attributed evaluation approval over unchanged captured originals."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.app.admin_auth.models import AuthenticatedAdmin
from backend.app.admin_auth.permissions import PERMISSION_SOURCE_CORPUS_REVIEW
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.checks import detect_prompt_injection
from backend.app.real_eval.dataset import RealMaterialCase
from backend.app.real_eval.review_models import (
    AnnotationReceipt,
    EvaluationApproval,
    EvaluationLabels,
    EvaluationReviewEvent,
)
from backend.app.real_eval.review_store import EvaluationReviewStore
from backend.app.source_corpus.extraction import assess_text, bytes_hash, text_hash
from backend.app.source_corpus.intake import repository_path
from backend.app.source_corpus.models import CorpusPacket
from backend.app.source_corpus.store import digest

Materials = Callable[[], tuple[list[RealMaterialCase], list[CorpusPacket]]]
ReviewerKeys = Callable[[], set[tuple[str, str]]]
_LABEL_FIELDS = {
    "expected_behavior",
    "scenario",
    "risk_level",
    "required_conditions",
    "forbidden_claims",
    "expected_conflict",
    "source_applicability",
}
_REVIEW_FIELDS = {"annotation_status", "reviewed_by", "reviewed_at", "annotation_review_id"}


def case_hash(case: RealMaterialCase) -> str:
    return digest(case.model_dump(mode="json", exclude=_REVIEW_FIELDS))


def case_labels(case: RealMaterialCase) -> EvaluationLabels:
    values = case.model_dump(mode="json", include=_LABEL_FIELDS)
    values["applicability"] = values.pop("source_applicability", None)
    return EvaluationLabels.model_validate(values)


def _safe_text(value: str) -> str:
    value = value.strip()
    safe, findings = redact_sensitive_text(value)
    if not value or findings or safe != value or detect_prompt_injection(value):
        raise ValueError(
            "Evaluation notes and labels must not contain private data or instructions"
        )
    return value


class EvaluationReviewService:
    def __init__(
        self,
        project_root: Path,
        database_path: Path | str,
        *,
        load_materials: Materials,
        active_reviewer_keys: ReviewerKeys,
        readonly: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.load_materials = load_materials
        self.active_reviewer_keys = active_reviewer_keys
        path = database_path
        if str(path) != ":memory:":
            path = repository_path(self.project_root, path)
            if Path(path).suffix != ".sqlite3" or any(
                part.startswith(".") for part in Path(path).parts
            ):
                raise ValueError("Evaluation review storage must use a local SQLite ledger")
        self.store = EvaluationReviewStore(path, read_only=readonly)

    def _materials(self) -> tuple[dict[str, RealMaterialCase], dict[str, CorpusPacket]]:
        cases, packets = self.load_materials()
        if len(cases) > 500 or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("Evaluation case identifiers must be bounded and unique")
        if len({p.source_id for p in packets}) != len(packets):
            raise ValueError("Evaluation source identities must be unique")
        return {c.case_id: c for c in cases}, {p.source_id: p for p in packets}

    def _current(
        self,
        case_id: str,
    ) -> tuple[RealMaterialCase, dict[str, CorpusPacket]]:
        cases, packets = self._materials()
        if case_id not in cases:
            raise LookupError("Evaluation case was not found")
        return cases[case_id], packets

    def _evidence_hash(self, case: RealMaterialCase, packets: dict[str, CorpusPacket]) -> str:
        if not case.evidence:
            raise ValueError("Captured evaluation evidence is required")
        snapshots = []
        for evidence in case.evidence:
            packet = packets.get(evidence.source_id)
            if packet is None or packet.status != "pending":
                raise ValueError("Captured evaluation material is missing or blocked")
            if packet.text_sha256 != evidence.text_sha256 or evidence.quote not in packet.text:
                raise ValueError("Evaluation source hash or exact evidence quote has changed")
            self._verify_original(packet)
            snapshots.append(
                {
                    "evidence": evidence.model_dump(mode="json"),
                    "packet_hash": digest(packet.model_dump(mode="json")),
                }
            )
        return digest(snapshots)

    def _verify_original(self, packet: CorpusPacket) -> None:
        if not packet.raw_path or not packet.extracted_path:
            raise ValueError("Captured originals and complete extracted text are required")
        raw = repository_path(self.project_root, packet.raw_path)
        extraction = repository_path(self.project_root, packet.extracted_path)
        if not 0 < raw.stat().st_size <= 8 * 1024 * 1024 or raw.stat().st_size != packet.raw_bytes:
            raise ValueError("Captured original size has changed")
        if bytes_hash(raw.read_bytes()) != packet.raw_sha256:
            raise ValueError("Captured original bytes have changed")
        if extraction.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Extracted evaluation text exceeds its review limit")
        full_text = extraction.read_text(encoding="utf-8")
        if text_hash(full_text) != packet.extracted_sha256:
            raise ValueError("Complete extracted text has changed")
        derived, blockers, _ = assess_text(full_text)
        if blockers or derived != packet.text or text_hash(derived) != packet.text_sha256:
            raise ValueError("Captured evaluation text does not match its preserved original")

    def _latest(self) -> dict[str, EvaluationReviewEvent]:
        latest = {}
        for row in self.store.events():
            event = EvaluationReviewEvent.model_validate(row["value"])
            if row["case_id"] != event.case_id or event.at.tzinfo is None:
                raise ValueError("Evaluation review identity or timestamp is invalid")
            previous = latest.get(event.case_id)
            if event.previous_review_id != (previous.review_id if previous else None):
                raise ValueError("Evaluation review revision chain is invalid")
            if event.action == "approve":
                if (
                    event.approval is None
                    or event.case_snapshot is None
                    or (case_hash(event.case_snapshot) != event.approval.expected_case_hash)
                    or event.labels_hash
                    != digest(
                        event.approval.labels.model_dump(mode="json"),
                    )
                ):
                    raise ValueError("Evaluation labels do not match their review hash")
            elif (
                event.approval is not None
                or previous is None
                or event.review_id != previous.review_id
            ):
                raise ValueError("Evaluation revocation references an unavailable review")
            latest[event.case_id] = event
        return latest

    def _authorized(self, actor: AuthenticatedAdmin) -> None:
        if (
            not actor.token_id
            or PERMISSION_SOURCE_CORPUS_REVIEW not in actor.permissions
            or actor.auth_mode in {"disabled", "open", "demo"}
            or (actor.actor_id, actor.token_id) not in self.active_reviewer_keys()
        ):
            raise PermissionError("An active authenticated evaluation reviewer is required")

    def approve(
        self,
        case_id: str,
        approval: EvaluationApproval,
        actor: AuthenticatedAdmin,
    ) -> dict:
        self._authorized(actor)
        approval = EvaluationApproval.model_validate(approval.model_dump(mode="python"))
        case, packets = self._current(case_id)
        if redact_sensitive_text(case.question)[1]:
            raise ValueError("Evaluation questions must not contain private identifiers")
        evidence_hash = self._evidence_hash(case, packets)
        if approval.expected_case_hash != case_hash(case) or (
            approval.expected_evidence_hash != evidence_hash
        ):
            raise ValueError("Evaluation case or evidence changed; reload before reviewing")
        if not all(
            (approval.originals_checked, approval.question_checked, approval.conditions_checked)
        ):
            raise ValueError(
                "Question, original evidence and applicability require explicit review"
            )
        now = datetime.now(UTC)
        if not now < approval.expires_at <= now + timedelta(days=90):
            raise ValueError("Evaluation review expiry must be within the next 90 days")
        approval.note = _safe_text(approval.note)
        for values in (approval.labels.required_conditions, approval.labels.forbidden_claims):
            for index, value in enumerate(values):
                values[index] = _safe_text(value)
        with self.store.transaction():
            latest = self._latest().get(case_id)
            if approval.expected_review_id != (latest.review_id if latest else None):
                raise ValueError("Evaluation review changed; reload before deciding")
            self._append(
                case_id,
                actor,
                EvaluationReviewEvent(
                    action="approve",
                    case_id=case_id,
                    review_id="eval-review-" + uuid4().hex,
                    actor_id=actor.actor_id,
                    actor_token_id=actor.token_id,
                    actor_permissions=[PERMISSION_SOURCE_CORPUS_REVIEW],
                    auth_mode=actor.auth_mode,
                    at=now,
                    approval=approval,
                    labels_hash=digest(approval.labels.model_dump(mode="json")),
                    previous_review_id=latest.review_id if latest else None,
                    case_snapshot=case,
                ),
            )
        return self.case_record(case_id)

    def revoke(
        self,
        case_id: str,
        expected_review_id: str,
        reason: str,
        actor: AuthenticatedAdmin,
    ) -> dict:
        self._authorized(actor)
        self._current(case_id)
        reason = _safe_text(reason)
        with self.store.transaction():
            latest = self._latest().get(case_id)
            if latest is None:
                raise LookupError("Evaluation review was not found")
            if latest.review_id != expected_review_id or latest.action != "approve":
                raise ValueError("Evaluation review changed or is already revoked")
            self._append(
                case_id,
                actor,
                EvaluationReviewEvent(
                    action="revoke",
                    case_id=case_id,
                    review_id=latest.review_id,
                    actor_id=actor.actor_id,
                    actor_token_id=actor.token_id,
                    actor_permissions=[PERMISSION_SOURCE_CORPUS_REVIEW],
                    auth_mode=actor.auth_mode,
                    at=datetime.now(UTC),
                    reason=reason,
                    previous_review_id=latest.review_id,
                ),
            )
        return self.case_record(case_id)

    def _append(
        self, case_id: str, actor: AuthenticatedAdmin, event: EvaluationReviewEvent
    ) -> None:
        self._authorized(actor)
        self.store.append(case_id, event.model_dump(mode="json"))

    def _receipt(
        self,
        case: RealMaterialCase,
        packets: dict[str, CorpusPacket],
        event: EvaluationReviewEvent | None,
    ) -> tuple[AnnotationReceipt | None, str]:
        if event is None:
            return None, "pending"
        if event.action != "approve":
            return None, "revoked"
        approval = event.approval
        if approval is None or approval.expires_at <= datetime.now(UTC):
            return None, "expired"
        if not all(
            (approval.originals_checked, approval.question_checked, approval.conditions_checked)
        ):
            return None, "invalid_review_record"
        if event.at > datetime.now(UTC) or event.auth_mode in {"disabled", "open", "demo"}:
            return None, "invalid_reviewer_record"
        if (event.actor_id, event.actor_token_id) not in self.active_reviewer_keys():
            return None, "reviewer_inactive"
        if (
            PERMISSION_SOURCE_CORPUS_REVIEW not in event.actor_permissions
            or not event.actor_token_id
        ):
            return None, "invalid_reviewer_record"
        try:
            evidence_hash = self._evidence_hash(case, packets)
        except (ValueError, OSError, KeyError, TypeError):
            return None, "evidence_changed_or_unavailable"
        if approval.expected_case_hash != case_hash(case) or (
            approval.expected_evidence_hash != evidence_hash
        ):
            return None, "case_or_evidence_changed"
        return AnnotationReceipt(
            review_id=event.review_id,
            case_hash=approval.expected_case_hash,
            evidence_hash=evidence_hash,
            labels_hash=event.labels_hash,
            reviewer_id=event.actor_id,
            reviewed_at=event.at,
            expires_at=approval.expires_at,
        ), "approved"

    def case_record(self, case_id: str) -> dict:
        case, packets = self._current(case_id)
        with self.store.transaction():
            event = self._latest().get(case_id)
            receipt, status = self._receipt(case, packets, event)
        try:
            evidence_hash = self._evidence_hash(case, packets)
        except (ValueError, OSError, KeyError, TypeError):
            evidence_hash = None
        return {
            "case": case.model_dump(mode="json"),
            "case_hash": case_hash(case),
            "evidence_hash": evidence_hash,
            "review_status": status,
            "review_id": event.review_id if event else None,
            "approved_annotation": receipt.model_dump(mode="json") if receipt else None,
            "labels": event.approval.labels.model_dump(mode="json")
            if event and event.action == "approve"
            else case_labels(case).model_dump(mode="json"),
            "note": event.approval.note
            if event and event.approval
            else event.reason
            if event
            else "",
            "source_publication_is_separate": True,
            "human_qualification_verified": False,
        }

    def list_records(self) -> list[dict]:
        cases, _ = self._materials()
        return [self.case_record(case_id) for case_id in cases]

    def history(self, case_id: str) -> list[dict]:
        self._current(case_id)
        with self.store.transaction():
            self._latest()
            return [
                {key: value for key, value in event["value"].items() if key != "actor_token_id"}
                for event in self.store.events()
                if event["case_id"] == case_id
            ]

    def project_reviewed_cases(self, cases: list[RealMaterialCase]) -> list[RealMaterialCase]:
        current, packets = self._materials()
        with self.store.transaction():
            latest = self._latest()
            result = []
            for case in cases:
                base = current.get(case.case_id)
                event = latest.get(case.case_id)
                receipt, _ = self._receipt(base, packets, event) if base else (None, "missing")
                if base and case_hash(case) != case_hash(base):
                    receipt = None
                if receipt is None:
                    result.append(
                        case.model_copy(
                            update={
                                "annotation_status": "pending",
                                "reviewed_by": None,
                                "reviewed_at": None,
                                "annotation_review_id": None,
                            }
                        )
                    )
                    continue
                values = event.approval.labels.model_dump()
                values["source_applicability"] = values.pop("applicability")
                result.append(
                    RealMaterialCase.model_validate(
                        {
                            **base.model_dump(),
                            **values,
                            "annotation_status": "reviewed",
                            "reviewed_by": receipt.reviewer_id,
                            "reviewed_at": receipt.reviewed_at,
                            "annotation_review_id": receipt.review_id,
                        }
                    )
                )
        return result

    def annotation_errors(
        self, cases: list[RealMaterialCase], packets: list[CorpusPacket]
    ) -> list[str]:
        current, originals = self._materials()
        supplied = {packet.source_id: packet for packet in packets}
        errors = []
        with self.store.transaction():
            latest = self._latest()
            for case in cases:
                base = current.get(case.case_id)
                event = latest.get(case.case_id)
                receipt, status = (
                    self._receipt(base, originals, event) if base else (None, "missing")
                )
                valid = bool(receipt)
                if valid:
                    valid = (
                        digest(case.model_dump(mode="json", exclude=_LABEL_FIELDS | _REVIEW_FIELDS))
                        == digest(
                            base.model_dump(mode="json", exclude=_LABEL_FIELDS | _REVIEW_FIELDS)
                        )
                        and digest(case_labels(case).model_dump(mode="json")) == receipt.labels_hash
                        and case.annotation_review_id == receipt.review_id
                        and all(
                            evidence.source_id in supplied
                            and digest(
                                supplied[evidence.source_id].model_dump(mode="json"),
                            )
                            == digest(originals[evidence.source_id].model_dump(mode="json"))
                            for evidence in case.evidence
                        )
                    )
                if not valid:
                    errors.append(
                        f"{case.case_id}: human annotation requires current authenticated "
                        f"ledger approval ({status if receipt is None else 'changed_labels'})"
                    )
        return errors

    def material(self, case_id: str, source_id: str) -> CorpusPacket:
        case, packets = self._current(case_id)
        if source_id not in {e.source_id for e in case.evidence} or source_id not in packets:
            raise LookupError("Evaluation evidence was not found")
        self._verify_original(packets[source_id])
        return packets[source_id]

    def close(self) -> None:
        self.store.close()
