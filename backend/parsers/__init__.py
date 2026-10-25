"""Document type detection and parser dispatch."""

from pathlib import Path

from backend.parsers.models import ExtractionResult
from backend.utils.file_validation import validate_file_content


def _parse_pdf(path: Path) -> ExtractionResult:
    from backend.parsers.pdf_parser import parse_pdf

    return parse_pdf(path)


def _parse_docx(path: Path) -> ExtractionResult:
    from backend.parsers.word_parser import parse_docx

    return parse_docx(path)


def _parse_text(path: Path) -> ExtractionResult:
    from backend.parsers.text_parser import parse_text

    return parse_text(path)


def _parse_csv(path: Path) -> ExtractionResult:
    from backend.parsers.csv_parser import parse_csv

    return parse_csv(path)


def _parse_xlsx(path: Path) -> ExtractionResult:
    from backend.parsers.excel_parser import parse_xlsx

    return parse_xlsx(path)


PARSER_BY_EXTENSION = {
    ".pdf": ("pdf", _parse_pdf),
    ".docx": ("docx", _parse_docx),
    ".txt": ("txt", _parse_text),
    ".csv": ("csv", _parse_csv),
    ".xlsx": ("xlsx", _parse_xlsx),
}


def parse_document(path: Path, extension: str) -> tuple[str, ExtractionResult]:
    detected_type = validate_file_content(path, extension)
    parser_type, parser = PARSER_BY_EXTENSION[extension]
    return parser_type, parser(path)
