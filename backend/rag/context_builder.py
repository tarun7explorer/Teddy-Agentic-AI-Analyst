"""Bounded context formatting helper for retrieved source passages."""

from typing import Any


def build_context(passages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Copy passages in ranked order until the character budget is consumed."""
    if max_chars <= 0:
        return []
    result = []
    used = 0
    for passage in passages:
        text = str(passage.get("text", ""))
        remaining = max_chars - used
        if remaining <= 0:
            break
        item = dict(passage)
        item["text"] = text[:remaining]
        if item["text"].strip():
            result.append(item)
            used += len(item["text"])
    return result
