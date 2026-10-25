from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.analytics.schemas import AnalyticsResponse
from backend.api import documents
from backend.config import NVIDIA_APPROVED_BASE_URL, settings
from backend.main import app
from backend.parsers.models import ExtractionResult
from backend.rag.chunker import build_document_chunks
from backend.services import summary_service
from backend.services.ai_service import AIQuotaError
from backend.storage.document_store import DocumentStore
from backend.storage.temporary_storage import StoredDocument


class MemoryDocumentStore(DocumentStore):
    """Avoid filesystem side effects while exercising document API contracts."""

    def __init__(self):
        super().__init__(Path("unused-test-store"), ttl_minutes=30)

    def cleanup_expired(self):
        return 0

    def new_temp_path(self, document_id, extension):
        return Path("unused-test-upload")


@pytest.fixture
def client_store():
    store = MemoryDocumentStore()
    app.dependency_overrides[documents.get_document_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


def make_document(document_id, text, *, analytics=None, warnings=None):
    references = [{"type": "text", "line": 1}]
    passages = [{"source_id": "text-lines-1", "reference": references[0], "text": text}]
    return StoredDocument(
        document_id=document_id,
        original_filename="report.txt",
        detected_file_type="txt",
        file_size=len(text),
        status="completed",
        extracted_text=text,
        tables=[],
        source_references=references,
        warnings=warnings or [],
        source_passages=passages,
        chat_chunks=build_document_chunks(passages, text),
        created_at=1.0,
        expires_at=9_999_999_999.0,
        temp_path=Path("not-created.txt"),
        analytics=analytics or AnalyticsResponse(
            status="no_suitable_data", charts=[], metrics=[], comparison_tables=[],
            timelines=[], profiles=[],
        ).model_dump(mode="json"),
    )


def upload_text(client, name="report.txt", text="Revenue reached 42 million in the annual report."):
    response = client.post("/api/v1/documents/upload", files={"file": (name, text.encode("utf-8"))})
    assert response.status_code == 201
    return response.json()


def summary_payload(source_id="text-lines-1", quote="Revenue reached 42 million"):
    evidence = [{"source_id": source_id, "quote": quote}]
    summary_words = ["first", "second", "third", "fourth", "fifth"]
    return {
        "five_line_summary": [{"text": f"The {word} finding is reported.", "evidence": evidence} for word in summary_words],
        "detailed_summary": {"text": "The report states that revenue reached 42 million.", "evidence": evidence},
        "key_takeaways": [], "important_entities": [], "risks": [], "decisions": [], "action_items": [],
    }


def test_upload_exposes_assessment_provider_status_analytics_and_warnings(client_store, monkeypatch):
    client, _store = client_store

    async def save_upload(_upload, _path, _max_bytes):
        return len(b"Revenue reached 42 million")

    passage = {"source_id": "text-lines-1", "reference": {"type": "text", "line": 1}, "text": "Revenue reached 42 million"}
    extraction = ExtractionResult(
        extracted_text=passage["text"], source_passages=[passage],
        source_references=[passage["reference"]], warnings=["Some lines could not be extracted."],
    )
    chunks = build_document_chunks(extraction.source_passages, extraction.extracted_text)
    analytics = AnalyticsResponse(
        status="no_suitable_data", charts=[], metrics=[], comparison_tables=[], timelines=[], profiles=[],
    )
    monkeypatch.setattr(documents, "_save_upload", save_upload)
    monkeypatch.setattr(documents, "_process_document", lambda *_args: ("txt", extraction, chunks, analytics))

    uploaded = upload_text(client)
    metadata = uploaded["workflow"]
    assert metadata["status"] == "not_started"
    assert metadata["document_assessment"]["document_type"] == "txt"
    assert metadata["document_assessment"]["extracted_char_count"] > 0
    assert metadata["provider_status"]["provider"] == "none"
    assert metadata["provider_status"]["available"] is False
    assert metadata["warnings"][0]["code"] == "partial_extraction"
    assert "analytics" in metadata
    result = client.get(f"/api/v1/documents/{uploaded['document_id']}/results")
    assert result.json()["workflow"] == metadata


def test_analysis_with_mocked_ai_returns_additive_workflow_and_cached_compatible_payload(client_store, monkeypatch):
    client, store = client_store
    monkeypatch.setattr(settings, "ai_provider", "nvidia_nim")
    monkeypatch.setattr(settings, "allow_paid_apis", False)
    monkeypatch.setattr(settings, "nvidia_nim_free_access_confirmed", True)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_nim_model", "mock-free-model")
    monkeypatch.setattr(settings, "nvidia_nim_api_base_url", NVIDIA_APPROVED_BASE_URL)
    store._documents["doc-analysis"] = make_document("doc-analysis", "Revenue reached 42 million in the annual report.")

    async def mocked_provider(**_kwargs):
        return summary_payload()

    monkeypatch.setattr(summary_service.provider, "complete_json", mocked_provider)
    url = "/api/v1/documents/doc-analysis/analyze"
    first = client.post(url)
    second = client.post(url)
    payload = first.json()
    assert first.status_code == 200
    assert len(payload["five_line_summary"]) == 5
    assert payload["workflow"]["document_assessment"]["supported_type"] is True
    assert payload["workflow"]["analytics"] is not None
    assert payload["workflow"]["verification"]["claims_checked"] >= 6
    assert payload["workflow"]["verification"]["status"] == "partial", payload["workflow"]["verification"]
    assert second.json() == payload


def test_ai_disabled_returns_stable_code_and_preserves_local_results_and_export(client_store, monkeypatch):
    client, store = client_store
    monkeypatch.setattr(settings, "ai_provider", "none")
    store._documents["doc-local"] = make_document("doc-local", "Valid extracted text remains available.")
    response = client.post("/api/v1/documents/doc-local/analyze")
    result = client.get("/api/v1/documents/doc-local/results").json()
    exported = client.get("/api/v1/documents/doc-local/export/report.pdf")
    assert response.status_code == 503
    assert response.headers["x-teddy-error-code"] == "ai_disabled"
    assert result["workflow"]["partial_result"] is True
    assert result["analytics"] is not None
    assert result["workflow"]["provider_status"]["available"] is False
    assert exported.status_code == 200
    assert exported.content.startswith(b"%PDF")


def test_provider_quota_failure_is_stable_and_does_not_fallback(client_store, monkeypatch):
    client, store = client_store
    monkeypatch.setattr(settings, "ai_provider", "nvidia_nim")
    monkeypatch.setattr(settings, "allow_paid_apis", False)
    monkeypatch.setattr(settings, "nvidia_nim_free_access_confirmed", True)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_nim_model", "mock-free-model")
    monkeypatch.setattr(settings, "nvidia_nim_api_base_url", NVIDIA_APPROVED_BASE_URL)
    store._documents["doc-quota"] = make_document("doc-quota", "Revenue reached 42 million in the annual report.")
    calls = []

    async def exhausted(**_kwargs):
        calls.append("selected-provider")
        raise AIQuotaError("Configured free quota is exhausted. No fallback was attempted.")

    monkeypatch.setattr(summary_service.provider, "complete_json", exhausted)
    response = client.post("/api/v1/documents/doc-quota/analyze")
    result = client.get("/api/v1/documents/doc-quota/results").json()
    assert response.status_code == 429
    assert response.headers["x-teddy-error-code"] == "provider_quota_exhausted"
    assert calls == ["selected-provider"]
    assert result["analytics"] is not None
    assert result["workflow"]["error_code"] == "provider_quota_exhausted"


def test_chat_insufficient_evidence_and_cross_document_isolation(client_store, monkeypatch):
    client, store = client_store
    store._documents["doc-first"] = make_document(
        "doc-first", "The first report is about revenue and says it reached 42 million.",
    )
    store._documents["doc-second"] = make_document(
        "doc-second", "The second report contains a confidential passphrase: orange telescope.",
    )
    monkeypatch.setattr(settings, "ai_provider", "none")

    async def no_ai(**_kwargs):
        raise AssertionError("Irrelevant evidence must not trigger AI generation.")

    monkeypatch.setattr(summary_service.provider, "complete_json", no_ai)
    response = client.post("/api/v1/documents/doc-first/chat", json={
        "question": "What is the orange telescope passphrase?",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert "narrower question" in response.json()["answer"]
    assert all("orange telescope" not in source["quote"] for source in response.json()["sources"])
    assert response.json()["workflow"]["verification"]["status"] == "not_run"


def test_unknown_and_malformed_document_ids_are_rejected(client_store):
    client, _store = client_store
    assert client.get("/api/v1/documents/not-a-real-id/results").status_code == 404
    long_id = "x" * 161
    assert client.get(f"/api/v1/documents/{long_id}/results").status_code == 422
