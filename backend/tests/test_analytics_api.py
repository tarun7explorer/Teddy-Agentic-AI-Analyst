from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api import documents
from backend.main import app
from backend.storage.document_store import DocumentStore


@pytest.fixture
def client(tmp_path):
    store = DocumentStore(tmp_path / "uploads", ttl_minutes=30)
    app.dependency_overrides[documents.get_document_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def create_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Monthly"
    sheet.append(["Month", "Revenue"])
    sheet.append(["2025-01-01", 10])
    sheet.append(["2025-02-01", 15])
    sheet.append(["2025-03-01", 22])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_upload_results_include_calculated_analytics(client):
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("monthly.xlsx", create_workbook())},
    )

    assert upload.status_code == 201
    document_id = upload.json()["document_id"]
    analytics = upload.json()["analytics"]
    assert analytics["status"] == "available"
    trend = next(chart for chart in analytics["charts"] if chart["chart_type"] == "line")
    assert trend["labels"] == ["2025-01-01", "2025-02-01", "2025-03-01"]
    assert trend["series"][0]["data"] == [10.0, 15.0, 22.0]

    endpoint_result = client.get(f"/api/v1/documents/{document_id}/analytics")
    assert endpoint_result.status_code == 200
    assert endpoint_result.json() == analytics


def test_text_upload_reports_no_suitable_chart_data(client):
    upload = client.post("/api/v1/documents/upload", files={"file": ("notes.txt", b"Just prose, no table.")})

    assert upload.status_code == 201
    assert upload.json()["analytics"]["status"] == "no_suitable_data"
    assert upload.json()["analytics"]["charts"] == []


def test_unknown_document_analytics_returns_404(client):
    response = client.get("/api/v1/documents/unknown/analytics")

    assert response.status_code == 404
