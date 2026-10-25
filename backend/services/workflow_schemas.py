"""Public, secret-free workflow metadata added to existing API responses."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.analytics.schemas import AnalyticsResponse


class WorkflowWarningView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class DocumentAssessmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=40)
    operation: Literal["analyze", "chat"]
    supported_type: bool
    sufficient_for_operation: bool
    extraction_quality: Literal["good", "partial", "poor", "empty"]
    extracted_char_count: int = Field(ge=0, le=5_000_000)
    passage_count: int = Field(ge=0, le=50_000)
    table_count: int = Field(ge=0, le=1_000)
    source_reference_count: int = Field(ge=0, le=50_000)
    warnings: list[str] = Field(default_factory=list, max_length=32)
    unsupported_content: list[str] = Field(default_factory=list, max_length=16)


class WorkflowEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=160)
    reference: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    quote: str = Field(min_length=1, max_length=1200)


class ClaimVerificationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=2400)
    status: Literal["verified", "partially_verified", "unverified", "contradicted"]
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    reasons: list[str] = Field(default_factory=list, max_length=8)


class VerificationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "partial", "failed", "not_run"] = "not_run"
    claims_checked: int = Field(default=0, ge=0, le=500)
    claims_with_valid_sources: int = Field(default=0, ge=0, le=500)
    rejected_claim_count: int = Field(default=0, ge=0, le=500)
    claim_results: list[ClaimVerificationView] = Field(default_factory=list, max_length=500)
    unresolved_warnings: list[str] = Field(default_factory=list, max_length=32)


class ProviderAvailabilityView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "nvidia_nim", "grok"]
    available: bool
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)


class WorkflowMetadata(BaseModel):
    """Stable additive response metadata; excludes workflow IDs and secrets."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_started", "created", "running", "completed", "partial", "failed"]
    partial_result: bool
    completed_steps: list[str] = Field(default_factory=list, max_length=8)
    warnings: list[WorkflowWarningView] = Field(default_factory=list, max_length=32)
    error_code: str | None = Field(default=None, max_length=64)
    document_assessment: DocumentAssessmentView
    analytics: AnalyticsResponse | None = None
    evidence: list[WorkflowEvidenceView] = Field(default_factory=list, max_length=32)
    verification: VerificationView = Field(default_factory=VerificationView)
    provider_status: ProviderAvailabilityView
