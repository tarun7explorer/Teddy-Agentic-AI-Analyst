"""Per-document chat endpoint using only the document's own cached extraction."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Response

from backend.agents.orchestrator import orchestrator
from backend.api.documents import get_document_store
from backend.config import settings
from backend.services.chat_schemas import ChatRequest, ChatResponse
from backend.storage.temporary_storage import DocumentStore
from backend.api.workflow_http import api_error, document_not_found, workflow_http_exception


router = APIRouter(tags=["document chat"])


@router.post("/api/v1/documents/{document_id}/chat", response_model=ChatResponse)
async def chat_with_document(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: ChatRequest,
    response: Response,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> ChatResponse:
    response.headers["Cache-Control"] = "no-store"
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    if len(request.question) > settings.chat_max_question_chars:
        raise api_error(422, "question_too_long", f"Questions must be at most {settings.chat_max_question_chars} characters.")

    history = store.get_chat_history(document_id)
    workflow = await orchestrator.run(
        store=store, document_id=document_id, operation="chat",
        question=request.question, history=history,
    )
    result = workflow.chat
    if result is None:
        raise workflow_http_exception(workflow.state, "Document chat could not be completed.")

    store.append_chat_exchange(document_id, request.question, result.answer)
    return result
