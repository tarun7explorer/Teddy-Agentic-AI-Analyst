import csv
from io import StringIO

import fitz
import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.main import app
from backend.storage.document_store import DocumentStore


@pytest.fixture
def client_store(tmp_path):
    store = DocumentStore(tmp_path / "uploads", ttl_minutes=30)
    app.dependency_overrides[documents.get_document_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


def upload(client, filename="report.txt", content="Quarterly report, revenue increased."):
    response = client.post("/api/v1/documents/upload", files={"file": (filename, content.encode())})
    assert response.status_code == 201
    return response.json()["document_id"]


def analysis(document_id, lead):
    citations = [{
        "source_id": "text-lines-1",
        "reference": {"type": "text", "line_start": 1, "line_end": 1},
        "quote": "Quarterly report, revenue increased.",
    }]
    return {
        "document_id": document_id,
        "five_line_summary": [{"text": f"{lead} Summary point {n}.", "citations": citations} for n in range(1, 6)],
        "detailed_summary": {"text": "Revenue increased in the quarterly report.", "citations": citations},
        "key_takeaways": [{"text": "Revenue increased.", "citations": citations}],
        "important_entities": [], "risks": [], "decisions": [], "action_items": [],
    }


def test_summary_export_is_document_scoped_and_requires_analysis(client_store):
    client, store = client_store
    first_id = upload(client, "first.txt")
    second_id = upload(client, "second.txt")
    store.save_analysis(first_id, analysis(first_id, "First only."))
    store.save_analysis(second_id, analysis(second_id, "Second only."))

    first = client.get(f"/api/v1/documents/{first_id}/export/summary.md")
    absent = client.get(f"/api/v1/documents/missing/export/summary.md")
    not_generated = upload(client, "pending.txt")
    pending = client.get(f"/api/v1/documents/{not_generated}/export/summary.md")

    assert first.status_code == 200
    assert "First only." in first.text and "Second only." not in first.text
    assert first.headers["content-disposition"].endswith('filename="first-summary.md"')
    assert "line_start: 1" in first.text
    assert absent.status_code == 404
    assert pending.status_code == 409
    assert "not available" in pending.json()["detail"]


def test_pdf_report_includes_summary_findings_statistics_charts_and_sources(client_store):
    client, store = client_store
    document_id = upload(client, "Annual Report <draft>.txt")
    record = store.get(document_id)
    store.save_analysis(document_id, analysis(document_id, "Annual report result."))
    record.analytics = {
        "metrics": [{"label": "Revenue", "statistic": "maximum", "value": 42, "unit": "USD", "source_reference": {"type": "csv", "row_start": 2}}],
        "charts": [{"title": "Revenue by year", "chart_type": "bar", "aggregation": "sum", "unit": "USD",
                    "source_reference": {"type": "sheet", "sheet": "Annual"}, "labels": ["2024", "2025"],
                    "series": [{"name": "Revenue", "data": [38, 42]}]}],
    }

    response = client.get(f"/api/v1/documents/{document_id}/export/report.pdf")

    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert "Annual_Report_draft-report.pdf" in response.headers["content-disposition"]
    pdf = fitz.open(stream=response.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)
    assert "Annual Report <draft>.txt" in text
    assert "Annual report result." in text
    assert "Revenue increased." in text
    assert "Revenue by year" in text and "2025" in text and "42" in text
    assert "line_start: 1" in text and "sheet: Annual" in text


def test_pdf_empty_analysis_and_analytics_are_explained(client_store):
    client, _store = client_store
    document_id = upload(client, "no-results.txt")
    response = client.get(f"/api/v1/documents/{document_id}/export/report.pdf")
    text = "\n".join(page.get_text() for page in fitz.open(stream=response.content, filetype="pdf"))
    assert response.status_code == 200
    assert "Summary unavailable" in text
    assert "No calculated statistics" in text
    assert "No supported charts" in text


def test_csv_export_keeps_negative_numbers_and_neutralizes_formula_cells(client_store):
    client, store = client_store
    document_id = upload(client)
    store.get(document_id).tables = [{
        "name": "Quarterly Sales", "columns": ["Quarter", "Revenue", "Note"],
        "rows": [{"Quarter": "Q1", "Revenue": -12, "Note": "ordinary"},
                 {"Quarter": "Q2", "Revenue": 42, "Note": "=HYPERLINK(\"https://example.invalid\")"}],
    }]

    response = client.get(f"/api/v1/documents/{document_id}/export/tables/0.csv")
    rows = list(csv.reader(StringIO(response.text)))
    assert response.status_code == 200
    assert "Quarterly_Sales.csv" in response.headers["content-disposition"]
    assert rows[0] == ["Quarter", "Revenue", "Note"]
    assert rows[1] == ["Q1", "-12", "ordinary"]
    assert rows[2][2].startswith("'=HYPERLINK")


def test_csv_array_rows_and_unknown_table_document_errors(client_store):
    client, store = client_store
    document_id = upload(client, "rows.txt")
    store.get(document_id).tables = [{"name": "rows", "rows": [["A", "B"], ["1", "2"]]}]
    response = client.get(f"/api/v1/documents/{document_id}/export/tables/0.csv")
    missing_table = client.get(f"/api/v1/documents/{document_id}/export/tables/4.csv")
    missing_document = client.get("/api/v1/documents/missing/export/report.pdf")
    assert list(csv.reader(StringIO(response.text))) == [["Column 1", "Column 2"], ["A", "B"], ["1", "2"]]
    assert missing_table.status_code == missing_document.status_code == 404


def test_delete_removes_source_file_and_export_access(client_store):
    client, store = client_store
    document_id = upload(client)
    store.save_analysis(document_id, analysis(document_id, "Scoped."))
    path = store.get(document_id).temp_path
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 200
    assert not path.exists()
    assert client.get(f"/api/v1/documents/{document_id}/export/report.pdf").status_code == 404


def test_pdf_generation_failure_is_safe(client_store, monkeypatch):
    client, _store = client_store
    document_id = upload(client)
    monkeypatch.setattr(documents, "report_pdf", lambda _record: (_ for _ in ()).throw(RuntimeError("secret detail")))
    response = client.get(f"/api/v1/documents/{document_id}/export/report.pdf")
    assert response.status_code == 500
    assert response.json()["detail"] == "The PDF report could not be generated."
    assert "secret detail" not in response.text
