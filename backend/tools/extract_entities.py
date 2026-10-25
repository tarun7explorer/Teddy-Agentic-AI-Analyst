"""Bounded deterministic mention extraction with source-backed candidate labels."""

import re

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.state import EntityCandidate
from backend.config import settings
from backend.storage.temporary_storage import DocumentStore, StoredDocument
from backend.tools.common import require_scoped_document
from backend.tools.registry import ToolDefinition


class ExtractEntitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160)
    max_entities: int = Field(default=100, ge=1, le=100)


class ExtractEntitiesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    candidates: list[EntityCandidate] = Field(default_factory=list, max_length=100)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=8)


_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"(?<!\w)(?:[$\u20ac\u00a3]\s*)?[+-]?\d[\d,]*(?:\.\d+)?\s?(?:%|million|billion|thousand)?", re.IGNORECASE)
_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30}){1,3}\b")


def extract_document_entities(document: StoredDocument, *, max_entities: int = 100) -> ExtractEntitiesOutput:
    limit = min(max_entities, 100)
    budget = min(settings.max_extracted_chars, 1_000_000)
    candidates: list[EntityCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    consumed = 0
    truncated = False

    patterns = (
        ("date_candidate", _DATE_PATTERN),
        ("number_candidate", _NUMBER_PATTERN),
        ("name_candidate", _NAME_PATTERN),
    )
    for passage in document.source_passages:
        source_id = str(passage.get("source_id") or "")
        text = str(passage.get("text") or "")
        remaining = budget - consumed
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        consumed += len(text)
        for category, pattern in patterns:
            for match in pattern.finditer(text):
                mention = match.group(0).strip()
                key = (source_id, category, mention.casefold())
                if not source_id or key in seen:
                    continue
                seen.add(key)
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 80)
                candidates.append(EntityCandidate(
                    category=category,
                    mention=mention[:160],
                    source_id=source_id,
                    reference=passage.get("reference") or {"type": "document"},
                    quote=text[start:end][:500],
                ))
                if len(candidates) >= limit:
                    return ExtractEntitiesOutput(
                        document_id=document.document_id,
                        candidates=candidates,
                        truncated=True,
                        warnings=["Entity candidate output reached its configured result limit."],
                    )
    warnings = ["Pattern matches are candidates only and are not semantic entity verification."] if candidates else []
    if truncated:
        warnings.append("Entity extraction was bounded by the configured input or result limit.")
    return ExtractEntitiesOutput(
        document_id=document.document_id,
        candidates=candidates,
        truncated=truncated,
        warnings=warnings[:8],
    )


def make_extract_entities_tool(
    *, store: DocumentStore, allowed_document_id: str,
) -> ToolDefinition[ExtractEntitiesInput, ExtractEntitiesOutput]:
    def handler(request: ExtractEntitiesInput) -> ExtractEntitiesOutput:
        document = require_scoped_document(
            store,
            allowed_document_id=allowed_document_id,
            requested_document_id=request.document_id,
        )
        return extract_document_entities(document, max_entities=request.max_entities)

    return ToolDefinition("extract_entities", ExtractEntitiesInput, ExtractEntitiesOutput, handler)
