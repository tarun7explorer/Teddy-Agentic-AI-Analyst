"""Image parsing and OCR are planned but not implemented in this release."""

from pathlib import Path

from backend.utils.file_validation import UnsupportedFileType


def parse_image(_path: Path):
    raise UnsupportedFileType("Image files and OCR are not supported yet.")
