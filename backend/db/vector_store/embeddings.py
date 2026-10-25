"""Embeddings are intentionally absent; chat does not call an embedding service."""


def embed_text(_text: str):
    raise NotImplementedError("No embedding provider is configured.")
