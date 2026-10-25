"""UTF text extraction."""

from pathlib import Path

from backend.config import settings
from backend.parsers.models import ExtractionResult


def parse_text(path: Path) -> ExtractionResult:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ValueError("The text file must use UTF-8 or UTF-16 encoding.") from exc
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("The file does not contain extractable text.")
    warnings = []
    if len(text) > settings.max_extracted_chars:
        text = text[: settings.max_extracted_chars]
        warnings.append("Extracted text was truncated at the configured size limit.")
    return ExtractionResult(
        extracted_text=text,
        source_references=[{"type": "text", "line_start": 1, "line_end": text.count("\n") + 1}],
        warnings=warnings,
        source_passages=[{
            "source_id": "text-lines-1",
            "reference": {"type": "text", "line_start": 1, "line_end": text.count("\n") + 1},
            "text": text,
        }],
    )
