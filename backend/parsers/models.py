"""Shared extraction result shape returned by the format parsers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    extracted_text: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    source_references: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_passages: list[dict[str, Any]] = field(default_factory=list)
