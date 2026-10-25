"""Profile extracted table values and coordinate conservative analytics."""

import re
from typing import Any

import pandas as pd

from backend.analytics.chart_selector import select_charts
from backend.analytics.schemas import AnalyticsResponse, ColumnProfile, TableProfile
from backend.analytics.statistics import clean_missing, numeric_series
from backend.config import settings


MAX_TABLES = 12
MAX_COLUMNS = 100
DATE_NAME_HINTS = ("date", "time", "year", "month")
DATE_VALUE_PATTERN = re.compile(r"\d{1,4}[-/][A-Za-z0-9]{1,4}[-/]\d{1,4}")
EXPLICIT_VALUE_PATTERN = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 /()&._-]{1,59})\s*[:=]\s*([$€£]?\s*[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?)\s*$"
)


def _frame_from_table(table: dict[str, Any]) -> pd.DataFrame:
    rows = table.get("rows") or []
    columns = table.get("columns") or []
    if rows and isinstance(rows[0], list):
        if not columns:
            columns = [str(value).strip() or f"Column {index + 1}" for index, value in enumerate(rows[0])]
            rows = rows[1:]
        columns = columns[:MAX_COLUMNS]
        normalized = [list(row[:len(columns)]) + [None] * max(0, len(columns) - len(row)) for row in rows]
        return pd.DataFrame(normalized[: settings.max_table_rows], columns=columns)
    if rows and isinstance(rows[0], dict):
        frame = pd.DataFrame(rows[: settings.max_table_rows])
    else:
        frame = pd.DataFrame(columns=columns)
    if len(frame.columns) > MAX_COLUMNS:
        frame = frame.iloc[:, :MAX_COLUMNS]
    if len(frame.index) > settings.max_table_rows:
        frame = frame.iloc[: settings.max_table_rows]
    return frame


def _date_series(series: pd.Series, column_name: str) -> pd.Series | None:
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce")
    else:
        sample = series.dropna().astype(str).head(30)
        has_date_hint = any(hint in column_name.casefold() for hint in DATE_NAME_HINTS)
        has_date_values = any(DATE_VALUE_PATTERN.search(value) for value in sample)
        if not has_date_hint and not has_date_values:
            return None
        if column_name.casefold().strip() in {"year", "fiscal year", "calendar year"}:
            parsed = pd.to_datetime(series.astype("string"), errors="coerce", format="%Y")
        else:
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    valid = clean_missing(series).notna().sum()
    if valid < 2 or parsed.notna().sum() < 2:
        return None
    if parsed.notna().sum() / valid < 0.7:
        return None
    return parsed


def _profile_one_table(table: dict[str, Any], table_index: int) -> tuple[dict[str, Any] | None, TableProfile | None, list[str]]:
    frame = _frame_from_table(table)
    warnings: list[str] = []
    name = str(table.get("name") or f"Table {table_index + 1}")[:120]
    source_reference = table.get("source_reference") or {}
    if frame.empty or len(frame.columns) == 0:
        return None, None, [f"{name}: no tabular rows were available for profiling."]

    numeric_columns: dict[str, tuple[pd.Series, str | None]] = {}
    date_columns: dict[str, pd.Series] = {}
    categorical_columns: list[str] = []
    profiles: list[ColumnProfile] = []
    missing_found = False

    for column in frame.columns:
        column_name = str(column)[:120]
        series = clean_missing(frame[column])
        missing_count = int(series.isna().sum())
        missing_found |= missing_count > 0
        date_values = _date_series(series, column_name)
        values, unit, numeric_ratio = numeric_series(series)
        is_identifier = bool(re.search(r"(^id$|_id$|\bidentifier\b|postal|zip code)", column_name.casefold()))
        if date_values is not None and (any(hint in column_name.casefold() for hint in DATE_NAME_HINTS) or numeric_ratio < 0.9):
            date_columns[column_name] = date_values
            kind = "date"
            valid_dates = int(date_values.notna().sum())
            date_parse_failures = max(0, int(series.notna().sum()) - valid_dates)
            missing_count += date_parse_failures
            missing_found |= date_parse_failures > 0
            if date_parse_failures:
                warnings.append(f"{name}: unparseable dates in '{column_name}' were excluded from timelines.")
        elif numeric_ratio >= 0.7 and not is_identifier:
            numeric_columns[column_name] = (values, unit)
            kind = "numeric"
            valid_numeric = int(values.notna().sum())
            parse_failures = max(0, int(series.notna().sum()) - valid_numeric)
            missing_count += parse_failures
            missing_found |= parse_failures > 0
            if parse_failures:
                warnings.append(f"{name}: nonnumeric values in '{column_name}' were excluded from calculations.")
        else:
            distinct = int(series.nunique(dropna=True))
            if distinct <= MAX_COLUMNS and distinct <= 20:
                categorical_columns.append(column_name)
                kind = "categorical"
            else:
                kind = "text"
        profiles.append(ColumnProfile(
            name=column_name,
            data_type=kind,
            value_count=(
                int(values.notna().sum()) if kind == "numeric"
                else int(date_values.notna().sum()) if kind == "date"
                else int(series.notna().sum())
            ),
            missing_count=missing_count,
            distinct_count=(
                int(values.nunique(dropna=True)) if kind == "numeric"
                else int(date_values.nunique(dropna=True)) if kind == "date"
                else int(series.nunique(dropna=True))
            ),
            unit=unit if kind == "numeric" else None,
        ))

    if missing_found:
        warnings.append(f"{name}: missing values were excluded from relevant calculations.")
    profile = {
        "frame": frame,
        "table_name": name,
        "table_index": table_index,
        "source_reference": source_reference,
        "numeric_columns": numeric_columns,
        "date_columns": date_columns,
        "categorical_columns": categorical_columns,
    }
    public_profile = TableProfile(
        table_name=name,
        row_count=len(frame.index),
        column_count=len(frame.columns),
        source_reference=source_reference,
        columns=profiles,
    )
    return profile, public_profile, warnings


def profile_tables(tables: list[dict[str, Any]]) -> AnalyticsResponse:
    charts = []
    metrics = []
    comparisons = []
    timelines = []
    profiles = []
    warnings: list[str] = []

    if len(tables) > MAX_TABLES:
        warnings.append(f"Only the first {MAX_TABLES} extracted tables were profiled.")
    for table_index, table in enumerate(tables[:MAX_TABLES]):
        try:
            internal, public, table_warnings = _profile_one_table(table, table_index)
            warnings.extend(table_warnings)
            if internal is None or public is None:
                continue
            profiles.append(public)
            table_charts, table_metrics, table_comparisons, table_timelines = select_charts(internal)
            charts.extend(table_charts)
            metrics.extend(table_metrics)
            comparisons.extend(table_comparisons)
            timelines.extend(table_timelines)
        except Exception:
            # A malformed extracted table should not make document upload fail.
            warnings.append(f"{str(table.get('name') or f'Table {table_index + 1}')[:80]}: analytics could not be calculated safely.")

    charts = charts[:8]
    metrics = metrics[:12]
    comparisons = comparisons[:8]
    timelines = timelines[:100]
    status = "available" if charts or metrics or comparisons or timelines else "no_suitable_data"
    if status == "no_suitable_data":
        warnings.append("No chart-ready numeric or date data was found. No chart was generated.")
    return AnalyticsResponse(
        status=status,
        charts=charts,
        metrics=metrics,
        comparison_tables=comparisons,
        timelines=timelines,
        profiles=profiles,
        warnings=list(dict.fromkeys(warnings)),
    )


def _explicit_numeric_tables(source_passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract repeated, explicitly labelled numeric statements without guessing prose structure."""
    extracted: list[dict[str, Any]] = []
    excluded_labels = re.compile(r"\b(date|year|time|page|section|figure|identifier|\bid\b)\b", re.IGNORECASE)
    for passage in source_passages:
        pairs = []
        for line in str(passage.get("text", "")).splitlines():
            # Only complete label/value lines are treated as tabular data.
            match = EXPLICIT_VALUE_PATTERN.fullmatch(line.strip())
            if not match:
                continue
            label, raw_value = match.groups()
            if excluded_labels.search(label):
                continue
            value = raw_value.strip()
            # Four-digit years are context, not a measure to chart.
            numeric_text = re.sub(r"[$€£,%\s]", "", value).replace(",", "")
            try:
                number = float(numeric_text)
            except ValueError:
                continue
            if not number % 1 and 1800 <= number <= 2199 and not any(symbol in value for symbol in "$€£%"):
                continue
            unit = "%" if value.endswith("%") else next((symbol for symbol in "$€£" if symbol in value), "")
            pairs.append((label.strip(), value, unit))
        labels = [label for label, _, _ in pairs]
        units = {unit for _, _, unit in pairs}
        if len(set(labels)) < 3 or len(units) != 1:
            continue
        reference = passage.get("reference") or {"type": "document"}
        extracted.append({
            "name": "Explicit numeric statements",
            "columns": ["Metric", "Value"],
            "rows": [{"Metric": label, "Value": value} for label, value, _ in pairs[: settings.max_table_rows]],
            "source_reference": reference,
        })
    return extracted[:MAX_TABLES]


def profile_document(
    tables: list[dict[str, Any]],
    source_passages: list[dict[str, Any]],
) -> AnalyticsResponse:
    """Profile parsed tables plus only repeated, explicitly labelled text values."""
    additions = _explicit_numeric_tables(source_passages)
    return profile_tables([*tables, *additions])
