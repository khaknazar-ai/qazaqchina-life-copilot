from typing import TYPE_CHECKING, Any

from backend.app.source_conflicts.errors import (
    ConflictError,
    ConflictIntegrityError,
    ConflictNotFoundError,
    ConflictPermissionError,
    ConflictRevisionError,
    ConflictValidationError,
)
from backend.app.source_conflicts.models import (
    AppliedResolution,
    ConditionalBranch,
    ConflictCase,
    ConflictEvent,
    EvidenceCondition,
    IntegrityReport,
    ResolutionApplicability,
    ResolutionEvaluation,
    ResolutionProposal,
    SourceSnapshot,
)

if TYPE_CHECKING:
    from backend.app.source_conflicts.service import ConflictResolutionService, snapshot_hash


def __getattr__(name: str) -> Any:
    if name in {"ConflictResolutionService", "snapshot_hash"}:
        from backend.app.source_conflicts import service

        value = getattr(service, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AppliedResolution",
    "ConflictCase",
    "ConflictError",
    "ConflictEvent",
    "ConditionalBranch",
    "EvidenceCondition",
    "ConflictIntegrityError",
    "ConflictNotFoundError",
    "ConflictPermissionError",
    "ConflictResolutionService",
    "ConflictRevisionError",
    "ConflictValidationError",
    "IntegrityReport",
    "ResolutionEvaluation",
    "ResolutionApplicability",
    "ResolutionProposal",
    "SourceSnapshot",
    "snapshot_hash",
]
