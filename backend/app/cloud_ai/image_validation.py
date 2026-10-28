"""Decode and bound images before cloud processing consumes a request budget."""

import warnings
from io import BytesIO
from struct import error as StructError

from backend.app.cloud_ai.client import CloudAIError

MAX_IMAGE_BYTES = 5_000_000
MAX_IMAGE_PIXELS = 15_680_000
MAX_ASPECT_RATIO = 200
MIN_IMAGE_SIDE = 11
MAX_IMAGE_LONG_SIDE = 7680
MAX_IMAGE_SHORT_SIDE = 4320
MAX_WEBP_LONG_SIDE = 3840
MAX_WEBP_SHORT_SIDE = 2160
IMAGE_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_END_CRC = b"\xaeB`\x82"


def _require_complete_png(data: bytes) -> None:
    # Pillow verifies earlier chunk checksums but accepts a partial IEND checksum.
    # Check bounded chunk framing and a complete terminal IEND before decoding.
    offset = len(PNG_SIGNATURE)
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        end = offset + length + 12
        if end > len(data):
            break
        if data[offset + 4 : offset + 8] == b"IEND":
            if length == 0 and end == len(data) and data[end - 4 : end] == PNG_END_CRC:
                return
            break
        offset = end
    raise CloudAIError("cloud_image_invalid")


def validate_cloud_image(image_bytes: bytes) -> str:
    """Return the decoded MIME type, or reject without transmitting the image.

    The byte limit is the application's upload limit. The pixel, side and aspect
    limits follow the Qwen-OCR image requirements. Side caps conservatively bound
    JPEG/PNG to 8K and WEBP to 4K, where that format is supported. Verification
    checks container integrity; a second open and full decode also reject
    truncated pixel data.
    """
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise CloudAIError("cloud_image_invalid")
    if image_bytes.startswith(PNG_SIGNATURE):
        _require_complete_png(image_bytes)
    try:
        from PIL import Image, ImageFile
    except ImportError:
        raise CloudAIError("cloud_image_validation_unavailable") from None
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        # A permissive global decoder would undermine the integrity check.
        raise CloudAIError("cloud_image_validation_unavailable")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes), formats=list(IMAGE_MIME_TYPES)) as image:
                mime = IMAGE_MIME_TYPES.get(image.format or "")
                width, height = image.size
                long_side, short_side = max(width, height), min(width, height)
                if (
                    mime is None
                    or width < MIN_IMAGE_SIDE
                    or height < MIN_IMAGE_SIDE
                    or width * height > MAX_IMAGE_PIXELS
                    or long_side > short_side * MAX_ASPECT_RATIO
                    or long_side > MAX_IMAGE_LONG_SIDE
                    or short_side > MAX_IMAGE_SHORT_SIDE
                    or (
                        image.format == "WEBP"
                        and (
                            long_side > MAX_WEBP_LONG_SIDE
                            or short_side > MAX_WEBP_SHORT_SIDE
                        )
                    )
                    or getattr(image, "is_animated", False)
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise CloudAIError("cloud_image_invalid")
                image.verify()
            with Image.open(BytesIO(image_bytes), formats=list(IMAGE_MIME_TYPES)) as image:
                image.load()
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        OverflowError,
        StructError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise CloudAIError("cloud_image_invalid") from None
    return mime
