"""Bounded source-aware chunking performed once when a document is uploaded."""

from typing import Any

from backend.config import settings


def _split_boundaries(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + size // 2, end), text.rfind(" ", start + size // 2, end))
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def build_document_chunks(
    source_passages: list[dict[str, Any]],
    extracted_text: str = "",
) -> list[dict[str, Any]]:
    """Split extracted passages while retaining each parser source reference."""
    passages = source_passages or ([{
        "source_id": "document-text", "reference": {"type": "document"}, "text": extracted_text,
    }] if extracted_text.strip() else [])
    chunks: list[dict[str, Any]] = []
    overlap = min(settings.chat_chunk_overlap_chars, settings.chat_chunk_chars // 3)
    for passage_index, passage in enumerate(passages, start=1):
        text = str(passage.get("text", "")).strip()
        if not text:
            continue
        base_id = str(passage.get("source_id") or f"source-{passage_index}")
        reference = passage.get("reference") or {"type": "document"}
        parts = [text] if len(text) <= settings.chat_chunk_chars else _split_boundaries(
            text, settings.chat_chunk_chars, overlap,
        )
        for part_index, part in enumerate(parts, start=1):
            chunk_id = base_id if len(parts) == 1 else f"{base_id}-chunk-{part_index}"
            chunks.append({"chunk_id": chunk_id, "source_id": chunk_id, "reference": reference, "text": part})
            if len(chunks) >= settings.chat_max_chunks:
                return chunks
    return chunks
