import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.domain.enums import LanguageCode
from backend.app.source_corpus.extraction import (
    MAX_RAW_BYTES,
    assess_text,
    bytes_hash,
    extract_html,
    text_hash,
)
from backend.app.source_corpus.models import CorpusPacket


def repository_path(project_root: Path, path: str | Path) -> Path:
    root = project_root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Corpus paths must remain inside the repository")
    return target


def load_prepared_packets(
    project_root: Path, output_dir: str | Path = "data/local/source_corpus/packets"
) -> list[CorpusPacket]:
    """Read the newest server-prepared report, never a path from an API request."""
    output = repository_path(project_root, output_dir)
    reports = sorted(output.glob("review_packets-*.local.json"))
    if not reports:
        return []
    report_path = repository_path(project_root, reports[-1])
    if report_path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError("Prepared corpus report exceeds the review limit")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("runtime_import_allowed") is not False or len(report["packets"]) > 500:
        raise ValueError("Prepared corpus report is not a pending intake")
    packets = [CorpusPacket.model_validate(value) for value in report["packets"]]
    if len({packet.candidate_id for packet in packets}) != len(packets):
        raise ValueError("Prepared corpus report contains duplicate identifiers")
    return packets


def prepare_packets(
    project_root: Path,
    inventory_path: str | Path,
    capture_manifest_path: str | Path | None = None,
    *,
    output_dir: str | Path = "data/local/source_corpus/packets",
) -> list[CorpusPacket]:
    inventory = json.loads(
        repository_path(project_root, inventory_path).read_text(encoding="utf-8")
    )
    manifest = (
        json.loads(repository_path(project_root, capture_manifest_path).read_text(encoding="utf-8"))
        if capture_manifest_path is not None
        else {"capture_records": []}
    )
    records = {item["candidate_id"]: item for item in manifest["capture_records"]}
    candidates = inventory["sources"]
    ids = [item["candidate_id"] for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate corpus candidate identifiers")
    output = repository_path(project_root, output_dir)
    output.mkdir(parents=True, exist_ok=True)
    packets = [
        prepare_packet(project_root, item, records.get(item["candidate_id"]), output)
        for item in candidates
    ]
    return packets


def prepare_packet(
    project_root: Path,
    candidate: dict,
    capture: dict | None,
    output: Path,
) -> CorpusPacket:
    candidate_id = candidate["candidate_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", candidate_id):
        raise ValueError("Invalid candidate identifier")
    findings: list[str] = []
    text = ""
    method = None
    extracted_path = None
    raw_path = None
    raw_sha256 = None
    raw_bytes = 0
    extracted_sha256 = None
    capture = capture or {}
    try:
        if not capture.get("raw_path"):
            findings.append("original_not_captured")
        else:
            raw = repository_path(project_root, capture["raw_path"])
            raw_path = str(raw.relative_to(project_root.resolve())).replace("\\", "/")
            if raw.stat().st_size > MAX_RAW_BYTES:
                findings.append("original_exceeds_byte_limit")
            else:
                data = raw.read_bytes()
                raw_bytes = len(data)
                raw_sha256 = bytes_hash(data)
                if raw_sha256 != capture.get("sha256") or raw_bytes != capture.get("byte_count"):
                    findings.append("original_capture_hash_or_size_mismatch")
                if data.startswith(b"%PDF-"):
                    text, method = _extract_pdf(project_root, raw, capture, raw_sha256)
                elif "application/json" in capture.get("content_type", ""):
                    from backend.app.source_corpus.public_json import extract_public_json

                    text, method = extract_public_json(data, candidate)
                elif "html" in capture.get("content_type", ""):
                    text, method = extract_html(data, capture.get("content_type"))
                elif capture.get("content_type", "").startswith("text/plain"):
                    text, method = data.decode("utf-8"), "plain_text"
                else:
                    findings.append("unsupported_document_type")
        if capture.get("requested_url") != candidate["url"]:
            findings.append("capture_url_does_not_match_candidate")
        if capture.get("status") == "application_shell_only":
            findings.append("body_missing_or_application_shell")
        if capture.get("http_status") != 200:
            findings.append("capture_not_http_200")
        if capture.get("final_url") and (
            urlsplit(candidate["url"]).hostname != urlsplit(capture["final_url"]).hostname
        ):
            findings.append("publisher_redirect_requires_separate_candidate")
    except (OSError, ValueError, UnicodeError, ImportError) as exc:
        findings.append(f"extraction_failed:{type(exc).__name__}")
    derived, blockers, warnings = assess_text(text)
    findings.extend(blockers)
    original_text_hash = text_hash(text)
    if text:
        extraction_file = output / f"{candidate_id}-{original_text_hash[:16]}.extracted.txt"
        # Immutable artifacts: never silently replace a prior extraction.
        if extraction_file.exists():
            if extraction_file.read_text(encoding="utf-8") != text:
                raise ValueError("Existing extraction differs from its identity")
        else:
            extraction_file.write_text(text, encoding="utf-8")
        extracted_path = str(extraction_file.relative_to(project_root.resolve())).replace("\\", "/")
        extracted_sha256 = original_text_hash
    languages = candidate.get("language", [])
    language = languages[0] if len(languages) == 1 else "unknown"
    packet = CorpusPacket(
        candidate_id=candidate_id,
        source_id=f"public-{candidate_id}",
        title=candidate["title"],
        publisher=candidate.get("publisher", ""),
        requested_url=candidate["url"],
        final_url=capture.get("final_url"),
        jurisdiction_or_scope=candidate.get("jurisdiction_or_scope", ""),
        language=LanguageCode(language),
        topics=candidate.get("topics", []),
        publication_date=candidate.get("publication_date"),
        publication_date_basis=candidate.get("publication_date_basis"),
        captured_at=datetime.fromisoformat(capture["captured_at"])
        if capture.get("captured_at")
        else None,
        raw_path=raw_path,
        raw_sha256=raw_sha256,
        raw_bytes=raw_bytes,
        extracted_path=extracted_path,
        extracted_sha256=extracted_sha256,
        text=derived,
        text_sha256=text_hash(derived),
        extraction_method=method,
        status="blocked" if findings else "pending",
        findings=list(dict.fromkeys(findings + warnings)),
        rights_status=candidate.get("rights_status"),
    )
    return packet


def _extract_pdf(project_root: Path, raw: Path, capture: dict, raw_hash: str) -> tuple[str, str]:
    # Optional parser can be supplied by a separate read-only bundled-runtime
    # extraction. Its attestation must bind all page texts to these exact bytes.
    manifest_path = capture.get("pdf_extraction_manifest")
    if not manifest_path:
        directory = repository_path(project_root, "data/raw/real_source_corpus/pdf_extractions")
        for path in sorted(directory.glob("*.json"))[:100]:
            path = repository_path(project_root, path)
            if path.stat().st_size > 400_000:
                continue
            extraction = json.loads(path.read_text(encoding="utf-8"))
            if extraction.get("raw_sha256") == raw_hash:
                manifest_path = path
                break
    if manifest_path:
        extraction = json.loads(repository_path(project_root, manifest_path).read_text("utf-8"))
        text = repository_path(project_root, extraction["text_path"]).read_text(encoding="utf-8")
        if (
            extraction["raw_sha256"] != raw_hash
            or extraction["text_sha256"] != text_hash(text)
            or extraction["pages_extracted"] != extraction["page_count"]
            or extraction["page_count"] < 1
        ):
            raise ValueError("PDF extraction is incomplete or belongs to different bytes")
        return text, "pdf_all_pages"
    from pypdf import PdfReader

    reader = PdfReader(raw)
    if reader.is_encrypted or len(reader.pages) > 300:
        raise ValueError("Encrypted or oversized PDF requires manual extraction")
    pages = [page.extract_text() or "" for page in reader.pages]
    if any(not page.strip() for page in pages):
        raise ValueError("PDF contains image-only pages; OCR review is required")
    return "\n\n".join(pages), "pdf_all_pages"
