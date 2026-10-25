"""XLSX extraction through Pandas and OpenPyXL with bounded row output."""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import settings
from backend.parsers.models import ExtractionResult


MAX_COLUMNS = 100
MAX_CELL_CHARS = 10_000


def _cell_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, str):
        return value[:MAX_CELL_CHARS]
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)[:MAX_CELL_CHARS]


def parse_xlsx(path: Path) -> ExtractionResult:
    tables: list[dict] = []
    sources: list[dict] = []
    passages: list[dict] = []
    text_parts: list[str] = []
    warnings: list[str] = []
    any_rows = False

    try:
        with pd.ExcelFile(path, engine="openpyxl") as workbook:
            if not workbook.sheet_names:
                raise ValueError("The Excel workbook does not contain any sheets.")
            remaining_rows = settings.max_table_rows
            for sheet_name in workbook.sheet_names:
                frame = workbook.parse(
                    sheet_name=sheet_name,
                    header=0,
                    nrows=remaining_rows + 1,
                    dtype=object,
                    keep_default_na=False,
                )
                if len(frame.columns) > MAX_COLUMNS:
                    raise OverflowError(f"Sheet '{sheet_name}' exceeds the {MAX_COLUMNS}-column processing limit.")
                if len(frame.columns) == 0:
                    continue
                truncated = len(frame.index) > remaining_rows
                if truncated:
                    frame = frame.iloc[:remaining_rows]
                    warnings.append("Workbook rows were truncated at the configured row limit.")
                if len(frame.index):
                    any_rows = True
                columns = [str(column)[:MAX_CELL_CHARS] for column in frame.columns]
                rows = []
                for row_offset, row_values in enumerate(frame.itertuples(index=False, name=None), start=2):
                    row = {columns[column_index]: _cell_value(value) for column_index, value in enumerate(row_values)}
                    rows.append(row)
                    row_reference = {"type": "sheet", "sheet": sheet_name, "row_start": row_offset, "row_end": row_offset}
                    passages.append({
                        "source_id": f"xlsx-sheet-{len(tables)}-row-{row_offset}",
                        "reference": row_reference,
                        "text": " | ".join(f"{column}: {row[column]}" for column in columns),
                    })
                table_index = len(tables) + 1
                reference = {"type": "sheet", "sheet": sheet_name, "row_start": 1, "row_end": len(rows) + 1}
                tables.append({
                    "name": sheet_name,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                    "source_reference": reference,
                })
                sources.append(reference)
                text_parts.append(f"Sheet: {sheet_name}\nColumns: " + " | ".join(columns))
                text_parts.extend(" | ".join(str(row[column]) for column in columns) for row in rows)
                remaining_rows = max(0, remaining_rows - len(rows))
                if remaining_rows == 0 and len(workbook.sheet_names) > len(tables):
                    warnings.append("Remaining workbook sheets were skipped at the configured row limit.")
                    break
    except (ValueError, OverflowError):
        raise
    except Exception as exc:
        raise ValueError("The Excel workbook is corrupted or unreadable.") from exc

    if not tables:
        raise ValueError("The workbook does not contain any extractable sheets or tables.")
    if not any_rows:
        warnings.append("The workbook contains sheet headers but no data rows.")
    extracted_text = "\n".join(text_parts)
    if len(extracted_text) > settings.max_extracted_chars:
        extracted_text = extracted_text[: settings.max_extracted_chars]
        warnings.append("Extracted text was truncated at the configured size limit.")
    return ExtractionResult(extracted_text, tables, sources, list(dict.fromkeys(warnings)), passages)
