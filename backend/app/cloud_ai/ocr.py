import base64

from backend.app.cloud_ai.client import CloudAIError, QwenCloudClient
from backend.app.cloud_ai.image_validation import validate_cloud_image
from backend.app.photo_intake.models import OCRResult, PhotoIntakeRequest
from backend.app.photo_intake.ocr import OCRProvider

# The compatible API selects the plain-text OCR task with this documented prompt:
# https://www.alibabacloud.com/help/en/model-studio/qwen-vl-ocr
TEXT_RECOGNITION_PROMPT = (
    "Please output only the text content from the image "
    "without any additional descriptions or formatting."
)


class QwenOCRProvider(OCRProvider):
    def __init__(self, client: QwenCloudClient) -> None:
        self.client = client

    def extract_text(self, image_bytes: bytes, request: PhotoIntakeRequest) -> OCRResult:
        if not request.allow_cloud_processing:
            raise CloudAIError("cloud_photo_consent_required")
        mime = validate_cloud_image(image_bytes)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        text, usage = self.client.complete(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                            "max_pixels": 2_097_152,
                        },
                        {
                            "type": "text",
                            "text": TEXT_RECOGNITION_PROMPT,
                        },
                    ],
                }
            ],
            kind="ocr",
        )
        return OCRResult(
            provider="qwen",
            model=self.client.settings.QWEN_OCR_MODEL,
            text=text,
            confidence=None,
            used_network=True,
            used_external_provider=True,
            usage=usage,
            warnings=["Cloud OCR can misread text. Verify names, dates and numbers."],
        )
