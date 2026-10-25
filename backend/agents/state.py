"""Small, typed workflow state without duplicated document bodies or persistence."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from backend.analytics.schemas import AnalyticsResponse
from backend.services.schemas import SupportedFinding


class WorkflowStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class WorkflowStep(StrEnum):
    ASSESS_DOCUMENT = "assess_document"
    ANALYTICS = "analytics"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    GENERATE_SUMMARY = "generate_summary"
    ANSWER_CHAT = "answer_chat"
    VERIFY_OUTPUT = "verify_output"


class SafeErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    AI_DISABLED = "ai_disabled"
    AI_CONFIGURATION = "ai_configuration"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_MODEL_UNAVAILABLE = "provider_model_unavailable"
    PROVIDER_AUTHENTICATION = "provider_authentication_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_QUOTA_EXHAUSTED = "provider_quota_exhausted"
    PROVIDER_PAYMENT_REQUIRED = "provider_payment_required"
    PROVIDER_INVALID_RESPONSE = "provider_invalid_response"
    DOCUMENT_NOT_FOUND = "document_not_found"
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
    DOCUMENT_EMPTY = "document_empty"
    ANALYTICS_UNAVAILABLE = "analytics_unavailable"
    SUMMARY_UNAVAILABLE = "summary_unavailable"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    WORKFLOW_LIMIT = "workflow_limit"
    INTERNAL_ERROR = "internal_error"


class WorkflowWarningCode(StrEnum):
    DOCUMENT_NOT_FOUND = "document_not_found"
    PARTIAL_EXTRACTION = "partial_extraction"
    EMPTY_CONTENT = "empty_content"
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
    ANALYTICS_UNAVAILABLE = "analytics_unavailable"
    NO_ANALYTICS_DATA = "no_analytics_data"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    AI_UNAVAILABLE = "ai_unavailable"
    SUMMARY_FAILED = "summary_failed"
    VERIFICATION_PARTIAL = "verification_partial"
    WORKFLOW_STEP_LIMIT = "workflow_step_limit"
    WORKFLOW_TIMEOUT = "workflow_timeout"
    TOOL_FAILED = "tool_failed"


class WorkflowWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: WorkflowWarningCode
    message: str = Field(min_length=1, max_length=500)


class DocumentAssessment(BaseModel):
    """Metadata-only extraction assessment; source text stays in the document store."""

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=40)
    operation: Literal["analyze", "chat"] = "analyze"
    supported_type: bool = True
    sufficient_for_operation: bool = True
    extraction_quality: Literal["good", "partial", "poor", "empty"]
    extracted_char_count: int = Field(ge=0, le=5_000_000)
    passage_count: int = Field(ge=0, le=50_000)
    table_count: int = Field(ge=0, le=1_000)
    source_reference_count: int = Field(default=0, ge=0, le=50_000)
    warnings: list[str] = Field(default_factory=list, max_length=32)
    unsupported_content: list[str] = Field(default_factory=list, max_length=16)


class RetrievedEvidence(BaseModel):
    """Bounded cited excerpt, not a copy of the full source document."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=160)
    reference: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    quote: str = Field(min_length=1, max_length=1200)


class ClaimVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=2400)
    status: Literal["verified", "partially_verified", "unverified", "contradicted"]
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    reasons: list[str] = Field(default_factory=list, max_length=8)


class VerificationResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "partial", "failed", "not_run"] = "not_run"
    claims_checked: int = Field(default=0, ge=0, le=500)
    claims_with_valid_sources: int = Field(default=0, ge=0, le=500)
    rejected_claim_count: int = Field(default=0, ge=0, le=500)
    claim_results: list[ClaimVerification] = Field(default_factory=list, max_length=500)
    unresolved_warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "VerificationResults":
        if self.claims_with_valid_sources + self.rejected_claim_count > self.claims_checked:
            raise ValueError("Verification result counts exceed the number of claims checked.")
        return self


class EntityCandidate(BaseModel):
    """A source-backed pattern match, explicitly not a semantic entity assertion."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["date_candidate", "number_candidate", "name_candidate"]
    mention: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=160)
    reference: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    quote: str = Field(min_length=1, max_length=500)


_ALLOWED_TRANSITIONS = {
    WorkflowStatus.CREATED: {WorkflowStatus.RUNNING, WorkflowStatus.FAILED},
    WorkflowStatus.RUNNING: {WorkflowStatus.COMPLETED, WorkflowStatus.PARTIAL, WorkflowStatus.FAILED},
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.PARTIAL: set(),
    WorkflowStatus.FAILED: set(),
}


class WorkflowState(BaseModel):
    """Validated per-request workflow state; no persistence or full document copy."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    workflow_id: UUID = Field(default_factory=uuid4)
    current_document_id: str = Field(min_length=1, max_length=160)
    requested_operation: Literal["analyze", "chat"]
    status: WorkflowStatus = WorkflowStatus.CREATED
    completed_steps: list[WorkflowStep] = Field(default_factory=list, max_length=8)
    warnings: list[WorkflowWarning] = Field(default_factory=list, max_length=32)
    partial_result: bool = False
    document_assessment: DocumentAssessment | None = None
    analytics_results: AnalyticsResponse | None = None
    retrieved_evidence: list[RetrievedEvidence] = Field(default_factory=list, max_length=32)
    summary_findings: list[SupportedFinding] = Field(default_factory=list, max_length=160)
    entity_candidates: list[EntityCandidate] = Field(default_factory=list, max_length=100)
    verification_results: VerificationResults | None = None
    error_code: SafeErrorCode | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "WorkflowState":
        if self.started_at.tzinfo is None:
            raise ValueError("Workflow timestamps must include a timezone.")
        if self.ended_at is not None:
            if self.ended_at.tzinfo is None or self.ended_at < self.started_at:
                raise ValueError("Workflow end time must be timezone-aware and after its start time.")
        terminal = self.status in {WorkflowStatus.COMPLETED, WorkflowStatus.PARTIAL, WorkflowStatus.FAILED}
        if terminal != (self.ended_at is not None):
            raise ValueError("Terminal workflow states must have an end time; active states must not.")
        if (self.status == WorkflowStatus.PARTIAL) != self.partial_result:
            raise ValueError("Partial-result flag must agree with the workflow status.")
        if self.status == WorkflowStatus.FAILED and self.error_code is None:
            raise ValueError("Failed workflows require a safe error code.")
        if self.status == WorkflowStatus.COMPLETED and self.error_code is not None:
            raise ValueError("Completed workflows cannot contain an error code.")
        return self

    def __setattr__(self, name: str, value: object) -> None:
        if name == "status" and "status" in self.__dict__:
            raise ValueError("Change workflow status with transition_to().")
        super().__setattr__(name, value)

    def start(self) -> None:
        self.transition_to(WorkflowStatus.RUNNING)

    def record_completed_step(self, step: WorkflowStep) -> None:
        if self.status != WorkflowStatus.RUNNING:
            raise ValueError("Workflow steps can only be recorded while running.")
        step = WorkflowStep(step)
        if step in self.completed_steps:
            raise ValueError("A workflow step cannot be recorded twice.")
        self.completed_steps.append(step)

    def add_warning(self, code: WorkflowWarningCode, message: str) -> None:
        if self.status != WorkflowStatus.RUNNING:
            raise ValueError("Warnings can only be added while the workflow is running.")
        if not message.strip():
            return
        warning = WorkflowWarning(code=code, message=message)
        if warning not in self.warnings and len(self.warnings) < 32:
            self.warnings.append(warning)

    def transition_to(self, target: WorkflowStatus, *, error_code: SafeErrorCode | None = None) -> None:
        target = WorkflowStatus(target)
        if error_code is not None:
            error_code = SafeErrorCode(error_code)
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid workflow transition: {self.status.value} -> {target.value}.")
        if target == WorkflowStatus.FAILED and error_code is None:
            raise ValueError("Failed workflows require a safe error code.")
        if target not in {WorkflowStatus.FAILED, WorkflowStatus.PARTIAL} and error_code is not None:
            raise ValueError("An error code may only be set on failed or partial workflows.")
        object.__setattr__(self, "partial_result", target == WorkflowStatus.PARTIAL)
        object.__setattr__(self, "error_code", error_code)
        object.__setattr__(self, "status", target)
        if target in {WorkflowStatus.COMPLETED, WorkflowStatus.PARTIAL, WorkflowStatus.FAILED}:
            object.__setattr__(self, "ended_at", datetime.now(timezone.utc))

    @computed_field
    @property
    def duration_seconds(self) -> float | None:
        end = self.ended_at or datetime.now(timezone.utc)
        return max(0.0, (end - self.started_at).total_seconds())
