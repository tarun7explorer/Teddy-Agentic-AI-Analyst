"""Timing helpers are reserved; no document text is emitted by these utilities."""

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def elapsed_seconds():
    start = perf_counter()
    result = {}
    try:
        yield result
    finally:
        result["elapsed_seconds"] = perf_counter() - start
