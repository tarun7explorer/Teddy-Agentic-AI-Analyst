"""Compatibility import for existing callers of the original module path."""

from backend.storage.temporary_storage import DocumentStore, StoredDocument, document_store

__all__ = ["DocumentStore", "StoredDocument", "document_store"]
