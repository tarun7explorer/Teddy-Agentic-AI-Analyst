"""Compatibility import; the implementation lives in the reference rag folder."""

from backend.rag.chunker import build_document_chunks

__all__ = ["build_document_chunks"]
