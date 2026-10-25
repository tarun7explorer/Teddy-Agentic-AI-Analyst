from backend.analytics.data_profiler import profile_document, profile_tables


def test_numeric_aggregation_matches_chart_and_comparison_data():
    result = profile_tables([{
        "name": "Regional sales",
        "columns": ["Region", "Sales"],
        "rows": [
            {"Region": "North", "Sales": "10"},
            {"Region": "North", "Sales": "20"},
            {"Region": "South", "Sales": "5"},
            {"Region": "South", "Sales": "15"},
        ],
        "source_reference": {"type": "sheet", "sheet": "Q1"},
    }])

    bar = next(chart for chart in result.charts if chart.chart_type == "bar")
    assert bar.aggregation == "sum"
    assert bar.labels == ["North", "South"]
    assert bar.series[0].data == [30.0, 20.0]
    assert [row["Sales"] for row in bar.underlying_data] == bar.series[0].data
    assert bar.source_reference == {"type": "sheet", "sheet": "Q1"}
    assert result.comparison_tables[0].rows == bar.underlying_data


def test_date_columns_select_sorted_line_trend():
    result = profile_tables([{
        "name": "Yearly revenue",
        "columns": ["Year", "Revenue"],
        "rows": [
            {"Year": 2024, "Revenue": 125},
            {"Year": 2022, "Revenue": 90},
            {"Year": 2023, "Revenue": 110},
        ],
    }])

    trend = next(chart for chart in result.charts if chart.chart_type == "line")
    assert trend.labels == ["2022-01-01", "2023-01-01", "2024-01-01"]
    assert trend.series[0].data == [90.0, 110.0, 125.0]


def test_missing_and_invalid_numeric_cells_are_reported_and_excluded():
    result = profile_tables([{
        "name": "Costs",
        "columns": ["Department", "Cost"],
        "rows": [
            {"Department": "A", "Cost": "10"},
            {"Department": "A", "Cost": None},
            {"Department": "B", "Cost": "20"},
            {"Department": "B", "Cost": "not reported"},
            {"Department": "C", "Cost": "30"},
        ],
    }])

    cost = next(column for column in result.profiles[0].columns if column.name == "Cost")
    assert cost.data_type == "numeric"
    assert cost.value_count == 3
    assert cost.missing_count == 2
    assert any("excluded from calculations" in warning for warning in result.warnings)
    cost_chart = next(chart for chart in result.charts if chart.title == "Sum Cost by Department")
    assert cost_chart.series[0].data == [10.0, 20.0, 30.0]


def test_mean_is_explicit_for_nonadditive_measure():
    result = profile_tables([{
        "name": "Quality score",
        "columns": ["Team", "Score"],
        "rows": [
            {"Team": "A", "Score": 2}, {"Team": "A", "Score": 4},
            {"Team": "B", "Score": 8}, {"Team": "B", "Score": 10},
        ],
    }])

    comparison = result.comparison_tables[0]
    assert comparison.aggregation == "mean"
    assert [row["Score"] for row in comparison.rows] == [3.0, 9.0]


def test_semantic_categories_get_meaningful_proportions():
    result = profile_tables([{
        "name": "Status counts",
        "columns": ["Status"],
        "rows": [{"Status": "Open"}] * 4 + [{"Status": "Closed"}] * 2,
    }])

    chart = next(chart for chart in result.charts if chart.chart_type == "doughnut")
    assert chart.labels == ["Open", "Closed"]
    assert chart.series[0].data == [4.0, 2.0]
    assert sum(chart.series[0].data) == 6


def test_histogram_counts_match_observations():
    result = profile_tables([{
        "name": "Measurements",
        "columns": ["Measurement"],
        "rows": [{"Measurement": value} for value in [1, 2, 3, 4, 5, 6, 7, 8]],
    }])

    histogram = next(chart for chart in result.charts if chart.chart_type == "histogram")
    assert sum(histogram.series[0].data) == 8
    assert sum(row["row_count"] for row in histogram.underlying_data) == 8


def test_timeline_uses_extracted_dates_and_event_names():
    result = profile_tables([{
        "name": "Milestones",
        "columns": ["Date", "Event"],
        "rows": [
            {"Date": "2025-04-10", "Event": "Launch"},
            {"Date": "2025-02-02", "Event": "Review"},
        ],
    }])

    assert [event.event for event in result.timelines] == ["Review", "Launch"]
    assert [event.date for event in result.timelines] == ["2025-02-02", "2025-04-10"]


def test_text_only_and_unsupported_data_do_not_create_charts():
    result = profile_tables([{
        "name": "Notes",
        "columns": ["Description"],
        "rows": [{"Description": "No numeric data"}, {"Description": "Only prose"}],
    }])

    assert result.status == "no_suitable_data"
    assert result.charts == []
    assert result.metrics == []
    assert any("No chart-ready" in warning for warning in result.warnings)


def test_explicit_labeled_values_in_document_text_can_support_a_chart():
    result = profile_document([], [{
        "source_id": "pdf-page-4",
        "reference": {"type": "page", "page": 4},
        "text": "Revenue: $120\nExpenses: $80\nProfit: $40",
    }])

    chart = next(chart for chart in result.charts if chart.chart_type == "bar")
    assert chart.source_reference == {"type": "page", "page": 4}
    assert chart.series[0].data == [120.0, 80.0, 40.0]
    assert chart.unit == "$"


def test_unlabeled_prose_numbers_are_not_charted():
    result = profile_document([], [{
        "source_id": "text-lines-1",
        "reference": {"type": "text", "line_start": 1},
        "text": "We reviewed 12 projects and found 3 improvements. The result was positive.",
    }])

    assert result.status == "no_suitable_data"
    assert result.charts == []


def test_currency_unit_is_preserved_and_mixed_currencies_are_not_aggregated():
    result = profile_tables([{
        "name": "Revenue",
        "columns": ["Revenue"],
        "rows": [{"Revenue": "$1,250"}, {"Revenue": "$2,000"}],
    }])
    metric = next(metric for metric in result.metrics if metric.statistic == "mean")
    assert metric.value == 1625.0
    assert metric.unit == "$"

    mixed = profile_tables([{
        "name": "Mixed currencies",
        "columns": ["Amount"],
        "rows": [{"Amount": "$100"}, {"Amount": "€200"}],
    }])
    assert mixed.charts == []
    assert mixed.metrics == []
