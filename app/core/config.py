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

    # Default: local open-source sentence-transformers (no API key)
    embedding_provider: str = "sentence_transformers"
    embedding_dimension: int = 384
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    gemini_api_key: str = ""
    # Used by OpenAI-compatible APIs (Ollama, Groq, OpenRouter, OpenAI)
    openai_api_key: str = "ollama"
    openai_base_url: str = "http://localhost:11434/v1"

    # Default: Ollama via OpenAI-compatible chat API
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"
    llm_temperature: float = 0.0
    # Higher temperature for MCQ generation so multi-question runs stay varied.
    # (Metadata extraction keeps using the deterministic llm_temperature.)
    llm_question_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    llm_max_tokens: int = 2048
    # HTTP timeout for LLM calls (local CPU models often need 300+)
    llm_timeout_seconds: float = Field(default=300.0, ge=30.0, le=1800.0)

    chunk_min_words: int = 500
    chunk_max_words: int = 800

    # Max MCQs allowed in a single POST /questions/generate request
    question_generate_max_count: int = Field(default=10, ge=1, le=100)

    task_backend: str = "in_memory"

    hybrid_keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    hybrid_semantic_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    search_default_limit: int = 10

    # Comma-separated origins for the Next.js showcase UI
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

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
