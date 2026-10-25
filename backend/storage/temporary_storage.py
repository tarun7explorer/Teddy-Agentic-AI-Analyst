"""In-memory document metadata with expiring temporary source files."""

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.parsers.models import ExtractionResult


@dataclass
class StoredDocument:
    document_id: str
    original_filename: str
    detected_file_type: str
    file_size: int
    status: str
    extracted_text: str
    tables: list[dict[str, Any]]
    source_references: list[dict[str, Any]]
    warnings: list[str]
    source_passages: list[dict[str, Any]]
    chat_chunks: list[dict[str, Any]]
    created_at: float
    expires_at: float
    temp_path: Path
    analysis: dict[str, Any] | None = None
    analytics: dict[str, Any] | None = None
    chat_history: list[dict[str, str]] = field(default_factory=list)

    def status_response(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "detected_file_type": self.detected_file_type,
            "file_size": self.file_size,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "warnings": self.warnings,
        }

    def result_response(self) -> dict[str, Any]:
        result = self.status_response()
        result.update({
            "extracted_text": self.extracted_text,
            "tables": self.tables,
            "source_references": self.source_references,
        })
        if self.analysis is not None:
            result["analysis"] = self.analysis
        if self.analytics is not None:
            result["analytics"] = self.analytics
        return result


class DocumentStore:
    def __init__(self, directory: Path, ttl_minutes: int) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = ttl_minutes * 60
        self._documents: dict[str, StoredDocument] = {}
        self._lock = threading.RLock()

    def new_temp_path(self, document_id: str, extension: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory / f"{document_id}{extension}"

    def add(
        self, *, document_id: str, filename: str, detected_type: str, file_size: int,
        extraction: ExtractionResult, temp_path: Path,
        analytics: dict[str, Any] | None = None, chat_chunks: list[dict[str, Any]] | None = None,
    ) -> StoredDocument:
        now = time.time()
        document = StoredDocument(
            document_id=document_id, original_filename=filename, detected_file_type=detected_type,
            file_size=file_size, status="completed", extracted_text=extraction.extracted_text,
            tables=extraction.tables, source_references=extraction.source_references,
            warnings=extraction.warnings, source_passages=extraction.source_passages,
            chat_chunks=chat_chunks or [], created_at=now, expires_at=now + self.ttl_seconds,
            temp_path=temp_path, analytics=analytics,
        )
        with self._lock:
            self._documents[document_id] = document
        return document

    def save_analysis(self, document_id: str, analysis: dict[str, Any]) -> None:
        with self._lock:
            document = self._documents.get(document_id)
            if document is not None:
                document.analysis = analysis

    def get_chat_history(self, document_id: str) -> list[dict[str, str]]:
        with self._lock:
            document = self._documents.get(document_id)
            return [] if document is None else [dict(message) for message in document.chat_history]

    def append_chat_exchange(self, document_id: str, question: str, answer: str) -> bool:
        with self._lock:
            document = self._documents.get(document_id)
            if document is None:
                return False
            document.chat_history.extend([
                {"role": "user", "content": question}, {"role": "assistant", "content": answer},
            ])
            max_messages = settings.chat_history_turns * 2
            if max_messages == 0:
                document.chat_history.clear()
                return True
            document.chat_history[:] = document.chat_history[-max_messages:]
            while document.chat_history and sum(len(item["content"]) for item in document.chat_history) > settings.chat_history_max_chars:
                del document.chat_history[:2]
            return True

    def get(self, document_id: str) -> StoredDocument | None:
        self.cleanup_expired()
        with self._lock:
            return self._documents.get(document_id)

    def delete(self, document_id: str) -> bool:
        with self._lock:
            document = self._documents.pop(document_id, None)
        if document is None:
            return False
        self._remove_file(document.temp_path)
        return True

    def cleanup_expired(self) -> int:
        now = time.time()
        expired: list[StoredDocument] = []
        with self._lock:
            for document_id, document in list(self._documents.items()):
                if document.expires_at <= now:
                    expired.append(self._documents.pop(document_id))
        for document in expired:
            self._remove_file(document.temp_path)
        if self.directory.exists():
            cutoff = now - self.ttl_seconds
            for candidate in self.directory.iterdir():
                try:
                    if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                        candidate.unlink(missing_ok=True)
                except OSError:
                    continue
        return len(expired)

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


document_store = DocumentStore(settings.temp_directory, settings.document_ttl_minutes)
