"""Vector storage is deferred; current chat uses pure-Python lexical retrieval."""


class VectorStore:
    def add(self, *_args, **_kwargs):
        raise NotImplementedError("No vector store is configured.")

    def search(self, *_args, **_kwargs):
        raise NotImplementedError("No vector store is configured.")
