import json
from pathlib import Path

from backend.app.source_candidates.models import RegistryReadySource
from backend.app.source_ingestion.models import (
    SourceIngestionManifest,
    SourceIngestionResult,
)
from backend.app.source_ingestion.validation import (
    registry_ready_to_ingestion_record,
    validate_ingestion_records,
)

DEFAULT_SOURCE_INGESTION_OUTPUT_DIR = Path("reports/generated/source_ingestion")


class SourceIngestionService:
    def build_manifest_from_registry_ready_sources(
        self,
        sources: list[RegistryReadySource],
        target_registry_file: str | None = None,
        dry_run: bool = True,
    ) -> SourceIngestionManifest:
        records = [registry_ready_to_ingestion_record(source) for source in sources]
        issues = validate_ingestion_records(records)
        invalid_candidate_ids = {
            issue.candidate_id
            for issue in issues
            if issue.severity == "error" and issue.candidate_id is not None
        }
        notes = [
            "Dry run only; trusted source registry files were not modified.",
            "Human review is required before any future append to data/sources/*.jsonl.",
        ]
        if not dry_run:
            notes.append("Requested non-dry-run mode was ignored in Phase 35.")
        return SourceIngestionManifest(
            dry_run=True,
            total_records=len(records),
            valid_records=len(records) - len(invalid_candidate_ids),
            invalid_records=len(invalid_candidate_ids),
            records=records,
            issues=issues,
            target_registry_file=target_registry_file,
            notes=notes,
        )

    def write_manifest(
        self,
        manifest: SourceIngestionManifest,
        output_dir: Path | str,
    ) -> SourceIngestionResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        manifest_path = output_path / "source_ingestion_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        summary_path = self.write_ingestion_summary_md(manifest, output_path)

        output_paths = [str(manifest_path), str(summary_path)]
        if manifest.records:
            output_paths.append(str(self.write_registry_ready_jsonl(manifest, output_path)))

        return SourceIngestionResult(
            manifest=manifest,
            output_paths=output_paths,
            registry_modified=False,
        )

    def write_registry_ready_jsonl(
        self,
        manifest: SourceIngestionManifest,
        output_dir: Path | str,
        filename: str = "registry_ready_sources.jsonl",
    ) -> Path:
        path = Path(output_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            for record in manifest.records
        ]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path

    def write_ingestion_summary_md(
        self,
        manifest: SourceIngestionManifest,
        output_dir: Path | str,
    ) -> Path:
        path = Path(output_dir) / "source_ingestion_summary.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_build_summary_markdown(manifest), encoding="utf-8")
        return path


def _build_summary_markdown(manifest: SourceIngestionManifest) -> str:
    lines = [
        "# Source Ingestion Summary",
        "",
        "- dry_run: true",
        "- registry_modified: false",
        f"- target_registry_file: {manifest.target_registry_file or 'unspecified'}",
        f"- total_records: {manifest.total_records}",
        f"- valid_records: {manifest.valid_records}",
        f"- invalid_records: {manifest.invalid_records}",
        "",
        "No data/sources/*.jsonl file was modified.",
        "",
        "## Notes",
    ]
    lines.extend(f"- {note}" for note in manifest.notes)
    lines.extend(["", "## Issues"])
    if not manifest.issues:
        lines.append("- none")
    else:
        for issue in manifest.issues:
            lines.append(
                "- "
                f"{issue.severity} {issue.code}"
                f"{f' ({issue.candidate_id})' if issue.candidate_id else ''}: "
                f"{issue.message}"
            )
    lines.extend(["", "## Records"])
    if not manifest.records:
        lines.append("- none")
    else:
        for record in manifest.records:
            lines.append(f"- {record.source_id}: {record.title} ({record.source_type})")
    return "\n".join(lines) + "\n"
