"""Document-scoped facade over the existing deterministic analytics profiler."""

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from backend.analytics.schemas import AnalyticsResponse
from backend.storage.temporary_storage import DocumentStore, StoredDocument
from backend.tools.common import require_scoped_document
from backend.tools.registry import ToolDefinition


class CalculateStatisticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160)


class NumericCalculation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=240)
    value: FiniteFloat
    unit: str | None = Field(default=None, max_length=32)
    method: str = Field(min_length=1, max_length=120)
    source_reference: dict[str, Any] = Field(default_factory=dict, max_length=16)


class CalculateStatisticsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    status: Literal["available", "no_suitable_data"]
    analytics: AnalyticsResponse
    calculations: list[NumericCalculation] = Field(default_factory=list, max_length=500)
    input_table_count: int = Field(ge=0, le=12)
    input_passage_count: int = Field(ge=0, le=50_000)
    input_scope: str = Field(max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=32)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _numeric_results(analytics: AnalyticsResponse) -> list[NumericCalculation]:
    results: list[NumericCalculation] = []
    seen: set[tuple[str, float, str]] = set()

    def add(label: str, value: Any, unit: str | None, method: str, reference: dict[str, Any]) -> None:
        number = _finite_number(value)
        if number is None or len(results) >= 500:
            return
        key = (label.casefold(), number, method.casefold())
        if key in seen:
            return
        seen.add(key)
        results.append(NumericCalculation(
            label=label[:240], value=number, unit=unit, method=method[:120],
            source_reference=reference or {},
        ))

    for metric in analytics.metrics:
        add(metric.label, metric.value, metric.unit, metric.statistic, metric.source_reference)
    for table in analytics.comparison_tables:
        for row in table.rows:
            dimension_value = row.get(table.dimension, "")
            add(
                f"{table.measure} {table.dimension} {dimension_value}",
                row.get(table.measure), table.unit, table.aggregation, table.source_reference,
            )
    for chart in analytics.charts:
        if chart.chart_type not in {"bar", "line"}:
            continue
        for series in chart.series:
            for label, value in zip(chart.labels, series.data):
                add(
                    f"{series.name} {chart.title} {label}", value, chart.unit,
                    chart.aggregation, chart.source_reference,
                )
    return results


def calculate_document_statistics(document: StoredDocument) -> CalculateStatisticsOutput:
    if document.analytics is not None:
        analytics = AnalyticsResponse.model_validate(document.analytics)
    else:
        # Import lazily so the tool interface remains importable without loading
        # analytics' optional native dependencies until calculation is requested.
        from backend.analytics.data_profiler import profile_document

        analytics = profile_document(document.tables, document.source_passages)

    warnings = list(analytics.warnings)
    if document.warnings:
        warnings.extend(document.warnings)
    return CalculateStatisticsOutput(
        document_id=document.document_id,
        status=analytics.status,
        analytics=analytics,
        calculations=_numeric_results(analytics),
        input_table_count=min(len(document.tables), 12),
        input_passage_count=min(len(document.source_passages), 50_000),
        input_scope="Extracted tables and explicitly labeled numeric passages",
        warnings=list(dict.fromkeys(warnings))[:32],
    )


def make_calculate_statistics_tool(
    *, store: DocumentStore, allowed_document_id: str,
) -> ToolDefinition[CalculateStatisticsInput, CalculateStatisticsOutput]:
    def handler(request: CalculateStatisticsInput) -> CalculateStatisticsOutput:
        document = require_scoped_document(
            store,
            allowed_document_id=allowed_document_id,
            requested_document_id=request.document_id,
        )
        return calculate_document_statistics(document)

    return ToolDefinition("calculate_statistics", CalculateStatisticsInput, CalculateStatisticsOutput, handler)
