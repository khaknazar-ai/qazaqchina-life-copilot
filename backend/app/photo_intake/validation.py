import base64
import binascii
import hashlib

from backend.app.photo_intake.models import PhotoValidationResult

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RIFF_MAGIC = b"RIFF"
WEBP_MAGIC = b"WEBP"

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}


def decode_base64_image(image_base64: str) -> bytes:
    value = str(image_base64 or "").strip()
    if "," in value and value.casefold().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image payload is not valid base64.") from exc


def detect_image_type(data: bytes) -> str | None:
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if len(data) >= 12 and data.startswith(RIFF_MAGIC) and data[8:12] == WEBP_MAGIC:
        return "image/webp"
    return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_image_bytes(
    data: bytes,
    content_type: str | None = None,
    max_bytes: int = 5_000_000,
) -> PhotoValidationResult:
    warnings: list[str] = []
    errors: list[str] = []
    size_bytes = len(data)
    detected_type = detect_image_type(data)
    normalized_content_type = (content_type or "").strip().casefold() or None

    if not data:
        errors.append("Image data is empty.")
    if size_bytes > max_bytes:
        errors.append(f"Image is too large. Maximum allowed size is {max_bytes} bytes.")
    if detected_type is None:
        errors.append("Unsupported or unknown image type.")
    if normalized_content_type and normalized_content_type not in ALLOWED_CONTENT_TYPES:
        errors.append(f"Unsupported content type: {content_type}.")
    if (
        detected_type
        and normalized_content_type in ALLOWED_CONTENT_TYPES
        and ALLOWED_CONTENT_TYPES[normalized_content_type] != detected_type
    ):
        warnings.append(
            f"Provided content type {content_type} does not match detected type {detected_type}."
        )

    return PhotoValidationResult(
        valid=not errors,
        detected_type=detected_type,
        size_bytes=size_bytes,
        image_hash=sha256_bytes(data) if data else None,
        warnings=warnings,
        errors=errors,
    )
