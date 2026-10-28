from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LLM_DEFAULT_PROVIDER: str = "mock"
    LLM_DEFAULT_MODEL: str = "mock-qazaqchina-local"
    LLM_ENABLE_EXTERNAL: bool = False
    LLM_PROVIDER: str = "fake"
    LLM_PROVIDER_MODEL: str = "fake-grounded-llm"
    LLM_PROVIDER_ENABLED: bool = False
    LLM_GENERATION_MAX_TOKENS: int = 600
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: float = 30.0
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LOCAL_DATA_DIR: str = "data/local"
    ENABLE_LOCAL_PERSISTENCE: bool = False
    ADMIN_AUTH_ENABLED: bool = False
    SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED: bool = False
    ADMIN_AUTH_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    ADMIN_AUTH_ACTOR_ID: str = "local-operator"
    ADMIN_AUTH_ROLES: str = "admin_viewer"
    ADMIN_REVIEW_AUTH_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    ADMIN_REVIEW_AUTH_ACTOR_ID: str = ""
    ADMIN_REVIEW_AUTH_ROLES: str = "source_publisher"
    TRACE_DIR: str = ".traces"
    USE_AGENT_WORKFLOW: bool = False
    AGENT_USE_LANGGRAPH: bool = False
    AGENT_LANGGRAPH_USE_HYBRID_RAG: bool = True
    OLLAMA_CHAT_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3.5:9b-q4_K_M"
    OLLAMA_CONTEXT_TOKENS: int = Field(default=8192, ge=2048, le=16384)
    OLLAMA_MAX_TOKENS: int = Field(default=1200, ge=128, le=4096)
    OLLAMA_TIMEOUT_SECONDS: float = Field(default=120, ge=1, le=180)
    QWEN_CHAT_ENABLED: bool = False
    QWEN_OCR_ENABLED: bool = False
    LOCAL_OCR_ENABLED: bool = False
    LOCAL_OCR_TESSERACT_CMD: str = "tesseract"
    LOCAL_OCR_TESSDATA_DIR: str = ""
    LOCAL_OCR_LANGUAGES: str = "chi_sim+eng+rus+kaz"
    LOCAL_OCR_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=60)
    CLOUD_RETRIEVAL_ENABLED: bool = False
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v4"
    QWEN_EMBEDDING_DIMENSIONS: int = Field(default=1024, ge=64, le=2048)
    QWEN_RERANK_ENABLED: bool = False
    QWEN_RERANK_MODEL: str = "qwen3-rerank"
    SEMANTIC_CONFLICT_REVIEW_ENABLED: bool = False
    DASHSCOPE_API_KEY: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    DASHSCOPE_BASE_URL: str = ""
    QWEN_CHAT_MODEL: str = "qwen3.7-plus"
    QWEN_OCR_MODEL: str = "qwen-vl-ocr-2025-11-20"
    QWEN_TIMEOUT_SECONDS: float = Field(default=30, ge=1, le=60)
    QWEN_CHAT_MAX_TOKENS: int = Field(default=1200, ge=128, le=4096)
    QWEN_OCR_MAX_TOKENS: int = Field(default=4096, ge=128, le=8192)
    QWEN_DAILY_REQUEST_LIMIT: int = Field(default=20, ge=1, le=10000)
    QWEN_REQUESTS_PER_MINUTE: int = Field(default=6, ge=1, le=1000)
    PILOT_ACCESS_TOKENS: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    # Trusted deployment assignment, never a client profile or contributor badge.
    PILOT_ACCOUNT_TYPES: str = "{}"
    LOCAL_DEVICE_SIGNIN_ENABLED: bool = False
    LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER: str = Field(
        default="",
        pattern=(
            r"^(?:|https://servicewechat\.com/(?:wx[0-9a-f]{16}|touristappid)"
            r"/devtools/page-frame\.html)$"
        ),
    )
    API_MAX_BODY_BYTES: int = Field(default=65536, ge=1024, le=65536)
    API_MAX_IMAGE_BODY_BYTES: int = Field(default=6800000, ge=1024, le=6800000)
    API_MAX_CONCURRENT_REQUESTS: int = Field(default=8, ge=1, le=32)
    API_BODY_TIMEOUT_SECONDS: float = Field(default=10, ge=1, le=30)
    API_USER_REQUESTS_PER_MINUTE: int = Field(default=20, ge=1, le=120)
    API_IP_REQUESTS_PER_MINUTE: int = Field(default=120, ge=1, le=300)


@lru_cache
def get_settings() -> Settings:
    return Settings()
