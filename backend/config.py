"""Environment-backed application settings."""

import tempfile
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Teddy - Smart AI Analyst"
    environment: str = "development"
    debug: bool = False
    max_upload_size_mb: int = Field(default=10, ge=1, le=100)
    document_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    max_pdf_pages: int = Field(default=200, ge=1, le=2000)
    max_table_rows: int = Field(default=1000, ge=1, le=10000)
    max_extracted_chars: int = Field(default=1_000_000, ge=1000, le=5_000_000)
    max_concurrent_documents: int = Field(default=2, ge=1, le=8)
    upload_temp_dir: Path | None = None
    nvidia_nim_api_key: str | None = None
    nvidia_nim_api_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_nim_timeout_seconds: float = Field(default=45.0, gt=0, le=180)
    max_concurrent_ai_requests: int = Field(default=2, ge=1, le=8)
    nvidia_nim_temperature: float = Field(default=0.2, ge=0, le=2)
    nvidia_nim_top_p: float = Field(default=0.7, gt=0, le=1)
    nvidia_nim_max_tokens: int = Field(default=1800, ge=128, le=8192)
    max_ai_input_chars: int = Field(default=48000, ge=4000, le=200000)
    ai_chunk_chars: int = Field(default=8000, ge=1000, le=32000)
    max_ai_chunks: int = Field(default=6, ge=1, le=24)
    chat_chunk_chars: int = Field(default=1200, ge=200, le=5000)
    chat_chunk_overlap_chars: int = Field(default=120, ge=0, le=1000)
    chat_max_chunks: int = Field(default=1200, ge=1, le=5000)
    chat_retrieval_top_k: int = Field(default=5, ge=1, le=10)
    chat_max_context_chars: int = Field(default=9000, ge=1000, le=30000)
    chat_max_question_chars: int = Field(default=1000, ge=50, le=4000)
    chat_history_turns: int = Field(default=4, ge=0, le=10)
    chat_history_max_chars: int = Field(default=6000, ge=500, le=20000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def temp_directory(self) -> Path:
        return self.upload_temp_dir or (Path(tempfile.gettempdir()) / "teddy-uploads")


settings = Settings()
