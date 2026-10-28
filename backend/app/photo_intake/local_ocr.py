import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_OCR_LANGUAGES = ("chi_sim", "eng", "rus", "kaz")
_LANGUAGE_CODE = re.compile(r"^[a-z][a-z0-9_]{1,15}$")


class LocalOCREngineStatus(BaseModel):
    engine: str
    available: bool
    executable_path: str | None = None
    package_importable: bool = False
    version: str | None = None
    available_languages: list[str] = Field(default_factory=list)
    missing_languages: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LocalOCRReadinessReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available: bool
    default_provider: str = "fake"
    engines: list[LocalOCREngineStatus]
    safe_to_use_by_default: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def parse_language_codes(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    items = value.split("+") if isinstance(value, str) else list(value)
    codes = tuple(
        dict.fromkeys(
            str(item).strip().casefold() for item in items if str(item).strip()
        )
    )
    if not codes or any(not _LANGUAGE_CODE.fullmatch(code) for code in codes):
        return ()
    return codes


def check_local_ocr_readiness(
    tesseract_cmd: str = "tesseract",
    required_languages: str | tuple[str, ...] | list[str] = DEFAULT_OCR_LANGUAGES,
    tessdata_dir: str | None = None,
) -> LocalOCRReadinessReport:
    """Check Tesseract and its language data without recognizing an image."""
    required = parse_language_codes(required_languages)
    executable = _resolve_executable(tesseract_cmd)
    warnings: list[str] = ["No OCR was executed by readiness checks."]
    available_languages: list[str] = []
    version = None
    missing_languages = list(required)
    language_check_succeeded = False

    if not required:
        warnings.append("The configured Tesseract language list is invalid.")
    if not executable:
        warnings.append("Tesseract executable was not found.")
    elif required:
        try:
            version_result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                shell=False,
            )
            version_lines = (version_result.stdout or version_result.stderr).splitlines()
            version = version_lines[0].strip() if version_lines else None
            command = [executable, "--list-langs"]
            if tessdata_dir:
                command.extend(["--tessdata-dir", tessdata_dir])
            language_result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                shell=False,
            )
            output = "\n".join([language_result.stdout or "", language_result.stderr or ""])
            language_check_succeeded = language_result.returncode == 0
            available_languages = sorted(
                {
                    line.strip().casefold()
                    for line in output.splitlines()
                    if _LANGUAGE_CODE.fullmatch(line.strip().casefold())
                }
            )
            missing_languages = [code for code in required if code not in available_languages]
            if language_result.returncode != 0:
                warnings.append("Tesseract could not list its language data.")
            elif missing_languages:
                warnings.append("Required Tesseract language data is missing.")
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("Tesseract did not respond to its readiness check.")

    available = bool(executable and required and language_check_succeeded and not missing_languages)
    if available:
        warnings.append("Tesseract and the configured language data are ready for local OCR.")
    engines = [
        LocalOCREngineStatus(
            engine="tesseract",
            available=available,
            executable_path=executable,
            version=version,
            available_languages=available_languages,
            missing_languages=missing_languages,
            warnings=[warning for warning in warnings if "Tesseract" in warning],
        )
    ]
    return LocalOCRReadinessReport(
        available=available,
        engines=engines,
        warnings=warnings,
        recommendations=_recommendations(available),
    )


def local_ocr_report_to_jsonable(report: LocalOCRReadinessReport) -> dict:
    return report.model_dump(mode="json")


def local_ocr_report_to_markdown(report: LocalOCRReadinessReport) -> str:
    lines = [
        "# Local OCR Readiness Report",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Available: {report.available}",
        f"- Default provider: {report.default_provider}",
        f"- Safe to use by default: {report.safe_to_use_by_default}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "- No OCR was executed.",
        "",
        "## Detected Engines",
        "",
        "| Engine | Ready | Version | Languages |",
        "| --- | --- | --- | --- |",
    ]
    for engine in report.engines:
        lines.append(
            f"| {engine.engine} | {engine.available} | {engine.version or ''} | "
            f"{', '.join(engine.available_languages)} |"
        )
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {recommendation}" for recommendation in report.recommendations)
    return "\n".join(lines) + "\n"


def _resolve_executable(command: str) -> str | None:
    value = str(command or "").strip()
    if not value:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    return shutil.which(value)


def _recommendations(available: bool) -> list[str]:
    recommendations = [
        "The local provider runs Tesseract on the backend machine and does not send the image "
        "to a cloud provider.",
        "Review extracted text before using it; OCR output is user-provided input, not trusted "
        "evidence.",
        "Keep fake/manual OCR as the default unless LOCAL_OCR_ENABLED is explicitly enabled.",
    ]
    if not available:
        recommendations.append(
            "Install Tesseract and its configured language data, then set LOCAL_OCR_ENABLED=true."
        )
    return recommendations
