from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Journal RAG API"
    environment: str = "development"

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_user: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_request_timeout: int = 30
    documents_index: str = "rag_documents"
    chunks_index: str = "rag_chunks"
    jobs_index: str = "rag_jobs"
    account_classifications_index: str = "rag_account_classifications"

    redis_url: str = "redis://localhost:6379/0"

    gemini_api_key: str | None = None
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_generation_model: str = "gemini-2.5-flash"
    embedding_dimensions: int = 768

    chunk_size: int = 1000
    chunk_overlap: int = 150
    upload_dir: Path = Field(default=Path("./uploads"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAG_",
        extra="ignore",
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 1000)
        if value < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if value >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("embedding_dimensions must be greater than 0")
        return value

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
