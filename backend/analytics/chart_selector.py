"""Conservative chart selection over profiled tabular data."""

import math
from typing import Any

import numpy as np
import pandas as pd

from backend.analytics.schemas import ChartSpec, ChartSeries, ComparisonTable, KpiMetric, TimelineEvent
from backend.analytics.statistics import aggregate_by_category, aggregation_for


MAX_CHARTS = 8
MAX_CATEGORIES = 20
MAX_HISTOGRAM_BINS = 12
MAX_TIMELINE_EVENTS = 100
SEMANTIC_CATEGORY_HINTS = ("category", "status", "type", "segment", "region", "product", "department", "channel")


def _safe_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _unique_chart_id(table_index: int, label: str, chart_type: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in label).strip("-")
    return f"table-{table_index}-{chart_type}-{cleaned[:36] or 'data'}"


def select_charts(profile: dict[str, Any]) -> tuple[list[ChartSpec], list[KpiMetric], list[ComparisonTable], list[TimelineEvent]]:
    frame: pd.DataFrame = profile["frame"]
    table_name: str = profile["table_name"]
    table_index: int = profile["table_index"]
    source_reference: dict = profile["source_reference"]
    numeric: dict[str, tuple[pd.Series, str | None]] = profile["numeric_columns"]
    dates: dict[str, pd.Series] = profile["date_columns"]
    categorical: list[str] = profile["categorical_columns"]
    charts: list[ChartSpec] = []
    metrics: list[KpiMetric] = []
    comparisons: list[ComparisonTable] = []
    timelines: list[TimelineEvent] = []

    for column_name, (values, unit) in numeric.items():
        finite = values.dropna()
        if finite.empty:
            continue
        for statistic, label, calculated in (
            ("mean", "Average", finite.mean()),
            ("median", "Median", finite.median()),
            ("minimum", "Minimum", finite.min()),
            ("maximum", "Maximum", finite.max()),
        ):
            result = _safe_float(calculated)
            if result is None:
                continue
            metrics.append(KpiMetric(
                metric_id=f"table-{table_index}-{statistic}-{len(metrics)}",
                label=f"{label} {column_name}",
                value=round(result, 4),
                unit=unit,
                statistic=statistic,
                source_column=column_name,
                source_reference=source_reference,
            ))
            if len(metrics) >= 12:
                break
        if len(metrics) >= 12:
            break

    # Dates plus numeric values make a time series; duplicate periods use explicit aggregation.
    for date_column, date_values in dates.items():
        for value_column, (values, unit) in numeric.items():
            valid = pd.DataFrame({"date": date_values, "value": values}).dropna()
            if valid["date"].nunique() < 2:
                continue
            aggregation = aggregation_for(value_column)
            grouped = valid.groupby("date", sort=True)["value"]
            grouped_values = grouped.sum() if aggregation == "sum" else grouped.mean()
            labels = [value.strftime("%Y-%m-%d") for value in grouped_values.index]
            data = [_safe_float(value) for value in grouped_values.tolist()]
            if len(labels) < 2 or any(value is None for value in data):
                continue
            charts.append(ChartSpec(
                chart_id=_unique_chart_id(table_index, f"{date_column}-{value_column}", "line"),
                chart_type="line",
                title=f"{value_column} over time",
                x_axis_label=date_column,
                y_axis_label=f"{aggregation.title()} {value_column}" + (f" ({unit})" if unit else ""),
                unit=unit,
                aggregation=f"{aggregation} by {date_column}",
                labels=labels[:100],
                series=[ChartSeries(name=value_column, data=[round(value, 4) for value in data[:100]])],
                source_reference=source_reference,
                underlying_data=[{"date": label, value_column: value} for label, value in zip(labels[:100], data[:100])],
            ))
            if len(charts) >= MAX_CHARTS:
                return charts, metrics, comparisons, timelines

    # Categorical comparisons only use a modest number of groups and state their aggregation.
    for category_column in categorical:
        unique_values = frame[category_column].dropna().astype(str).unique()
        if not 2 <= len(unique_values) <= MAX_CATEGORIES:
            continue
        for value_column, (values, unit) in numeric.items():
            aggregation = aggregation_for(value_column)
            aggregated = aggregate_by_category(frame, category_column, values, value_column, aggregation)
            if len(aggregated) < 2 or len(aggregated) > MAX_CATEGORIES:
                continue
            labels = aggregated[category_column].astype(str).tolist()
            data = [_safe_float(value) for value in aggregated[value_column].tolist()]
            if any(value is None for value in data):
                continue
            rows = [
                {category_column: label, value_column: round(value, 4), "aggregation": aggregation}
                for label, value in zip(labels, data)
            ]
            if not any(item.chart_type == "line" and item.series[0].name == value_column for item in charts):
                charts.append(ChartSpec(
                    chart_id=_unique_chart_id(table_index, f"{category_column}-{value_column}", "bar"),
                    chart_type="bar",
                    title=f"{aggregation.title()} {value_column} by {category_column}",
                    x_axis_label=category_column,
                    y_axis_label=f"{aggregation.title()} {value_column}" + (f" ({unit})" if unit else ""),
                    unit=unit,
                    aggregation=aggregation,
                    labels=labels,
                    series=[ChartSeries(name=value_column, data=[round(value, 4) for value in data])],
                    source_reference=source_reference,
                    underlying_data=rows,
                ))
            comparisons.append(ComparisonTable(
                title=f"{aggregation.title()} {value_column} by {category_column}",
                dimension=category_column,
                measure=value_column,
                aggregation=aggregation,
                unit=unit,
                rows=rows,
                source_reference=source_reference,
            ))
            if len(charts) >= MAX_CHARTS:
                return charts, metrics, comparisons, timelines

    # Doughnut charts are limited to semantically named categorical fields and positive totals.
    for category_column in categorical:
        if not any(hint in category_column.casefold() for hint in SEMANTIC_CATEGORY_HINTS):
            continue
        counts = frame[category_column].dropna().astype(str).value_counts()
        if not 2 <= len(counts) <= 6:
            continue
        labels = counts.index.tolist()
        data = [float(value) for value in counts.tolist()]
        if sum(data) <= 0:
            continue
        rows = [{category_column: label, "record_count": int(value)} for label, value in zip(labels, data)]
        charts.append(ChartSpec(
            chart_id=_unique_chart_id(table_index, category_column, "doughnut"),
            chart_type="doughnut",
            title=f"Record share by {category_column}",
            x_axis_label=category_column,
            y_axis_label="Records",
            unit="records",
            aggregation="record count; percentage is derived from these counts",
            labels=labels,
            series=[ChartSeries(name="Records", data=data)],
            source_reference=source_reference,
            underlying_data=rows,
        ))
        if len(charts) >= MAX_CHARTS:
            return charts, metrics, comparisons, timelines

    # Histograms need enough observations and distinct values to show a distribution.
    for value_column, (values, unit) in numeric.items():
        finite = values.dropna()
        if len(finite) < 5 or finite.nunique() < 3:
            continue
        bin_count = min(MAX_HISTOGRAM_BINS, max(3, int(math.sqrt(len(finite)))))
        counts, edges = np.histogram(finite.to_numpy(dtype=float), bins=bin_count)
        labels = [f"{edges[i]:g}–{edges[i + 1]:g}" for i in range(len(counts))]
        series_data = [int(value) for value in counts.tolist()]
        charts.append(ChartSpec(
            chart_id=_unique_chart_id(table_index, value_column, "histogram"),
            chart_type="histogram",
            title=f"Distribution of {value_column}",
            x_axis_label=f"{value_column} range" + (f" ({unit})" if unit else ""),
            y_axis_label="Number of rows",
            unit="rows",
            aggregation="frequency per equal-width bin",
            labels=labels,
            series=[ChartSeries(name="Rows", data=[float(value) for value in series_data])],
            source_reference=source_reference,
            underlying_data=[{"range": label, "row_count": count} for label, count in zip(labels, series_data)],
        ))
        if len(charts) >= MAX_CHARTS:
            return charts, metrics, comparisons, timelines

    # A timeline is useful when rows contain both date and event/name text.
    for date_column, date_values in dates.items():
        event_column = next((
            column for column in categorical
            if any(hint in column.casefold() for hint in ("event", "description", "milestone", "title", "name"))
        ), None)
        if not event_column:
            continue
        events = pd.DataFrame({"date": date_values, "event": frame[event_column].astype("string")}).dropna()
        events = events[events["event"].str.strip().ne("")].sort_values("date").head(MAX_TIMELINE_EVENTS)
        timelines.extend(
            TimelineEvent(date=row.date.strftime("%Y-%m-%d"), event=str(row.event), source_reference=source_reference)
            for row in events.itertuples(index=False)
        )
        break

    return charts, metrics, comparisons, timelines
