from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.config import Settings, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    llm_provider: str
    llm_model: str


@router.get("/health", response_model=HealthResponse)
def health_check(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="QminiGuide API",
        environment=settings.APP_ENV,
        llm_provider="ollama" if settings.OLLAMA_CHAT_ENABLED else settings.LLM_DEFAULT_PROVIDER,
        llm_model=(
            settings.OLLAMA_MODEL if settings.OLLAMA_CHAT_ENABLED else settings.LLM_DEFAULT_MODEL
        ),
    )
