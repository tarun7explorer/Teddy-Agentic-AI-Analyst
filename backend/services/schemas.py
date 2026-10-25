"""Validated model output and public document-analysis response schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.services.workflow_schemas import WorkflowMetadata


class ModelEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_id: str = Field(min_length=1, max_length=160)
    quote: str = Field(min_length=1, max_length=1200)


class ModelStatement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=1, max_length=2400)
    evidence: list[ModelEvidence] = Field(default_factory=list, max_length=8)


class ModelEntity(ModelStatement):
    category: str = Field(default="other", max_length=40)


class ModelAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    five_line_summary: list[ModelStatement] = Field(min_length=5, max_length=5)
    detailed_summary: ModelStatement
    key_takeaways: list[ModelStatement] = Field(default_factory=list, max_length=20)
    important_entities: list[ModelEntity] = Field(default_factory=list, max_length=40)
    risks: list[ModelStatement] = Field(default_factory=list, max_length=20)
    decisions: list[ModelStatement] = Field(default_factory=list, max_length=20)
    action_items: list[ModelStatement] = Field(default_factory=list, max_length=20)

    @field_validator("five_line_summary")
    @classmethod
    def require_five_nonblank_lines(cls, value: list[ModelStatement]) -> list[ModelStatement]:
        if any(not item.text.strip() for item in value):
            raise ValueError("Summary lines must not be blank.")
        return value


class SourceCitation(BaseModel):
    source_id: str
    reference: dict[str, Any]
    quote: str


class SupportedFinding(BaseModel):
    text: str
    citations: list[SourceCitation] = Field(default_factory=list)


class EntityFinding(SupportedFinding):
    category: str = "other"


class AnalysisResponse(BaseModel):
    document_id: str
    status: str = "completed"
    provider: str = "nvidia_nim"
    model: str
    five_line_summary: list[SupportedFinding] = Field(min_length=5, max_length=5)
    detailed_summary: SupportedFinding
    key_takeaways: list[SupportedFinding]
    important_entities: list[EntityFinding]
    risks: list[SupportedFinding]
    decisions: list[SupportedFinding]
    action_items: list[SupportedFinding]
    warnings: list[str] = Field(default_factory=list)
    workflow: WorkflowMetadata | None = None
