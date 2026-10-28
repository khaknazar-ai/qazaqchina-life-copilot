from backend.app.photo_intake.local_ocr import (
    LocalOCREngineStatus,
    LocalOCRReadinessReport,
    check_local_ocr_readiness,
    local_ocr_report_to_jsonable,
    local_ocr_report_to_markdown,
)
from backend.app.photo_intake.models import (
    OCRResult,
    PhotoIntakeReport,
    PhotoIntakeRequest,
    PhotoIntakeResult,
    PhotoValidationResult,
)
from backend.app.photo_intake.ocr import (
    FakeOCRProvider,
    LocalOCRProvider,
    OCRProvider,
    create_ocr_provider,
)
from backend.app.photo_intake.service import (
    PhotoIntakeService,
    report_to_jsonable,
    report_to_markdown,
)
from backend.app.photo_intake.validation import (
    decode_base64_image,
    detect_image_type,
    sha256_bytes,
    validate_image_bytes,
)

__all__ = [
    "FakeOCRProvider",
    "LocalOCREngineStatus",
    "LocalOCRProvider",
    "LocalOCRReadinessReport",
    "OCRProvider",
    "OCRResult",
    "PhotoIntakeReport",
    "PhotoIntakeRequest",
    "PhotoIntakeResult",
    "PhotoIntakeService",
    "PhotoValidationResult",
    "check_local_ocr_readiness",
    "create_ocr_provider",
    "decode_base64_image",
    "detect_image_type",
    "local_ocr_report_to_jsonable",
    "local_ocr_report_to_markdown",
    "report_to_jsonable",
    "report_to_markdown",
    "sha256_bytes",
    "validate_image_bytes",
]
