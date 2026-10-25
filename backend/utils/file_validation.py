"""Safe filename handling and practical file-signature validation."""

import re
import zipfile
from pathlib import Path, PurePath, PureWindowsPath


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_COMPRESSION_RATIO = 250


class UnsupportedFileType(ValueError):
    pass


class InvalidFile(ValueError):
    pass


class ResourceLimitExceeded(OverflowError):
    pass


def safe_display_filename(filename: str | None) -> str:
    raw = (filename or "document").replace("\x00", "")
    basename = PureWindowsPath(raw).name
    basename = PurePath(basename).name
    basename = re.sub(r"[\x00-\x1f\x7f]", "", basename).strip(" .")
    if not basename:
        basename = "document"
    return basename[:255]


def get_supported_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType("Supported file types are PDF, DOCX, TXT, CSV, and XLSX.")
    return extension


def _validate_zip(path: Path, expected_member: str, label: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ResourceLimitExceeded("The document archive contains too many internal files.")
            total_size = sum(entry.file_size for entry in entries)
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ResourceLimitExceeded("The uncompressed document exceeds the processing safety limit.")
            for entry in entries:
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
                    raise ResourceLimitExceeded("The document archive has an unsafe compression ratio.")
                if entry.flag_bits & 0x1:
                    raise InvalidFile("Encrypted document archives are not supported.")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or expected_member not in names:
                raise InvalidFile(f"The file content does not match a valid {label} document.")
            if archive.testzip() is not None:
                raise InvalidFile(f"The {label} archive is corrupted.")
    except zipfile.BadZipFile as exc:
        raise InvalidFile(f"The file is not a valid {label} document.") from exc


def validate_file_content(path: Path, extension: str) -> str:
    if path.stat().st_size == 0:
        raise InvalidFile("The uploaded file is empty.")
    with path.open("rb") as source:
        head = source.read(16)

    if extension == ".pdf":
        if not head.startswith(b"%PDF-"):
            raise InvalidFile("The file content does not match a PDF document.")
        return "pdf"
    if extension == ".docx":
        if not head.startswith(b"PK"):
            raise InvalidFile("The file content does not match a DOCX document.")
        _validate_zip(path, "word/document.xml", "DOCX")
        return "docx"
    if extension == ".xlsx":
        if not head.startswith(b"PK"):
            raise InvalidFile("The file content does not match an XLSX workbook.")
        _validate_zip(path, "xl/workbook.xml", "XLSX")
        return "xlsx"
    if extension in {".txt", ".csv"}:
        utf16_text = extension == ".txt" and head.startswith((b"\xff\xfe", b"\xfe\xff"))
        if not utf16_text:
            with path.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    if b"\x00" in chunk:
                        raise InvalidFile("The uploaded content appears to be binary, not plain text.")
        if b"\x00" in head and not utf16_text:
            raise InvalidFile("The uploaded content appears to be binary, not plain text.")
        return extension[1:]
    raise UnsupportedFileType("This file type is not supported.")
