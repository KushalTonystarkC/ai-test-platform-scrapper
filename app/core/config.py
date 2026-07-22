from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "question-bank-kb"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://kushal:0000@localhost:5433/question_bank"
    database_echo: bool = False

    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    embedding_provider: str = "gemini"
    embedding_dimension: int = 1536
    embedding_model: str = "gemini-embedding-001"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2048

    chunk_min_words: int = 500
    chunk_max_words: int = 800

    task_backend: str = "in_memory"

    hybrid_keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    hybrid_semantic_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    search_default_limit: int = 10

    @field_validator("hybrid_semantic_weight")
    @classmethod
    def weights_sum_to_one(cls, v: float, info) -> float:  # type: ignore[no-untyped-def]
        keyword = info.data.get("hybrid_keyword_weight", 0.3)
        total = keyword + v
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"hybrid_keyword_weight + hybrid_semantic_weight must equal 1.0, got {total}"
            )
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
