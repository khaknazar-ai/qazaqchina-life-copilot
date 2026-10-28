import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT_DIR = Path("reports/generated/source_review_answer_constraints")
REQUIRED_METADATA_FIELDS = [
    "has_source_review_constraints",
    "source_review_constraint",
    "required_official_verification_warning",
    "prohibited_claim_types",
    "citizen_visible_source_review_disclosure_allowed",
]
FORBIDDEN_UI_MARKERS = [
    "configs/source_review",
    "official_source_candidate_intake",
    "official_source_review_evidence",
    "reviewer packet",
    "publish preview package",
    "source candidates under review",
]


def inspect_miniprogram_source_review_ui(
    project_root: Path | str = PROJECT_ROOT,
) -> dict[str, Any]:
    root = Path(project_root)
    miniprogram_path = _find_miniprogram_path(root)
    chat_files = _chat_ui_files(miniprogram_path)
    chat_text = "\n".join(path.read_text(encoding="utf-8") for path in chat_files)
    chat_page_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in chat_files
        if "pages/chat" in path.as_posix().replace("\\", "/")
    )
    chat_wxml = (miniprogram_path / "pages" / "chat" / "index.wxml").read_text(
        encoding="utf-8"
    )
    docs_text = _docs_text(root)

    metadata_references = {
        field: field in chat_text for field in REQUIRED_METADATA_FIELDS
    }
    source_review_warning_rendered = (
        "view.sourceReviewWarning.show" in chat_text
        and "Official verification required" in chat_text
        and 'wx:for="{{turn.warnings}}"' in chat_wxml
    )
    required_warning_supported = (
        metadata_references["required_official_verification_warning"]
        and "view.sourceReviewWarning.message" in chat_text
        and 'wx:for="{{turn.warnings}}"' in chat_wxml
    )
    low_risk_overwarning_guard_present = (
        "shouldShowSourceReviewWarning" in chat_text
        and "has_source_review_constraints === true" in chat_text
        and "value.source_review_constraint" in chat_text
        and "value.required_official_verification_warning" in chat_text
    )
    unpublished_candidates_hidden = (
        "answerView.unreviewedCandidates" not in chat_wxml
        and not _contains_forbidden_marker(chat_page_text)
        and "unpublished candidates must not be cited" in docs_text.casefold()
    )

    return {
        "miniprogram_path": str(miniprogram_path.relative_to(root)),
        "chat_ui_file_count": len(chat_files),
        "chat_ui_files": [str(path.relative_to(root)) for path in chat_files],
        "metadata_references": metadata_references,
        "source_review_warning_rendered": source_review_warning_rendered,
        "required_warning_supported": required_warning_supported,
        "unpublished_candidates_hidden": unpublished_candidates_hidden,
        "low_risk_overwarning_guard_present": low_risk_overwarning_guard_present,
        "ready_for_closed_beta": False,
        "ready_for_public_launch": False,
        "used_network": False,
        "used_external_provider": False,
        "notes": [
            "Mini Program UI must not cite unpublished source candidates.",
            "Source review metadata is a caution signal, not source citation support.",
            "Low-risk chat should not show a source-review warning banner.",
            "No source publishing or registry write occurred.",
        ],
    }


def write_miniprogram_source_review_ui_reports(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> tuple[dict[str, Any], list[Path]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report = inspect_miniprogram_source_review_ui(PROJECT_ROOT)
    json_path = output_path / "miniprogram_source_review_ui_report.json"
    markdown_path = output_path / "miniprogram_source_review_ui_report.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        miniprogram_source_review_ui_report_to_markdown(report),
        encoding="utf-8",
    )
    return report, [json_path, markdown_path]


def miniprogram_source_review_ui_report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Mini Program Source Review UI Report",
        "",
        "## Executive Decision",
        "",
        f"- Chat UI file count: {report['chat_ui_file_count']}",
        (
            "- Source review warning rendered: "
            f"{report['source_review_warning_rendered']}"
        ),
        f"- Required warning supported: {report['required_warning_supported']}",
        f"- Unpublished candidates hidden: {report['unpublished_candidates_hidden']}",
        (
            "- Low-risk overwarning guard present: "
            f"{report['low_risk_overwarning_guard_present']}"
        ),
        f"- Ready for closed beta: {report['ready_for_closed_beta']}",
        f"- Ready for public launch: {report['ready_for_public_launch']}",
        f"- Used network: {report['used_network']}",
        f"- Used external provider: {report['used_external_provider']}",
        "",
        "Mini Program UI must not cite unpublished source candidates.",
        "",
        "## Metadata References",
        "",
    ]
    lines.extend(
        f"- {field}: {present}"
        for field, present in report["metadata_references"].items()
    )
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Mini Program source-review warning UI without network."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    report, output_paths = write_miniprogram_source_review_ui_reports(args.output_dir)

    print("Mini Program Source Review UI Inspection")
    print(f"chat_ui_file_count={report['chat_ui_file_count']}")
    print(
        "source_review_warning_rendered="
        f"{str(report['source_review_warning_rendered']).lower()}"
    )
    print(
        "required_warning_supported="
        f"{str(report['required_warning_supported']).lower()}"
    )
    print(
        "unpublished_candidates_hidden="
        f"{str(report['unpublished_candidates_hidden']).lower()}"
    )
    print(
        "low_risk_overwarning_guard_present="
        f"{str(report['low_risk_overwarning_guard_present']).lower()}"
    )
    print("ready_for_closed_beta=false")
    print("ready_for_public_launch=false")
    print("used_network=false")
    print("used_external_provider=false")
    print("Mini Program UI must not cite unpublished source candidates.")
    print("Output paths:")
    for output_path in output_paths:
        print(f"- {output_path}")
    return 0


def _find_miniprogram_path(root: Path) -> Path:
    candidates = [
        root / "frontend" / "wechat-miniprogram",
        root / "miniprogram",
        root / "wechat-miniprogram",
        root / "frontend" / "miniprogram",
    ]
    for candidate in candidates:
        if (candidate / "app.json").exists():
            return candidate
    raise FileNotFoundError("Mini Program app.json was not found.")


def _chat_ui_files(miniprogram_path: Path) -> list[Path]:
    paths = [
        miniprogram_path / "pages" / "chat" / "index.js",
        miniprogram_path / "pages" / "chat" / "index.wxml",
        miniprogram_path / "pages" / "chat" / "index.wxss",
        miniprogram_path / "utils" / "answerSections.js",
    ]
    return [path for path in paths if path.exists()]


def _docs_text(root: Path) -> str:
    paths = [
        root / "docs" / "miniprogram_source_review_chat_constraints.md",
        root / "docs" / "source_review_chat_constraints.md",
        root / "docs" / "source_review_answer_constraints.md",
    ]
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in paths
        if path.exists()
    )


def _contains_forbidden_marker(text: str) -> bool:
    normalized = text.casefold()
    return any(marker in normalized for marker in FORBIDDEN_UI_MARKERS)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
