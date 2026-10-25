"""Shared document-scope checks for application-owned tools."""

from backend.storage.temporary_storage import DocumentStore, StoredDocument


class DocumentScopeError(ValueError):
    """Tool request attempted to leave its explicitly bound document scope."""


def require_scoped_document(
    store: DocumentStore,
    *,
    allowed_document_id: str,
    requested_document_id: str,
) -> StoredDocument:
    if requested_document_id != allowed_document_id:
        raise DocumentScopeError("Tool access is limited to the current document.")
    document = store.get(allowed_document_id)
    if document is None:
        raise LookupError("The current document is not available or has expired.")
    return document
