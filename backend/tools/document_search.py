"""Bounded lexical search over the current document's cached source chunks."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.config import settings
from backend.rag.retriever import retrieve_relevant_chunks
from backend.storage.temporary_storage import DocumentStore, StoredDocument
from backend.tools.common import require_scoped_document
from backend.tools.registry import ToolDefinition


class DocumentSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=4000)
    max_results: int = Field(default=5, ge=1, le=10)


class SearchPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=160)
    reference: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    text: str = Field(min_length=1, max_length=5000)


class DocumentSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    passages: list[SearchPassage] = Field(default_factory=list, max_length=10)
    characters_returned: int = Field(ge=0, le=30_000)
    warnings: list[str] = Field(default_factory=list, max_length=8)


def search_document(
    document: StoredDocument,
    *,
    query: str,
    max_results: int,
) -> DocumentSearchOutput:
    if not query.strip() or len(query) > settings.chat_max_question_chars:
        raise ValueError("Search query is empty or exceeds the configured question limit.")
    limit = min(max_results, settings.chat_retrieval_top_k, 10)
    selected = retrieve_relevant_chunks(
        document.chat_chunks,
        query.strip(),
        top_k=limit,
        max_context_chars=settings.chat_max_context_chars,
    )
    passages = [
        SearchPassage(
            source_id=str(item.get("source_id") or item.get("chunk_id") or ""),
            reference=item.get("reference") or {"type": "document"},
            text=str(item.get("text", ""))[: min(settings.chat_chunk_chars, 5000)],
        )
        for item in selected
        if str(item.get("text", "")).strip()
    ]
    return DocumentSearchOutput(
        document_id=document.document_id,
        passages=passages,
        characters_returned=sum(len(item.text) for item in passages),
        warnings=[] if passages else ["No relevant extracted passage was found for this query."],
    )


def make_document_search_tool(
    *, store: DocumentStore, allowed_document_id: str,
) -> ToolDefinition[DocumentSearchInput, DocumentSearchOutput]:
    def handler(request: DocumentSearchInput) -> DocumentSearchOutput:
        document = require_scoped_document(
            store,
            allowed_document_id=allowed_document_id,
            requested_document_id=request.document_id,
        )
        return search_document(document, query=request.query, max_results=request.max_results)

    return ToolDefinition("document_search", DocumentSearchInput, DocumentSearchOutput, handler)
