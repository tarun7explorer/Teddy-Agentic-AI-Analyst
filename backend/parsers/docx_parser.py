"""DOCX extraction preserving paragraph and table order where possible."""

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from backend.config import settings
from backend.parsers.models import ExtractionResult


MAX_DOCX_BLOCKS = 10_000
MAX_DOCX_TABLE_ROWS = 10_000
MAX_CELL_CHARS = 10_000


def parse_docx(path: Path) -> ExtractionResult:
    try:
        document = Document(path)
        blocks = document.iter_inner_content()
        text_parts: list[str] = []
        tables: list[dict] = []
        sources: list[dict] = []
        passages: list[dict] = []
        warnings: list[str] = []
        total_chars = 0
        total_table_rows = 0
        paragraph_index = 0

        for block_number, block in enumerate(blocks, start=1):
            if block_number > MAX_DOCX_BLOCKS:
                warnings.append("Document block processing stopped at the safety limit.")
                break
            if isinstance(block, Paragraph):
                content = block.text.strip()
                if not content:
                    continue
                remaining = settings.max_extracted_chars - total_chars
                if remaining <= 0:
                    warnings.append("Extracted text was truncated at the configured size limit.")
                    break
                if len(content) > remaining:
                    content = content[:remaining]
                    warnings.append("Extracted text was truncated at the configured size limit.")
                text_parts.append(content)
                paragraph_index += 1
                reference = {"type": "paragraph", "paragraph": paragraph_index}
                sources.append(reference)
                passages.append({"source_id": f"docx-paragraph-{paragraph_index}", "reference": reference, "text": content})
                total_chars += len(content)
            elif isinstance(block, Table):
                if total_table_rows >= settings.max_table_rows:
                    warnings.append("Table processing stopped at the configured row limit.")
                    break
                rows = []
                for row_number, row in enumerate(block.rows):
                    if row_number >= min(MAX_DOCX_TABLE_ROWS, settings.max_table_rows - total_table_rows):
                        warnings.append("A Word table was truncated at the row safety limit.")
                        break
                    remaining_chars = max(0, settings.max_extracted_chars - total_chars)
                    if remaining_chars <= 0:
                        warnings.append("Extracted text was truncated at the configured size limit.")
                        break
                    cells = []
                    for cell in row.cells:
                        remaining_chars = max(0, settings.max_extracted_chars - total_chars)
                        cells.append(cell.text.strip()[: min(MAX_CELL_CHARS, remaining_chars)])
                    total_chars += sum(len(cell) for cell in cells)
                    rows.append(cells)
                    total_table_rows += 1
                table_index = len(tables) + 1
                tables.append({"name": f"Table {table_index}", "rows": rows, "source_reference": {"type": "table", "table": table_index}})
                table_text = f"[Table {table_index}]\n" + "\n".join(" | ".join(row) for row in rows)
                text_parts.append(table_text[: max(0, settings.max_extracted_chars - total_chars)])
                reference = {"type": "table", "table": table_index}
                sources.append(reference)
                passages.append({"source_id": f"docx-table-{table_index}", "reference": reference, "text": table_text[: settings.max_extracted_chars]})

        extracted = "\n\n".join(text_parts)
        if total_chars >= settings.max_extracted_chars:
            warnings.append("Extracted text was truncated at the configured size limit.")
        if not extracted.strip() and not tables:
            warnings.append("No extractable paragraphs or tables were found in this Word document.")
        return ExtractionResult(extracted, tables, sources, list(dict.fromkeys(warnings)), passages)
    except (ValueError, OverflowError):
        raise
    except Exception as exc:
        raise ValueError("The Word document is corrupted or unreadable.") from exc
