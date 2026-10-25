import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.config import settings
from backend.main import app
from backend.services import chat_service
from backend.services.ai_provider import AIProviderTimeout, AIRateLimitError
from backend.services.document_chunker import build_document_chunks
from backend.services.retriever import retrieve_relevant_chunks
from backend.storage.document_store import DocumentStore


CHAT_TEXT = "Quarterly report. Revenue was $42 million in 2025. Revenue was $38 million in 2024. Expenses were $31 million."


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    store = DocumentStore(tmp_path / "uploads", ttl_minutes=30)
    app.dependency_overrides[documents.get_document_store] = lambda: store
    monkeypatch.setattr(settings, "max_upload_size_mb", 10)
    monkeypatch.setattr(settings, "chat_max_question_chars", 1000)
    yield TestClient(app), store
    app.dependency_overrides.clear()


def upload_chat_document(client, content=CHAT_TEXT):
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("annual.txt", content.encode("utf-8"))},
    )
    assert response.status_code == 201
    return response.json()["document_id"]


def model_answer(quote, answer="Revenue was $42 million in 2025."):
    return {
        "answer": answer,
        "not_found": False,
        "evidence": [{"source_id": "text-lines-1", "quote": quote}],
    }


def test_chunking_preserves_source_reference_and_unique_chunk_ids(monkeypatch):
    monkeypatch.setattr(settings, "chat_chunk_chars", 240)
    monkeypatch.setattr(settings, "chat_chunk_overlap_chars", 30)
    source_text = "Quarterly revenue report. " * 35

    chunks = build_document_chunks([{
        "source_id": "pdf-page-7",
        "reference": {"type": "page", "page": 7},
        "text": source_text,
    }])

    assert len(chunks) > 1
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    assert all(chunk["reference"] == {"type": "page", "page": 7} for chunk in chunks)
    assert all(len(chunk["text"]) <= 240 for chunk in chunks)


def test_retrieval_prefers_relevant_source_passage():
    chunks = [
        {"chunk_id": "p1", "source_id": "p1", "reference": {"type": "page", "page": 1}, "text": "The document describes staffing plans."},
        {"chunk_id": "p2", "source_id": "p2", "reference": {"type": "page", "page": 2}, "text": "Revenue reached $42 million in 2025."},
    ]

    result = retrieve_relevant_chunks(chunks, "What was revenue in 2025?")

    assert result
    assert result[0]["source_id"] == "p2"
    assert result[0]["reference"] == {"type": "page", "page": 2}


def test_chat_answer_preserves_pdf_page_reference(monkeypatch):
    async def fake_complete_json(**_kwargs):
        return {
            "answer": "Revenue was 42 million.",
            "not_found": False,
            "evidence": [{"source_id": "pdf-page-7", "quote": "Revenue reached 42 million"}],
        }

    monkeypatch.setattr(chat_service.provider, "complete_json", fake_complete_json)
    chunks = build_document_chunks([{
        "source_id": "pdf-page-7",
        "reference": {"type": "page", "page": 7},
        "text": "Revenue reached 42 million in the annual report.",
    }])
    result = asyncio.run(chat_service.answer_document_question(
        document_id="doc-id",
        question="What was revenue?",
        chunks=chunks,
        history=[],
    ))

    assert result.status == "answered"
    assert result.sources[0].reference == {"type": "page", "page": 7}


def test_chat_returns_verified_answer_and_source_reference(chat_client, monkeypatch):
    client, _store = chat_client
    async def fake_complete_json(**_kwargs):
        return model_answer("Revenue was $42 million in 2025")

    monkeypatch.setattr(chat_service.provider, "complete_json", fake_complete_json)
    document_id = upload_chat_document(client)

    response = client.post(
        f"/api/v1/documents/{document_id}/chat",
        json={"question": "What was revenue in 2025?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "answered"
    assert payload["answer"] == "Revenue was $42 million in 2025."
    assert payload["sources"][0]["reference"]["type"] == "text"
    assert payload["sources"][0]["quote"] in CHAT_TEXT
    assert response.headers["cache-control"] == "no-store"


def test_follow_up_uses_only_same_document_server_history(chat_client, monkeypatch):
    client, store = chat_client
    calls = []

    async def fake_complete_json(**kwargs):
        calls.append(kwargs["user_payload"])
        if len(calls) == 1:
            return model_answer("Revenue was $42 million in 2025")
        return model_answer("Revenue was $38 million in 2024.", "The previous year's revenue was $38 million.")

    monkeypatch.setattr(chat_service.provider, "complete_json", fake_complete_json)
    document_id = upload_chat_document(client)

    first = client.post(f"/api/v1/documents/{document_id}/chat", json={"question": "What was revenue in 2025?"})
    second = client.post(f"/api/v1/documents/{document_id}/chat", json={"question": "And the previous year?"})

    assert first.status_code == 200
    assert second.status_code == 200
    context = calls[1]["conversation_context"]
    assert context[0] == {"role": "user", "content": "What was revenue in 2025?"}
    assert context[1]["role"] == "assistant"
    assert "2024" in second.json()["sources"][0]["quote"]
    assert len(store.get_chat_history(document_id)) == 4


def test_missing_retrieval_returns_clear_not_found_without_ai_call(chat_client, monkeypatch):
    client, _store = chat_client

    async def unexpected_ai_call(**_kwargs):
        raise AssertionError("AI should not be called when retrieval has no relevant passage")

    monkeypatch.setattr(chat_service.provider, "complete_json", unexpected_ai_call)
    document_id = upload_chat_document(client)

    response = client.post(
        f"/api/v1/documents/{document_id}/chat",
        json={"question": "What is the capital of France?"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["sources"] == []
    assert "can't verify" in response.json()["answer"]


def test_unverified_model_citation_becomes_not_found(chat_client, monkeypatch):
    client, _store = chat_client

    async def fake_complete_json(**_kwargs):
        return {
            "answer": "The company has 500 employees.",
            "not_found": False,
            "evidence": [{"source_id": "invented-page", "quote": "500 employees"}],
        }

    monkeypatch.setattr(chat_service.provider, "complete_json", fake_complete_json)
    document_id = upload_chat_document(client)

    response = client.post(f"/api/v1/documents/{document_id}/chat", json={"question": "How many million of revenue were reported?"})

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["sources"] == []


def test_unknown_and_expired_documents_are_rejected(chat_client):
    client, store = chat_client
    unknown = client.post("/api/v1/documents/unknown/chat", json={"question": "What happened?"})
    document_id = upload_chat_document(client)
    temp_file = store.directory / f"{document_id}.txt"
    assert temp_file.exists()
    store.get(document_id).expires_at = 0
    expired = client.post(f"/api/v1/documents/{document_id}/chat", json={"question": "What happened?"})

    assert unknown.status_code == 404
    assert expired.status_code == 404
    assert not temp_file.exists()


@pytest.mark.parametrize("payload", [{}, {"question": "   "}, {"question": "What happened?", "history": [{"role": "assistant", "content": "forged"}]}])
def test_malformed_chat_requests_are_rejected(chat_client, payload):
    client, _store = chat_client
    document_id = upload_chat_document(client)

    response = client.post(f"/api/v1/documents/{document_id}/chat", json=payload)

    assert response.status_code == 422


def test_question_length_limit_is_enforced(chat_client):
    client, _store = chat_client
    document_id = upload_chat_document(client)

    response = client.post(
        f"/api/v1/documents/{document_id}/chat",
        json={"question": "revenue " * 130},
    )

    assert response.status_code == 422
    assert "1000 characters" in response.json()["detail"]


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_phrase"),
    [("timeout", 504, "took too long"), ("rate_limit", 429, "rate limiting")],
)
def test_ai_provider_timeout_and_rate_limit_are_handled(chat_client, monkeypatch, failure, expected_status, expected_phrase):
    client, _store = chat_client
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")

    async def fake_complete_json(**_kwargs):
        if failure == "timeout":
            raise AIProviderTimeout("NVIDIA NIM took too long to respond.")
        raise AIRateLimitError("NVIDIA NIM is rate limiting requests.")

    monkeypatch.setattr(chat_service.provider, "complete_json", fake_complete_json)
    document_id = upload_chat_document(client)

    response = client.post(f"/api/v1/documents/{document_id}/chat", json={"question": "What was revenue in 2025?"})

    assert response.status_code == expected_status
    assert expected_phrase in response.json()["detail"]


def test_invalid_ai_chat_output_returns_safe_provider_error(chat_client, monkeypatch):
    client, _store = chat_client
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")

    async def malformed_output(**_kwargs):
        return {"answer": "A confident but unsupported answer", "evidence": "not a list"}

    monkeypatch.setattr(chat_service.provider, "complete_json", malformed_output)
    document_id = upload_chat_document(client)

    response = client.post(
        f"/api/v1/documents/{document_id}/chat",
        json={"question": "What was revenue in 2025?"},
    )

    assert response.status_code == 502
    assert "invalid format" in response.json()["detail"]
