"""Atomic whole-file workspace commits; unrelated JSONL stores keep their policy.

One live WorkspaceService owns the file. Replacement is the commit point after
the candidate file is flushed/fsynced. This does not fsync the parent directory
or promise power-loss or multi-process durability. Orphan temporary files are
uncommitted and never replayed or automatically removed on open.
"""

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Iterable

from pydantic import ValidationError

from backend.app.api_utils.identity_boundary import is_persistent_owner
from backend.app.persistence.errors import PersistenceSerializationError
from backend.app.persistence.jsonl_store import JsonlRecordStore
from backend.app.persistence.models import StoredRecord
from backend.app.workspace.models import WorkspaceRecord

RECORD_TYPE = "citizen_workspace"
logger = logging.getLogger(__name__)


class WorkspaceRecoveryRequired(PersistenceSerializationError):
    """Retains byte-level diagnostics without exposing record content or owners."""

    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__("workspace_recovery_required: " + json.dumps(diagnostic, sort_keys=True))


class WorkspaceCommitUncertain(OSError):
    """Publication could not be reconciled; this instance must not serve stale state."""


class WorkspaceSnapshotStore(JsonlRecordStore):
    """Existing record envelope, strict workspace reads and atomic publication."""

    blocked = False

    def _bytes(self) -> bytes:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return b""

    def load(self) -> list[WorkspaceRecord]:
        with self._lock:
            raw = self._bytes()
            states = []
            offset = 0
            for number, line in enumerate(raw.splitlines(keepends=True), 1):
                reason = "unterminated_record" if not line.endswith(b"\n") else "invalid_record"
                try:
                    if reason == "unterminated_record":
                        raise ValueError(reason)
                    record = StoredRecord.model_validate_json(line)
                    state = WorkspaceRecord.model_validate(record.payload)
                    if (record.record_type != RECORD_TYPE or record.record_id != state.owner
                            or not is_persistent_owner(state.owner)):
                        raise ValueError("invalid_workspace_envelope")
                except (ValidationError, ValueError):
                    diagnostic = {
                        "reason": reason, "line": number, "byte_offset": offset,
                        "line_bytes": len(line), "line_sha256": hashlib.sha256(line).hexdigest(),
                        "file_bytes": len(raw), "file_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                    logger.error("Workspace storage blocked: %s", diagnostic)
                    # Pydantic's exception may include private input values.
                    raise WorkspaceRecoveryRequired(diagnostic) from None
                states.append(state)
                offset += len(line)
            self._digest = hashlib.sha256(raw).digest()
            return states

    def publish(self, states: Iterable[WorkspaceRecord]) -> None:
        """Publish every owner plus retry keys together, with no append tail.

        A replace error is reconciled against exact candidate bytes. If the
        replacement actually completed, it is committed despite the lost ack.
        Otherwise callers receive failure and keep their previous memory state.
        """
        data = b"".join(
            (StoredRecord(record_id=state.owner, record_type=RECORD_TYPE,
                          payload=state.model_dump(mode="json")).model_dump_json() + "\n").encode()
            for state in states if is_persistent_owner(state.owner)
        )
        digest = hashlib.sha256(data).digest()
        with self._lock:
            current = self._bytes()
            if hashlib.sha256(current).digest() != self._digest:
                # Never compact away corruption or a different writer's data.
                diagnostic = {"reason": "file_changed_since_open",
                              "file_bytes": len(current),
                              "file_sha256": hashlib.sha256(current).hexdigest()}
                logger.error("Workspace storage blocked: %s", diagnostic)
                self.blocked = True
                raise WorkspaceRecoveryRequired(diagnostic)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=self.path.parent, prefix="workspace-", suffix=".tmp",
                    delete=False,
                ) as output:
                    temporary = output.name
                    if output.write(data) != len(data):
                        raise OSError("Incomplete workspace snapshot write")
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    os.replace(temporary, self.path)
                except OSError as exc:
                    try:
                        observed = self._bytes()
                    except OSError:
                        self.blocked = True
                        raise WorkspaceCommitUncertain("workspace_save_unconfirmed") from None
                    if observed != data:
                        if hashlib.sha256(observed).digest() != self._digest:
                            self.blocked = True
                            raise WorkspaceCommitUncertain("workspace_save_unconfirmed") from None
                        raise exc
                # No fallible disk operation after this commit point.
                temporary = None
                self._digest = digest
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        # Only this attempt's temp is eligible; failure must not
                        # hide the write outcome. Opening never cleans or replays it.
                        pass
