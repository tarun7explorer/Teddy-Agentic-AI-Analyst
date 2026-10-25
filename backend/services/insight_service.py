"""Evidence validation and safe conversion of model claims into citations."""

import re
from typing import Any

from backend.services.schemas import ModelEvidence, ModelStatement, SourceCitation, SupportedFinding


def _normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def validate_evidence(
    evidence: list[ModelEvidence],
    source_map: dict[str, dict[str, Any]],
) -> list[SourceCitation]:
    """Accept citations only when their source ID and quoted text exist in extracted data."""
    verified: list[SourceCitation] = []
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        passage = source_map.get(item.source_id)
        if passage is None:
            continue
        quote = item.quote.strip()
        if not quote or _normalize_quote(quote) not in _normalize_quote(passage.get("text", "")):
            continue
        key = (item.source_id, _normalize_quote(quote))
        if key in seen:
            continue
        seen.add(key)
        verified.append(SourceCitation(
            source_id=item.source_id,
            reference=passage.get("reference") or {"type": "document"},
            quote=quote,
        ))
    return verified


def verify_statement(statement: ModelStatement, source_map: dict[str, dict[str, Any]]) -> SupportedFinding | None:
    citations = validate_evidence(statement.evidence, source_map)
    if not statement.text.strip() or not citations:
        return None
    return SupportedFinding(text=statement.text.strip(), citations=citations)
