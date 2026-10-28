import subprocess

from backend.app.cloud_ai.client import CloudAIError
from backend.app.cloud_ai.image_validation import validate_cloud_image
from backend.app.config import Settings, get_settings
from backend.app.photo_intake.local_ocr import check_local_ocr_readiness, parse_language_codes
from backend.app.photo_intake.models import OCRResult, PhotoIntakeRequest

FAKE_OCR_MODEL = "fake-ocr-adapter-v1"
LOCAL_OCR_MODEL = "tesseract-local"
LOCAL_OCR_MAX_TEXT_CHARS = 12_000


class OCRProvider:
    def extract_text(self, image_bytes: bytes, request: PhotoIntakeRequest) -> OCRResult:
        raise NotImplementedError


class FakeOCRProvider(OCRProvider):
    provider = "fake"
    model = FAKE_OCR_MODEL

    def extract_text(self, image_bytes: bytes, request: PhotoIntakeRequest) -> OCRResult:
        manual_text = str(request.manual_transcription or "").strip()
        warnings = ["Fake OCR provider; not production OCR."]
        if manual_text:
            warnings.append("Manual transcription was used instead of OCR text.")
            return OCRResult(
                provider=self.provider,
                model=self.model,
                text=manual_text,
                confidence=1.0,
                used_network=False,
                used_external_provider=False,
                warnings=warnings,
            )
        return OCRResult(
            provider=self.provider,
            model=self.model,
            text=_demo_text_for_request(request),
            confidence=0.0,
            used_network=False,
            used_external_provider=False,
            warnings=warnings,
        )


class LocalOCRProvider(OCRProvider):
    provider = "local"
    model = LOCAL_OCR_MODEL

    def __init__(self, settings: Settings | None = None, runner=None) -> None:
        self.settings = settings or get_settings()
        self._runner = runner

    def extract_text(self, image_bytes: bytes, request: PhotoIntakeRequest) -> OCRResult:
        languages = parse_language_codes(self.settings.LOCAL_OCR_LANGUAGES)
        readiness = check_local_ocr_readiness(
            self.settings.LOCAL_OCR_TESSERACT_CMD,
            languages,
            self.settings.LOCAL_OCR_TESSDATA_DIR or None,
        )
        if not readiness.available:
            return self._unavailable_result(readiness.warnings)
        engine = readiness.engines[0]
        try:
            validate_cloud_image(image_bytes)
        except CloudAIError:
            return OCRResult(
                provider=self.provider,
                model=self.model,
                text="",
                warnings=["The selected image is invalid or unsupported for OCR."],
            )
        command = [
            engine.executable_path or self.settings.LOCAL_OCR_TESSERACT_CMD,
            "stdin",
            "stdout",
        ]
        if self.settings.LOCAL_OCR_TESSDATA_DIR:
            command.extend(["--tessdata-dir", self.settings.LOCAL_OCR_TESSDATA_DIR])
        command.extend(
            [
                "--oem",
                "1",
                "--psm",
                "3",
                "-l",
                self._select_languages(request, languages),
            ]
        )
        try:
            run = self._runner or subprocess.run
            completed = run(
                command,
                input=image_bytes,
                capture_output=True,
                timeout=self.settings.LOCAL_OCR_TIMEOUT_SECONDS,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return self._failed_result("Local OCR timed out. Try a smaller or clearer image.")
        except OSError:
            return self._failed_result(
                "Tesseract could not be started. Check its installation path."
            )
        if completed.returncode != 0:
            return self._failed_result(
                "Tesseract could not read this image. Check the image and installed language data."
            )
        text = (completed.stdout or b"").decode("utf-8", errors="replace").strip()
        warnings = ["Local OCR can misread text. Verify names, dates and numbers."]
        if len(text) > LOCAL_OCR_MAX_TEXT_CHARS:
            text = text[:LOCAL_OCR_MAX_TEXT_CHARS]
            warnings.append("OCR output was shortened to fit the review screen.")
        if not text:
            warnings.append("No text was detected. Try a clearer photo or enter the text manually.")
        return OCRResult(
            provider=self.provider,
            model=engine.version or self.model,
            text=text,
            confidence=None,
            used_network=False,
            used_external_provider=False,
            warnings=warnings,
        )

    def _select_languages(self, request: PhotoIntakeRequest, configured: tuple[str, ...]) -> str:
        hint = str(request.language_hint or "").strip().casefold().replace("_", "-")
        language = hint.split("-", 1)[0]
        preferred = {
            "zh": ("chi_sim", "eng"),
            "ru": ("rus", "eng"),
            "kk": ("kaz", "rus", "eng"),
            "en": ("eng",),
        }.get(language, configured)
        selected = tuple(code for code in preferred if code in configured)
        return "+".join(selected or configured)

    def _unavailable_result(self, readiness_warnings: list[str]) -> OCRResult:
        return OCRResult(
            provider=self.provider,
            model=self.model,
            text="",
            warnings=["Local OCR is not ready.", *readiness_warnings],
        )

    def _failed_result(self, warning: str) -> OCRResult:
        return OCRResult(
            provider=self.provider,
            model=self.model,
            text="",
            used_network=False,
            used_external_provider=False,
            warnings=[warning, "Enter the notice text manually if OCR remains unavailable."],
        )


def create_ocr_provider(provider: str = "fake", settings: Settings | None = None) -> OCRProvider:
    if provider == "fake":
        return FakeOCRProvider()
    if provider == "local":
        return LocalOCRProvider(settings)
    raise ValueError("Only fake or local Tesseract OCR providers are available.")


def _demo_text_for_request(request: PhotoIntakeRequest) -> str:
    combined = " ".join(
        value.casefold()
        for value in [
            request.scenario or "",
            request.language_hint or "",
            request.filename or "",
        ]
    )
    if any(hint in combined for hint in ["hospital", "medical", "医院", "挂号"]):
        return "请携带护照、医保或支付方式到医院窗口办理挂号。"
    if any(hint in combined for hint in ["university", "student", "study", "学校", "大学"]):
        return "请携带护照、录取通知书和住宿登记材料到学校报到。"
    if any(hint in combined for hint in ["notice", "chinese", "document", "residence", "police"]):
        return "请携带护照和签证到派出所办理登记。"
    return "No OCR text extracted in fake mode. Please type the notice text manually."
