"""Document type detection and parser dispatch."""

from pathlib import Path

from backend.parsers.csv_parser import parse_csv
from backend.parsers.word_parser import parse_docx
from backend.parsers.models import ExtractionResult
from backend.parsers.pdf_parser import parse_pdf
from backend.parsers.text_parser import parse_text
from backend.parsers.excel_parser import parse_xlsx
from backend.utils.file_validation import validate_file_content


PARSER_BY_EXTENSION = {
    ".pdf": ("pdf", parse_pdf),
    ".docx": ("docx", parse_docx),
    ".txt": ("txt", parse_text),
    ".csv": ("csv", parse_csv),
    ".xlsx": ("xlsx", parse_xlsx),
}


def parse_document(path: Path, extension: str) -> tuple[str, ExtractionResult]:
    detected_type = validate_file_content(path, extension)
    parser_type, parser = PARSER_BY_EXTENSION[extension]
    return parser_type, parser(path)
