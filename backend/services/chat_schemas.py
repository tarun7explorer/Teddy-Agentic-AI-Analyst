"""Request and response schemas for grounded document chat."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.services.schemas import ModelEvidence, SourceCitation


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def strip_and_require_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a question about this document.")
        return value


class ModelChatAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str = Field(min_length=1, max_length=4000)
    not_found: bool = False
    evidence: list[ModelEvidence] = Field(default_factory=list, max_length=8)


class ChatResponse(BaseModel):
    document_id: str
    status: Literal["answered", "not_found"]
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list, max_length=8)
