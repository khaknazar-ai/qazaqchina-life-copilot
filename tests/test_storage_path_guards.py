from pathlib import Path

import pytest

from backend.app.real_eval.review_service import EvaluationReviewService
from backend.app.vector_index.persistent import PersistentVectorCache, VectorCacheError


def test_evaluation_review_rejects_hidden_storage_directory() -> None:
    repo = Path(__file__).resolve().parents[1]

    with pytest.raises(ValueError, match="local SQLite ledger"):
        EvaluationReviewService(
            repo,
            ".private/reviews.sqlite3",
            load_materials=lambda: ({}, {}),
            active_reviewer_keys=lambda: set(),
        )


def test_vector_cache_rejects_hidden_storage_directory() -> None:
    repo = Path(__file__).resolve().parents[1]

    with pytest.raises(VectorCacheError, match="vector_cache_path_invalid"):
        PersistentVectorCache(
            repo / ".private" / "vectors.sqlite3",
            namespace="test",
            dimensions=4,
        )
