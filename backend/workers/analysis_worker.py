"""Worker scaffold only. Analysis currently runs in the document request path."""


def process_analysis(_document_id: str):
    raise NotImplementedError("Background analysis workers are not implemented.")
