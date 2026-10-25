"""Document-scoped exact-source and reference validation facade."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.config import settings
from backend.services.insight_service import validate_evidence
from backend.services.schemas import ModelEvidence, SourceCitation
from backend.services.summary_service import build_analysis_source_map
from backend.storage.temporary_storage import DocumentStore, StoredDocument
from backend.tools.common import require_scoped_document
from backend.tools.registry import ToolDefinition


class CitationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=160)
    reference: dict[str, Any] = Field(default_factory=dict, max_length=16)
    quote: str = Field(min_length=1, max_length=1200)


class ClaimForCitationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=80)
    evidence: list[CitationEvidence] = Field(default_factory=list, max_length=8)


class ValidateCitationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160)
    claims: list[ClaimForCitationCheck] = Field(max_length=500)


class ClaimCitationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verified_citations: list[SourceCitation] = Field(default_factory=list, max_length=8)
    rejected_evidence_count: int = Field(ge=0, le=8)
    reasons: list[str] = Field(default_factory=list, max_length=8)


class ValidateCitationsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    claims: list[ClaimCitationCheck] = Field(default_factory=list, max_length=500)


def build_document_source_map(document: StoredDocument) -> dict[str, dict[str, Any]]:
    """Map source IDs to the same passages/chunks used by current summary and chat services."""
    source_map = build_analysis_source_map(document.source_passages, document.extracted_text)
    for chunk in document.chat_chunks:
        source_id = str(chunk.get("source_id") or chunk.get("chunk_id") or "")
        if source_id:
            source_map[source_id] = {
                "source_id": source_id,
                "reference": chunk.get("reference") or {"type": "document"},
                "text": str(chunk.get("text") or ""),
            }
    return source_map


def validate_document_citations(
    document: StoredDocument,
    claims: list[ClaimForCitationCheck],
) -> ValidateCitationsOutput:
    source_map = build_document_source_map(document)
    checked: list[ClaimCitationCheck] = []
    for claim in claims:
        accepted: list[SourceCitation] = []
        reasons: list[str] = []
        rejected = 0
        for evidence in claim.evidence:
            if evidence.document_id != document.document_id:
                rejected += 1
                reasons.append("cross_document_reference")
                continue
            passage = source_map.get(evidence.source_id)
            if passage is None:
                rejected += 1
                reasons.append("unknown_source_id")
                continue
            expected_reference = passage.get("reference") or {"type": "document"}
            if evidence.reference != expected_reference:
                rejected += 1
                reasons.append("source_reference_mismatch")
                continue
            valid = validate_evidence(
                [ModelEvidence(source_id=evidence.source_id, quote=evidence.quote)],
                source_map,
            )
            if not valid:
                rejected += 1
                reasons.append("quote_not_found_in_source")
                continue
            accepted.extend(valid)
        checked.append(ClaimCitationCheck(
            claim_id=claim.claim_id,
            verified_citations=accepted[:8],
            rejected_evidence_count=rejected,
            reasons=list(dict.fromkeys(reasons))[:8],
        ))
    return ValidateCitationsOutput(document_id=document.document_id, claims=checked)


def make_validate_citations_tool(
    *, store: DocumentStore, allowed_document_id: str,
) -> ToolDefinition[ValidateCitationsInput, ValidateCitationsOutput]:
    def handler(request: ValidateCitationsInput) -> ValidateCitationsOutput:
        document = require_scoped_document(
            store,
            allowed_document_id=allowed_document_id,
            requested_document_id=request.document_id,
        )
        if len(request.claims) > 500:
            raise ValueError("Citation verification exceeds the configured claim limit.")
        if sum(len(e.quote) for c in request.claims for e in c.evidence) > settings.max_ai_input_chars:
            raise ValueError("Citation evidence exceeds the configured input size limit.")
        return validate_document_citations(document, request.claims)

    return ToolDefinition("validate_citations", ValidateCitationsInput, ValidateCitationsOutput, handler)
