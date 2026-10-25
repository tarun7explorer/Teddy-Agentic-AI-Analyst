"""Numeric parsing, summary calculations, and explicit group aggregation."""

import math
import re
from typing import Any

import pandas as pd


MISSING_MARKERS = {"", "na", "n/a", "null", "none", "nan", "-", "—"}
ADDITIVE_HINTS = ("revenue", "sales", "amount", "cost", "quantity", "count", "units", "total", "volume")


def clean_missing(series: pd.Series) -> pd.Series:
    return series.map(lambda value: pd.NA if value is None or (isinstance(value, str) and value.strip().casefold() in MISSING_MARKERS) else value)


def numeric_series(series: pd.Series) -> tuple[pd.Series, str | None, float]:
    """Parse common currency/percent strings and report the nonmissing parse ratio."""
    cleaned = clean_missing(series)
    non_missing = cleaned.dropna()
    if non_missing.empty:
        return pd.Series(index=series.index, dtype="float64"), None, 0.0
    if pd.api.types.is_numeric_dtype(non_missing):
        values = pd.to_numeric(cleaned, errors="coerce").astype("float64")
        return values.where(values.map(math.isfinite)), None, 1.0

    strings = non_missing.astype(str).str.strip()
    percent_flags = strings.str.endswith("%")
    if percent_flags.any() and not percent_flags.all():
        return pd.Series(index=series.index, dtype="float64"), None, 0.0
    currency_symbols = set("".join(strings.str.extract(r"([$€£])", expand=False).dropna().tolist()))
    if len(currency_symbols) > 1:
        return pd.Series(index=series.index, dtype="float64"), None, 0.0
    unit = "%" if percent_flags.all() else (next(iter(currency_symbols)) if len(currency_symbols) == 1 else None)

    def parse(value: Any) -> float | None:
        if pd.isna(value):
            return None
        text = str(value).strip()
        negative = text.startswith("(") and text.endswith(")")
        text = text.strip("() ").replace(",", "")
        text = re.sub(r"[$€£%\s]", "", text)
        try:
            number = float(text)
        except ValueError:
            return None
        if negative:
            number = -abs(number)
        return number if math.isfinite(number) else None

    values = cleaned.map(parse).astype("float64")
    return values, unit, float(values.notna().sum() / len(non_missing))


def aggregation_for(column_name: str) -> str:
    lowered = column_name.casefold()
    return "sum" if any(hint in lowered for hint in ADDITIVE_HINTS) else "mean"


def aggregate_by_category(
    frame: pd.DataFrame,
    category_column: str,
    values: pd.Series,
    value_column: str,
    aggregation: str,
) -> pd.DataFrame:
    data = pd.DataFrame({"category": frame[category_column].astype("string"), "value": values})
    data = data.dropna(subset=["category", "value"])
    grouped = data.groupby("category", sort=False)["value"]
    result = grouped.sum() if aggregation == "sum" else grouped.mean()
    return result.rename_axis(category_column).reset_index(name=value_column)
