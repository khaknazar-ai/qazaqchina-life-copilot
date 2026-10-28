from datetime import UTC, datetime

from pydantic import BaseModel, Field


class PhotoIntakeRequest(BaseModel):
    filename: str | None = None
    content_type: str | None = None
    image_base64: str = Field(max_length=6_667_000)
    scenario: str | None = None
    language_hint: str | None = None
    manual_transcription: str | None = Field(default=None, max_length=12000)
    allow_cloud_processing: bool = False


class PhotoValidationResult(BaseModel):
    valid: bool
    detected_type: str | None = None
    size_bytes: int = 0
    image_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OCRResult(BaseModel):
    provider: str
    model: str
    text: str
    confidence: float | None = None
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, str | int] = Field(default_factory=dict)


class PhotoIntakeResult(BaseModel):
    accepted: bool
    validation: PhotoValidationResult
    ocr: OCRResult | None = None
    extracted_text: str | None = None
    manual_transcription_used: bool = False
    privacy_warnings: list[str] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    not_trusted_evidence: bool = True


class PhotoIntakeReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: PhotoIntakeResult
    notes: list[str] = Field(default_factory=list)
