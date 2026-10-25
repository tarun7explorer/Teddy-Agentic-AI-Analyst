"""Validated analytics payload returned by the document API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class ColumnProfile(BaseModel):
    name: str
    data_type: Literal["numeric", "date", "categorical", "text", "unknown"]
    value_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    unit: str | None = None


class ChartSeries(BaseModel):
    name: str
    data: list[FiniteFloat] = Field(max_length=100)


class ChartSpec(BaseModel):
    chart_id: str
    chart_type: Literal["bar", "line", "doughnut", "histogram"]
    title: str
    x_axis_label: str
    y_axis_label: str
    unit: str | None = None
    aggregation: str
    labels: list[str] = Field(min_length=2, max_length=100)
    series: list[ChartSeries] = Field(min_length=1, max_length=6)
    source_reference: dict[str, Any] = Field(default_factory=dict)
    underlying_data: list[dict[str, Any]] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_chart_data_shape(self):
        if any(len(series.data) != len(self.labels) for series in self.series):
            raise ValueError("Each chart series must have one value for every label.")
        return self


class KpiMetric(BaseModel):
    metric_id: str
    label: str
    value: FiniteFloat
    unit: str | None = None
    statistic: Literal["mean", "median", "minimum", "maximum"]
    source_column: str
    source_reference: dict[str, Any] = Field(default_factory=dict)


class ComparisonTable(BaseModel):
    title: str
    dimension: str
    measure: str
    aggregation: str
    unit: str | None = None
    rows: list[dict[str, Any]] = Field(max_length=100)
    source_reference: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    date: str
    event: str
    source_reference: dict[str, Any] = Field(default_factory=dict)


class TableProfile(BaseModel):
    table_name: str
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    source_reference: dict[str, Any] = Field(default_factory=dict)
    columns: list[ColumnProfile] = Field(max_length=100)


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["available", "no_suitable_data"]
    charts: list[ChartSpec] = Field(max_length=8)
    metrics: list[KpiMetric] = Field(max_length=12)
    comparison_tables: list[ComparisonTable] = Field(max_length=8)
    timelines: list[TimelineEvent] = Field(max_length=100)
    profiles: list[TableProfile] = Field(max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=30)
