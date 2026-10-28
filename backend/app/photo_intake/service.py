from backend.app.cloud_ai.client import CloudAIError
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.photo_intake.models import (
    PhotoIntakeReport,
    PhotoIntakeRequest,
    PhotoIntakeResult,
    PhotoValidationResult,
)
from backend.app.photo_intake.ocr import FakeOCRProvider, OCRProvider, create_ocr_provider
from backend.app.photo_intake.validation import decode_base64_image, validate_image_bytes

PRIVACY_WARNINGS = [
    "Photos may contain personal documents, phone numbers, addresses, medical, visa, "
    "or payment information.",
    "Do not upload sensitive documents unless it is necessary for your current task.",
    "Extracted text is user-provided input and is not trusted evidence.",
]

SAFETY_WARNINGS = [
    "OCR or manual transcription text must be verified against official or curated sources "
    "before acting.",
    "Do not cite extracted photo text as trusted evidence.",
]


class PhotoIntakeService:
    def __init__(self, ocr_provider: OCRProvider | None = None) -> None:
        self.ocr_provider = ocr_provider or create_ocr_provider("fake")

    def preview_photo(self, request: PhotoIntakeRequest) -> PhotoIntakeResult:
        try:
            image_bytes = decode_base64_image(request.image_base64)
            validation = validate_image_bytes(
                image_bytes,
                content_type=request.content_type,
            )
        except ValueError as exc:
            return PhotoIntakeResult(
                accepted=False,
                validation=PhotoValidationResult(
                    valid=False,
                    errors=[str(exc)],
                ),
                privacy_warnings=list(PRIVACY_WARNINGS),
                safety_warnings=list(SAFETY_WARNINGS),
                not_trusted_evidence=True,
            )

        if not validation.valid:
            return PhotoIntakeResult(
                accepted=False,
                validation=validation,
                privacy_warnings=list(PRIVACY_WARNINGS),
                safety_warnings=list(SAFETY_WARNINGS),
                not_trusted_evidence=True,
            )

        try:
            # Explicit transcription always takes priority and never sends the image to a cloud.
            if str(request.manual_transcription or "").strip():
                ocr = FakeOCRProvider().extract_text(image_bytes, request)
            else:
                ocr = self.ocr_provider.extract_text(image_bytes, request)
        except CloudAIError as exc:
            return PhotoIntakeResult(
                accepted=False,
                validation=validation.model_copy(update={"errors": [exc.code]}),
                ocr=None,
                privacy_warnings=list(PRIVACY_WARNINGS),
                safety_warnings=[*SAFETY_WARNINGS, "OCR unavailable; enter the text manually."],
            )
        # Remove private identifiers from BOTH representations returned by the API.
        ocr = ocr.model_copy(update={"text": _safe_extracted_text(ocr.text)})
        extracted_text = _safe_extracted_text(ocr.text)
        manual_transcription_used = bool(str(request.manual_transcription or "").strip())
        manual_warning = "Manual transcription was used instead of OCR text."
        if manual_transcription_used and manual_warning not in ocr.warnings:
            ocr = ocr.model_copy(
                update={
                    "warnings": [
                        *ocr.warnings,
                        manual_warning,
                    ]
                }
            )
        return PhotoIntakeResult(
            accepted=True,
            validation=validation,
            ocr=ocr,
            extracted_text=extracted_text,
            manual_transcription_used=manual_transcription_used,
            privacy_warnings=list(PRIVACY_WARNINGS),
            safety_warnings=list(SAFETY_WARNINGS),
            not_trusted_evidence=True,
        )


def report_to_jsonable(report: PhotoIntakeReport) -> dict:
    return report.model_dump(mode="json")


def report_to_markdown(report: PhotoIntakeReport) -> str:
    result = report.result
    validation = result.validation
    lines = [
        "# Photo Intake Inspection",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Accepted: {result.accepted}",
        f"- Detected type: {validation.detected_type or 'unknown'}",
        f"- Size bytes: {validation.size_bytes}",
        f"- Image hash present: {bool(validation.image_hash)}",
        f"- Manual transcription used: {result.manual_transcription_used}",
        f"- Not trusted evidence: {result.not_trusted_evidence}",
        f"- Used network: {result.ocr.used_network if result.ocr else False}",
        f"- Used external provider: {result.ocr.used_external_provider if result.ocr else False}",
        "",
        "## Extracted Text Preview",
        "",
        result.extracted_text or "No extracted text.",
        "",
        "## Privacy Warnings",
        "",
    ]
    lines.extend(f"- {warning}" for warning in result.privacy_warnings)
    lines.extend(["", "## Safety Warnings", ""])
    lines.extend(f"- {warning}" for warning in result.safety_warnings)
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def _safe_extracted_text(text: str) -> str:
    redacted, warnings = redact_sensitive_text(str(text or ""))
    if warnings:
        return redacted
    return str(text or "")
