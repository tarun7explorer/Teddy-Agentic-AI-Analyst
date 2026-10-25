"""Assess already-extracted document content without re-opening or re-parsing it."""

from backend.agents.state import DocumentAssessment
from backend.storage.temporary_storage import StoredDocument


# Mirrors the active parser dispatch: PDF, DOCX, XLSX, CSV, and plain text.
_SUPPORTED_TYPES = frozenset({"pdf", "docx", "xlsx", "csv", "txt"})
_PARTIAL_WARNING_TERMS = (
    "truncat", "limit", "stopped", "unparseable", "scanned", "ocr", "could not",
    "unsupported", "partially", "not available",
)


class DocumentAgent:
    def assess(self, document: StoredDocument, operation: str) -> DocumentAssessment:
        if operation not in {"analyze", "chat"}:
            raise ValueError("Unsupported document operation.")

        document_type = str(document.detected_file_type or "unknown").casefold()
        supported = document_type in _SUPPORTED_TYPES
        text = str(document.extracted_text or "")
        passages = document.source_passages or []
        tables = document.tables or []
        parser_warnings = [str(warning)[:500] for warning in (document.warnings or [])]
        lower_warnings = [warning.casefold() for warning in parser_warnings]
        warning_indicates_partial = any(
            term in warning for term in _PARTIAL_WARNING_TERMS for warning in lower_warnings
        )
        has_text_evidence = bool(text.strip() or passages)
        has_any_content = has_text_evidence or bool(tables)
        sufficient = supported and (
            (has_text_evidence if operation == "chat" else has_any_content)
        )

        unsupported_content: list[str] = []
        if not supported:
            unsupported_content.append("unsupported_document_type")
        if not has_text_evidence:
            unsupported_content.append("no_extractable_text_or_passages")
        if not tables and not has_text_evidence:
            unsupported_content.append("no_extractable_tables")
        if any("ocr" in warning or "scanned" in warning or "no selectable text" in warning for warning in lower_warnings):
            unsupported_content.append("scanned_content_not_ocr_processed")
        if warning_indicates_partial:
            unsupported_content.append("parser_reported_incomplete_extraction")

        if not has_any_content:
            quality = "empty"
        elif not supported:
            quality = "poor"
        elif warning_indicates_partial or (operation == "analyze" and not has_text_evidence):
            quality = "partial"
        else:
            quality = "good"

        return DocumentAssessment(
            document_type=document_type,
            operation=operation,
            supported_type=supported,
            sufficient_for_operation=sufficient,
            extraction_quality=quality,
            extracted_char_count=min(len(text), 5_000_000),
            passage_count=min(len(passages), 50_000),
            table_count=min(len(tables), 1_000),
            source_reference_count=min(len(document.source_references or []), 50_000),
            warnings=parser_warnings[:32],
            unsupported_content=list(dict.fromkeys(unsupported_content))[:16],
        )
