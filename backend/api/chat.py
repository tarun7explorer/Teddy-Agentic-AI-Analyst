"""Per-document chat endpoint using only the document's own cached extraction."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.api.documents import get_document_store
from backend.config import settings
from backend.services.ai_provider import AIProviderError
from backend.services.chat_schemas import ChatRequest, ChatResponse
from backend.services.chat_service import answer_document_question
from backend.storage.temporary_storage import DocumentStore


router = APIRouter(tags=["document chat"])


@router.post("/api/v1/documents/{document_id}/chat", response_model=ChatResponse)
async def chat_with_document(
    document_id: str,
    request: ChatRequest,
    response: Response,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> ChatResponse:
    response.headers["Cache-Control"] = "no-store"
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    if len(request.question) > settings.chat_max_question_chars:
        raise HTTPException(
            status_code=422,
            detail=f"Questions must be at most {settings.chat_max_question_chars} characters.",
        )

    history = store.get_chat_history(document_id)
    try:
        result = await answer_document_question(
            document_id=document_id,
            question=request.question,
            chunks=document.chat_chunks,
            history=history,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    store.append_chat_exchange(document_id, request.question, result.answer)
    return result
