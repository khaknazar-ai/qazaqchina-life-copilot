"""Content-addressed local vector cache; current source snapshots govern reuse."""

import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from backend.app.embeddings.qwen import valid_vector
from backend.app.source_index.models import SourceChunk


class VectorCacheError(ValueError):
    pass


def index_namespace(*, provider: str, model: str, dimensions: int, base_url: str) -> str:
    return sha256(
        json.dumps([provider, model, dimensions, base_url], separators=(",", ":")).encode()
    ).hexdigest()


class PersistentVectorCache:
    def __init__(self, path: Path, *, namespace: str, dimensions: int) -> None:
        repo = Path(__file__).resolve().parents[3]
        target = path.resolve()
        if (
            not target.is_relative_to(repo)
            or target.suffix not in {".sqlite3", ".db"}
            or any(
                part.startswith(".") for part in target.relative_to(repo).parts
            )
        ):
            raise VectorCacheError("vector_cache_path_invalid")
        self.path, self.namespace, self.dimensions = target, namespace, dimensions

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute(
            "CREATE TABLE IF NOT EXISTS retrieval_vector_manifest "
            "(namespace TEXT PRIMARY KEY, digest TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS retrieval_vector_cache "
            "(namespace TEXT NOT NULL, chunk_id TEXT NOT NULL, source_id TEXT NOT NULL, "
            "source_fingerprint TEXT NOT NULL, text_hash TEXT NOT NULL, vector TEXT NOT NULL, "
            "PRIMARY KEY(namespace, chunk_id))"
        )
        return db

    def prepare(self, chunks: list[SourceChunk], fingerprints: dict[str, str]) -> str:
        expected = {
            chunk.chunk_id: (chunk.source_id, fingerprints[chunk.source_id], chunk.text_hash)
            for chunk in chunks
        }
        if len(expected) != len(chunks):
            raise VectorCacheError("vector_cache_duplicate_chunk")
        digest = sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                # A configuration change invalidates all old vectors. The cache is
                # deliberately single-model; rows never mix dimensions or providers.
                db.execute(
                    "DELETE FROM retrieval_vector_cache WHERE namespace != ?", (self.namespace,)
                )
                db.execute(
                    "DELETE FROM retrieval_vector_manifest WHERE namespace != ?", (self.namespace,)
                )
                rows = db.execute(
                    "SELECT chunk_id,source_id,source_fingerprint,text_hash "
                    "FROM retrieval_vector_cache WHERE namespace=?",
                    (self.namespace,),
                ).fetchall()
                obsolete = [
                    (self.namespace, chunk_id)
                    for chunk_id, source_id, fingerprint, text_hash in rows
                    if expected.get(chunk_id) != (source_id, fingerprint, text_hash)
                ]
                db.executemany(
                    "DELETE FROM retrieval_vector_cache WHERE namespace=? AND chunk_id=?",
                    obsolete,
                )
                db.execute(
                    "INSERT INTO retrieval_vector_manifest VALUES (?,?) "
                    "ON CONFLICT(namespace) DO UPDATE SET digest=excluded.digest",
                    (self.namespace, digest),
                )
        except (OSError, sqlite3.Error) as exc:
            raise VectorCacheError("vector_cache_unavailable") from exc
        return digest

    def read(
        self, chunks: list[SourceChunk], fingerprints: dict[str, str], digest: str
    ) -> dict[str, list[float]]:
        try:
            with closing(self._connect()) as db:
                self._check_manifest(db, digest)
                rows = {
                    chunk_id: (source_id, fingerprint, text_hash, vector)
                    for chunk_id, source_id, fingerprint, text_hash, vector in db.execute(
                        "SELECT chunk_id,source_id,source_fingerprint,text_hash,vector "
                        "FROM retrieval_vector_cache WHERE namespace=?",
                        (self.namespace,),
                    )
                }
        except (OSError, sqlite3.Error) as exc:
            raise VectorCacheError("vector_cache_unavailable") from exc
        found: dict[str, list[float]] = {}
        for chunk in chunks:
            row = rows.get(chunk.chunk_id)
            if row is None:
                continue
            if row[:3] != (chunk.source_id, fingerprints[chunk.source_id], chunk.text_hash):
                raise VectorCacheError("vector_cache_snapshot_changed")
            try:
                vector = json.loads(row[3])
            except (ValueError, TypeError) as exc:
                self._discard(chunk.chunk_id, digest)
                raise VectorCacheError("vector_cache_corrupt") from exc
            if not valid_vector(vector, self.dimensions):
                self._discard(chunk.chunk_id, digest)
                raise VectorCacheError("vector_cache_corrupt")
            found[chunk.chunk_id] = vector
        return found

    def _discard(self, chunk_id: str, digest: str) -> None:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                self._check_manifest(db, digest)
                db.execute(
                    "DELETE FROM retrieval_vector_cache WHERE namespace=? AND chunk_id=?",
                    (self.namespace, chunk_id),
                )
        except (OSError, sqlite3.Error) as exc:
            raise VectorCacheError("vector_cache_unavailable") from exc

    def put(
        self,
        chunks: list[SourceChunk],
        vectors: list[list[float]],
        fingerprints: dict[str, str],
        digest: str,
    ) -> None:
        if len(chunks) != len(vectors) or any(
            not valid_vector(vector, self.dimensions) for vector in vectors
        ):
            raise VectorCacheError("vector_cache_vector_invalid")
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                self._check_manifest(db, digest)
                db.executemany(
                    "INSERT INTO retrieval_vector_cache VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(namespace,chunk_id) DO UPDATE SET "
                    "source_id=excluded.source_id,source_fingerprint=excluded.source_fingerprint,"
                    "text_hash=excluded.text_hash,vector=excluded.vector",
                    [
                        (
                            self.namespace,
                            chunk.chunk_id,
                            chunk.source_id,
                            fingerprints[chunk.source_id],
                            chunk.text_hash,
                            json.dumps(vector, separators=(",", ":"), allow_nan=False),
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ],
                )
        except (OSError, sqlite3.Error) as exc:
            raise VectorCacheError("vector_cache_unavailable") from exc

    def check_current(self, digest: str) -> None:
        try:
            with closing(self._connect()) as db:
                self._check_manifest(db, digest)
        except (OSError, sqlite3.Error) as exc:
            raise VectorCacheError("vector_cache_unavailable") from exc

    def _check_manifest(self, db: sqlite3.Connection, digest: str) -> None:
        row = db.execute(
            "SELECT digest FROM retrieval_vector_manifest WHERE namespace=?",
            (self.namespace,),
        ).fetchone()
        if row != (digest,):
            raise VectorCacheError("vector_cache_snapshot_changed")
