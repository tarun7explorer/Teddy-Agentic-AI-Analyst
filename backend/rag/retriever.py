"""Small pure-Python BM25-style retrieval over cached document chunks."""

import math
import re
from collections import Counter
from typing import Any

from backend.config import settings


STOP_WORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be", "before", "by", "can",
    "did", "do", "does", "document", "for", "from", "how", "i", "in", "is", "it", "me", "of",
    "on", "or", "please", "should", "that", "the", "their", "this", "to", "was", "what", "when",
    "where", "which", "who", "why", "with", "would", "you", "your",
}
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(text.casefold()) if len(token) > 1 and token not in STOP_WORDS]


def retrieve_relevant_chunks(
    chunks: list[dict[str, Any]], question: str, *, top_k: int | None = None,
    max_context_chars: int | None = None,
) -> list[dict[str, Any]]:
    """Rank relevant chunks and return bounded passages with nonzero lexical relevance."""
    query_terms = Counter(tokenize(question))
    if not query_terms or not chunks:
        return []
    tokenized = [tokenize(str(chunk.get("text", ""))) for chunk in chunks]
    document_frequency: Counter[str] = Counter()
    for terms in tokenized:
        document_frequency.update(set(terms))
    average_length = sum(map(len, tokenized)) / max(1, len(tokenized))
    k1, b = 1.5, 0.75
    ranked: list[tuple[float, int]] = []
    for index, terms in enumerate(tokenized):
        frequencies = Counter(terms)
        length = len(terms)
        score = 0.0
        for term, query_frequency in query_terms.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            df = document_frequency[term]
            inverse_frequency = math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5))
            denominator = term_frequency + k1 * (1 - b + b * length / max(1, average_length))
            score += query_frequency * inverse_frequency * (term_frequency * (k1 + 1) / denominator)
        if score > 0:
            ranked.append((score, index))
    ranked.sort(key=lambda item: item[0], reverse=True)
    result: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    selected_chunk_ids: set[str] = set()
    context_limit = max_context_chars or settings.chat_max_context_chars
    used_chars = 0
    limit = top_k or settings.chat_retrieval_top_k
    for distinct_only in (True, False):
        for _, index in ranked:
            chunk = chunks[index]
            source_id = str(chunk.get("source_id") or chunk.get("chunk_id") or index)
            original_source = re.sub(r"-chunk-\d+$", "", source_id)
            chunk_id = str(chunk.get("chunk_id") or source_id)
            if distinct_only and original_source in seen_source_ids:
                continue
            if chunk_id in selected_chunk_ids:
                continue
            text = str(chunk.get("text", ""))
            if used_chars + len(text) > context_limit:
                remaining = context_limit - used_chars
                if remaining < 100:
                    continue
                text = text[:remaining]
            if not text.strip():
                continue
            item = dict(chunk)
            item["text"] = text
            result.append(item)
            selected_chunk_ids.add(chunk_id)
            seen_source_ids.add(original_source)
            used_chars += len(text)
            if len(result) >= limit or used_chars >= context_limit:
                return result
    return result
