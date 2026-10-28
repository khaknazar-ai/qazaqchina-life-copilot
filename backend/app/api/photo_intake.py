from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_cloud_client
from backend.app.cloud_ai.client import QwenCloudClient
from backend.app.cloud_ai.ocr import QwenOCRProvider
from backend.app.config import Settings, get_settings
from backend.app.photo_intake.local_ocr import check_local_ocr_readiness
from backend.app.photo_intake.models import PhotoIntakeRequest, PhotoIntakeResult
from backend.app.photo_intake.ocr import LocalOCRProvider
from backend.app.photo_intake.service import PhotoIntakeService

router = APIRouter(prefix="/api/photo-intake", tags=["photo-intake"])


@router.post("/preview", response_model=PhotoIntakeResult)
def preview_photo_intake(
    request: PhotoIntakeRequest,
    cloud_client: Annotated[QwenCloudClient | None, Depends(get_cloud_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PhotoIntakeResult:
    if cloud_client and cloud_client.settings.QWEN_OCR_ENABLED:
        provider = QwenOCRProvider(cloud_client)
    elif settings.LOCAL_OCR_ENABLED:
        provider = LocalOCRProvider(settings)
    else:
        provider = None
    return PhotoIntakeService(ocr_provider=provider).preview_photo(request)


@router.get("/mode")
def photo_intake_mode(
    cloud_client: Annotated[QwenCloudClient | None, Depends(get_cloud_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    cloud = bool(cloud_client and cloud_client.settings.QWEN_OCR_ENABLED)
    if cloud:
        return {
            "provider": "qwen",
            "cloud_processing": True,
            "local_processing": False,
            "local_unavailable": False,
            "requires_photo_consent": True,
        }
    if not settings.LOCAL_OCR_ENABLED:
        return {
            "provider": "fake",
            "cloud_processing": False,
            "local_processing": False,
            "local_unavailable": False,
            "requires_photo_consent": False,
        }
    readiness = check_local_ocr_readiness(
        settings.LOCAL_OCR_TESSERACT_CMD,
        settings.LOCAL_OCR_LANGUAGES,
        settings.LOCAL_OCR_TESSDATA_DIR or None,
    )
    return {
        "provider": "local" if readiness.available else "local_unavailable",
        "cloud_processing": False,
        "local_processing": readiness.available,
        "local_unavailable": not readiness.available,
        "requires_photo_consent": False,
        "available_languages": readiness.engines[0].available_languages,
        "missing_languages": readiness.engines[0].missing_languages,
    }
