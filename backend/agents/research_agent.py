"""Retrieve bounded evidence from the current document using existing BM25 RAG."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.state import RetrievedEvidence
from backend.tools.document_search import DocumentSearchOutput, SearchPassage
from backend.tools.registry import ToolNotAllowed, ToolRegistry, ToolExecutionError


class ResearchAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["found", "not_found", "unavailable"]
    evidence: list[RetrievedEvidence] = Field(default_factory=list, max_length=10)
    passages: list[SearchPassage] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class ResearchAgent:
    async def retrieve(
        self,
        *,
        document_id: str,
        query: str,
        registry: ToolRegistry,
        max_results: int = 5,
    ) -> ResearchAgentResult:
        try:
            raw = await registry.execute("document_search", {
                "document_id": document_id,
                "query": query,
                "max_results": max_results,
            })
            result = DocumentSearchOutput.model_validate(raw)
        except (ToolNotAllowed, ToolExecutionError, ValidationError, ValueError):
            return ResearchAgentResult(
                status="unavailable",
                warnings=["Document-scoped retrieval could not complete safely."],
            )
        passages = result.passages
        return ResearchAgentResult(
            status="found" if passages else "not_found",
            passages=passages,
            evidence=[
                RetrievedEvidence(
                    source_id=passage.source_id,
                    reference=passage.reference,
                    quote=passage.text[:1200],
                )
                for passage in passages
            ],
            warnings=result.warnings,
        )
