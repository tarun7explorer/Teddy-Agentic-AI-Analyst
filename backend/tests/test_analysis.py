import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.config import settings
from backend.main import app
from backend.services import ai_provider, summary_service
from backend.storage.document_store import DocumentStore


SOURCE_TEXT = "Revenue reached 42 million in 2025, according to the annual report."


@pytest.fixture
def ai_client(tmp_path, monkeypatch):
    store = DocumentStore(tmp_path / "uploads", ttl_minutes=30)
    app.dependency_overrides[documents.get_document_store] = lambda: store
    monkeypatch.setattr(settings, "max_upload_size_mb", 10)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def valid_output(source_id="text-lines-1", quote="Revenue reached 42 million in 2025"):
    evidence = [{"source_id": source_id, "quote": quote}]
    return {
        "five_line_summary": [
            {"text": f"Verified summary point {index}.", "evidence": evidence}
            for index in range(1, 6)
        ],
        "detailed_summary": {
            "text": "The report states revenue reached 42 million in 2025.",
            "evidence": evidence,
        },
        "key_takeaways": [
            {"text": "Revenue was 42 million in 2025.", "evidence": evidence},
            {"text": "This unsupported claim must be omitted.", "evidence": [{"source_id": "invented", "quote": "not in source"}]},
        ],
        "important_entities": [
            {"text": "42 million in 2025", "category": "figure", "evidence": evidence},
        ],
        "risks": [],
        "decisions": [],
        "action_items": [],
    }


def upload_text(client):
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("annual.txt", SOURCE_TEXT.encode("utf-8"))},
    )
    assert response.status_code == 201
    return response.json()["document_id"]


def test_structured_analysis_is_validated_and_cached(ai_client, monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    calls = []

    async def fake_complete_json(**_kwargs):
        calls.append(1)
        return valid_output()

    monkeypatch.setattr(summary_service.provider, "complete_json", fake_complete_json)
    document_id = upload_text(ai_client)

    first = ai_client.post(f"/api/v1/documents/{document_id}/analyze")
    second = ai_client.post(f"/api/v1/documents/{document_id}/analyze")

    assert first.status_code == 200
    assert len(first.json()["five_line_summary"]) == 5
    assert first.json()["model"] == settings.nvidia_nim_model
    assert second.json() == first.json()
    assert len(calls) == 1


def test_invalid_model_output_returns_safe_error(ai_client, monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")

    async def fake_complete_json(**_kwargs):
        return {"five_line_summary": [{"text": "Only one line"}]}

    monkeypatch.setattr(summary_service.provider, "complete_json", fake_complete_json)
    document_id = upload_text(ai_client)

    response = ai_client.post(f"/api/v1/documents/{document_id}/analyze")

    assert response.status_code == 502
    assert "required analysis format" in response.json()["detail"]


def test_missing_credentials_do_not_break_upload(ai_client):
    document_id = upload_text(ai_client)
    response = ai_client.post(f"/api/v1/documents/{document_id}/analyze")
    results = ai_client.get(f"/api/v1/documents/{document_id}/results")

    assert response.status_code == 503
    assert "NVIDIA_NIM_API_KEY" in response.json()["detail"]
    assert results.status_code == 200
    assert results.json()["extracted_text"] == SOURCE_TEXT


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_phrase"),
    [
        ("timeout", 504, "took too long"),
        ("rate_limit", 429, "rate limiting"),
    ],
)
def test_provider_timeout_and_rate_limit_are_mapped(ai_client, monkeypatch, failure, expected_status, expected_phrase):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            if failure == "timeout":
                raise httpx.ReadTimeout("mock timeout")
            return httpx.Response(
                429,
                json={"error": "rate limited"},
                request=httpx.Request("POST", "https://nim.example/v1/chat/completions"),
            )

    monkeypatch.setattr(ai_provider.httpx, "AsyncClient", lambda **_kwargs: MockClient())
    document_id = upload_text(ai_client)

    response = ai_client.post(f"/api/v1/documents/{document_id}/analyze")

    assert response.status_code == expected_status
    assert expected_phrase in response.json()["detail"]


def test_source_quotes_and_references_are_verified(ai_client, monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    output = valid_output()
    output["five_line_summary"][0]["evidence"].append(
        {"source_id": "made-up-source", "quote": "fabricated quote"}
    )

    async def fake_complete_json(**_kwargs):
        return output

    monkeypatch.setattr(summary_service.provider, "complete_json", fake_complete_json)
    document_id = upload_text(ai_client)

    response = ai_client.post(f"/api/v1/documents/{document_id}/analyze")

    assert response.status_code == 200
    first_citation = response.json()["five_line_summary"][0]["citations"][0]
    assert first_citation["source_id"] == "text-lines-1"
    assert first_citation["reference"]["type"] == "text"
    assert first_citation["quote"] in SOURCE_TEXT
    assert len(response.json()["key_takeaways"]) == 1


def test_page_citation_uses_parser_page_reference(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")

    async def fake_complete_json(**_kwargs):
        return valid_output("pdf-page-3", "Revenue reached 42 million in 2025")

    monkeypatch.setattr(summary_service.provider, "complete_json", fake_complete_json)
    source = [{
        "source_id": "pdf-page-3",
        "reference": {"type": "page", "page": 3},
        "text": SOURCE_TEXT,
    }]

    async def run():
        return await summary_service.analyze_document(
            document_id="doc-id",
            source_passages=source,
            extracted_text=SOURCE_TEXT,
        )

    import asyncio
    response = asyncio.run(run())

    assert response.five_line_summary[0].citations[0].reference == {"type": "page", "page": 3}
