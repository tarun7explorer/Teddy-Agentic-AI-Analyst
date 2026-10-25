"""CSV extraction to bounded, source-addressable table rows."""

import csv
from pathlib import Path

from backend.config import settings
from backend.parsers.models import ExtractionResult


MAX_COLUMNS = 100
MAX_CELL_CHARS = 10_000


def parse_csv(path: Path) -> ExtractionResult:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            headers = next(reader, None)
            if not headers or not any(header.strip() for header in headers):
                raise ValueError("The CSV does not contain a header row.")
            if len(headers) > MAX_COLUMNS:
                raise OverflowError(f"The CSV exceeds the {MAX_COLUMNS}-column processing limit.")
            headers = [header.strip()[:MAX_CELL_CHARS] or f"Column {index + 1}" for index, header in enumerate(headers)]
            rows = []
            passages = []
            truncated = False
            for row_number, values in enumerate(reader, start=2):
                if row_number - 1 > settings.max_table_rows:
                    truncated = True
                    break
                if len(values) > MAX_COLUMNS:
                    raise OverflowError(f"The CSV exceeds the {MAX_COLUMNS}-column processing limit.")
                if len(values) > len(headers):
                    raise ValueError("The CSV contains rows with more values than its header row.")
                values = [value[:MAX_CELL_CHARS] for value in values]
                values += [""] * (len(headers) - len(values))
                row = {headers[index]: values[index] for index in range(len(headers))}
                rows.append(row)
                source_reference = {"type": "csv", "row_start": row_number, "row_end": row_number}
                passages.append({
                    "source_id": f"csv-row-{row_number}",
                    "reference": source_reference,
                    "text": " | ".join(f"{column}: {row[column]}" for column in headers),
                })
    except (csv.Error, UnicodeDecodeError) as exc:
        raise ValueError("The CSV is malformed or is not UTF-8 encoded.") from exc

    if not rows and not headers:
        raise ValueError("The CSV does not contain extractable data.")
    table = {
        "name": "CSV data",
        "columns": headers,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "source_reference": {"type": "csv", "row_start": 1, "row_end": len(rows) + 1},
    }
    lines = ["Columns: " + " | ".join(headers)]
    lines.extend(" | ".join(str(row[column]) for column in headers) for row in rows)
    text = "\n".join(lines)[: settings.max_extracted_chars]
    warnings = ["CSV rows were truncated at the configured row limit."] if truncated else []
    if not rows:
        warnings.append("The CSV contains column names but no data rows.")
    return ExtractionResult(
        extracted_text=text,
        tables=[table],
        source_references=[table["source_reference"]],
        warnings=warnings,
        source_passages=passages,
    )
