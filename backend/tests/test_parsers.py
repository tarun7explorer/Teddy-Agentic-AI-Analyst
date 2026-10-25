from backend.parsers.csv_parser import parse_csv
from backend.parsers.text_parser import parse_text


def test_csv_parser_preserves_row_sources_and_table_data(tmp_path):
    source = tmp_path / "rows.csv"
    source.write_text("Year,Revenue\n2025,42\n", encoding="utf-8")

    parsed = parse_csv(source)

    assert parsed.tables[0]["rows"] == [{"Year": "2025", "Revenue": "42"}]
    assert parsed.source_passages[0]["reference"] == {"type": "csv", "row_start": 2, "row_end": 2}


def test_text_parser_builds_line_reference(tmp_path):
    source = tmp_path / "memo.txt"
    source.write_text("first line\nsecond line", encoding="utf-8")

    parsed = parse_text(source)

    assert parsed.extracted_text == "first line\nsecond line"
    assert parsed.source_references == [{"type": "text", "line_start": 1, "line_end": 2}]
