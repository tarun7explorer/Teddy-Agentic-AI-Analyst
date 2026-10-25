"""Small deterministic normalization helper for extracted document text."""


def clean_extracted_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\x00", "").splitlines()).strip()
