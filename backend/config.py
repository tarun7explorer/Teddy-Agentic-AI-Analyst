"""Environment-backed application settings."""

import tempfile
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


NVIDIA_APPROVED_BASE_URL = "https://integrate.api.nvidia.com/v1"
XAI_APPROVED_BASE_URL = "https://api.x.ai/v1"


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
    # External AI is opt-in. The app deliberately has no paid-provider mode.
    allow_paid_apis: Literal[False] = Field(default=False, validation_alias="ALLOW_PAID_APIS")
    ai_provider: Literal["none", "nvidia_nim", "grok"] = "none"
    nvidia_nim_free_access_confirmed: bool = False
    nvidia_nim_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"),
        repr=False,
    )
    nvidia_nim_api_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NVIDIA_BASE_URL", "NVIDIA_NIM_API_BASE_URL"),
    )
    nvidia_nim_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NVIDIA_MODEL", "NVIDIA_NIM_MODEL"),
    )
    enable_grok: bool = False
    grok_free_api_access_confirmed: bool = False
    xai_api_key: str | None = Field(default=None, repr=False)
    xai_model: str | None = None
    xai_base_url: str | None = None
    ai_request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=180,
        validation_alias=AliasChoices("AI_REQUEST_TIMEOUT_SECONDS", "NVIDIA_NIM_TIMEOUT_SECONDS"),
    )
    ai_max_retries: int = Field(default=1, ge=0, le=1)
    agent_max_steps: int = Field(default=8, ge=1, le=8)
    agent_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ai_max_output_chars: int = Field(default=16_000, ge=256, le=64_000)
    max_concurrent_ai_requests: int = Field(default=2, ge=1, le=8)
    nvidia_nim_temperature: float = Field(default=0.2, ge=0, le=2)
    nvidia_nim_top_p: float = Field(default=0.7, gt=0, le=1)
    ai_max_output_tokens: int = Field(
        default=1800,
        ge=128,
        le=8192,
        validation_alias=AliasChoices("AI_MAX_OUTPUT_TOKENS", "NVIDIA_NIM_MAX_TOKENS"),
    )
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

    @model_validator(mode="after")
    def validate_ai_configuration(self) -> "Settings":
        if self.allow_paid_apis is not False:
            raise ValueError("Paid API usage is disabled and cannot be enabled.")

        if self.ai_provider == "nvidia_nim":
            if not self.nvidia_nim_free_access_confirmed:
                raise ValueError("NVIDIA NIM requires NVIDIA_NIM_FREE_ACCESS_CONFIRMED=true.")
            if not (self.nvidia_nim_api_key or "").strip():
                raise ValueError("NVIDIA NIM requires NVIDIA_API_KEY.")
            if not (self.nvidia_nim_model or "").strip():
                raise ValueError("NVIDIA NIM requires an explicitly configured NVIDIA_MODEL.")
            if self.nvidia_nim_api_base_url != NVIDIA_APPROVED_BASE_URL:
                raise ValueError("NVIDIA_BASE_URL must be the approved NVIDIA NIM endpoint.")

        if self.ai_provider == "grok":
            if not self.enable_grok:
                raise ValueError("Grok requires ENABLE_GROK=true.")
            if not self.grok_free_api_access_confirmed:
                raise ValueError("Grok requires GROK_FREE_API_ACCESS_CONFIRMED=true.")
            if not (self.xai_api_key or "").strip():
                raise ValueError("Grok requires XAI_API_KEY.")
            if not (self.xai_model or "").strip():
                raise ValueError("Grok requires an explicitly configured XAI_MODEL.")
            if self.xai_base_url and self.xai_base_url != XAI_APPROVED_BASE_URL:
                raise ValueError("XAI_BASE_URL must be the approved xAI API endpoint.")

        if self.enable_grok and self.ai_provider != "grok":
            raise ValueError("ENABLE_GROK=true is valid only when AI_PROVIDER=grok.")
        return self

    @property
    def nvidia_nim_timeout_seconds(self) -> float:
        """Backward-compatible view of the shared provider timeout setting."""
        return self.ai_request_timeout_seconds

    @property
    def nvidia_nim_max_tokens(self) -> int:
        """Backward-compatible view of the shared provider output-token limit."""
        return self.ai_max_output_tokens

    @property
    def temp_directory(self) -> Path:
        return self.upload_temp_dir or (Path(tempfile.gettempdir()) / "teddy-uploads")


settings = Settings()
