"""Compatibility import; retrieval implementation lives in the reference rag folder."""

from backend.rag.retriever import retrieve_relevant_chunks, tokenize

__all__ = ["retrieve_relevant_chunks", "tokenize"]
