"""PDF text extraction with page references and bounded work."""

from pathlib import Path

import fitz

from backend.config import settings
from backend.parsers.models import ExtractionResult


def parse_pdf(path: Path) -> ExtractionResult:
    parts: list[str] = []
    sources: list[dict[str, int]] = []
    passages: list[dict] = []
    warnings: list[str] = []
    total_chars = 0

    try:
        with fitz.open(path) as document:
            if document.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            if document.page_count == 0:
                raise ValueError("The PDF does not contain any pages.")
            if document.page_count > settings.max_pdf_pages:
                raise OverflowError(
                    f"The PDF exceeds the {settings.max_pdf_pages}-page processing limit."
                )
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if not text:
                    continue
                remaining = settings.max_extracted_chars - total_chars
                if remaining <= 0:
                    warnings.append("Extracted text was truncated at the configured size limit.")
                    break
                if len(text) > remaining:
                    text = text[:remaining]
                    warnings.append("Extracted text was truncated at the configured size limit.")
                parts.append(text)
                reference = {"type": "page", "page": page_number}
                sources.append(reference)
                passages.append({"source_id": f"pdf-page-{page_number}", "reference": reference, "text": text})
                total_chars += len(text)
                if total_chars >= settings.max_extracted_chars:
                    break
    except fitz.FileDataError as exc:
        raise ValueError("The PDF is corrupted or unreadable.") from exc

    if not parts:
        warnings.append("No selectable text was found. Scanned-page OCR is not available yet.")
    return ExtractionResult(
        extracted_text="\n\n".join(parts),
        source_references=sources,
        warnings=warnings,
        source_passages=passages,
    )
