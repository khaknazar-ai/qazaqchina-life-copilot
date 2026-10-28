import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.domain.community import CommunityPost
from backend.app.domain.sources import SourceReference


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            raw_line = line.strip()
            if not raw_line:
                raise ValueError(f"Empty JSONL record in {path} at line {line_number}")

            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {exc.msg}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(f"JSONL record in {path} at line {line_number} is not an object")

            records.append(record)

    return records


def load_official_sources(path: Path) -> list[SourceReference]:
    return _load_source_references(path)


def load_curated_guides(path: Path) -> list[SourceReference]:
    return _load_source_references(path)


def load_community_posts(path: Path) -> list[CommunityPost]:
    posts: list[CommunityPost] = []

    for index, record in enumerate(load_jsonl(path), start=1):
        try:
            posts.append(CommunityPost.model_validate(record))
        except ValidationError as exc:
            raise ValueError(f"Invalid community post in {path} at record {index}: {exc}") from exc

    return posts


def _load_source_references(path: Path) -> list[SourceReference]:
    sources: list[SourceReference] = []

    for index, record in enumerate(load_jsonl(path), start=1):
        try:
            sources.append(SourceReference.model_validate(record))
        except ValidationError as exc:
            raise ValueError(
                f"Invalid source reference in {path} at record {index}: {exc}"
            ) from exc

    return sources
