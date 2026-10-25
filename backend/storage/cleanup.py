"""Explicit cleanup entry point for expiring in-memory documents and files."""

from backend.storage.temporary_storage import document_store


def cleanup_expired_documents() -> int:
    return document_store.cleanup_expired()
