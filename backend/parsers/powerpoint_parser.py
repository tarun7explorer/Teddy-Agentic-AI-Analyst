"""PowerPoint support is planned but not implemented in this release."""

from pathlib import Path

from backend.utils.file_validation import UnsupportedFileType


def parse_powerpoint(_path: Path):
    raise UnsupportedFileType("PowerPoint files are not supported yet.")
