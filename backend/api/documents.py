"""Upload, inspect, and delete extracted documents."""

import logging
import asyncio
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.analytics.data_profiler import profile_document
from backend.analytics.schemas import AnalyticsResponse
from backend.config import settings
from backend.parsers import PARSER_BY_EXTENSION, parse_document
from backend.services.ai_provider import AIProviderError
from backend.rag.chunker import build_document_chunks
from backend.services.export_service import report_pdf, safe_export_stem, summary_markdown, table_csv
from backend.services.summary_service import analyze_document as run_analysis
from backend.storage.temporary_storage import DocumentStore, document_store
from backend.utils.file_validation import (
    InvalidFile,
    ResourceLimitExceeded,
    UnsupportedFileType,
    get_supported_extension,
    safe_display_filename,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
_processing_slots = asyncio.Semaphore(settings.max_concurrent_documents)


def get_document_store() -> DocumentStore:
    return document_store


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ResourceLimitExceeded(
                        f"The upload exceeds the {settings.max_upload_size_mb} MB size limit."
                    )
                output.write(chunk)
    finally:
        await upload.close()
    if size == 0:
        raise InvalidFile("The uploaded file is empty.")
    return size


def _unlink_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove temporary upload file.")


def _process_document(path: Path, extension: str):
    detected_type, extraction = parse_document(path, extension)
    chat_chunks = build_document_chunks(extraction.source_passages, extraction.extracted_text)
    try:
        analytics = profile_document(extraction.tables, extraction.source_passages)
    except Exception:
        logger.exception("Analytics profiling failed")
        analytics = AnalyticsResponse(
            status="no_suitable_data",
            charts=[],
            metrics=[],
            comparison_tables=[],
            timelines=[],
            profiles=[],
            warnings=["Tabular analytics could not be calculated safely for this document."],
        )
    return detected_type, extraction, chat_chunks, analytics


@router.get("/limits")
async def upload_limits() -> dict:
    """Expose only non-sensitive settings needed for browser-side validation."""
    return {
        "max_upload_size_bytes": settings.max_upload_size_mb * 1024 * 1024,
        "max_upload_size_mb": settings.max_upload_size_mb,
        "max_chat_question_chars": settings.chat_max_question_chars,
        "supported_extensions": sorted(PARSER_BY_EXTENSION),
    }


@router.post("/upload", status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    store.cleanup_expired()
    filename = safe_display_filename(file.filename)
    try:
        extension = get_supported_extension(filename)
    except UnsupportedFileType as exc:
        await file.close()
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    document_id = secrets.token_urlsafe(32)
    temp_path = store.new_temp_path(document_id, extension)
    try:
        size = await _save_upload(
            file,
            temp_path,
            settings.max_upload_size_mb * 1024 * 1024,
        )
        async with _processing_slots:
            detected_type, extraction, chat_chunks, analytics = await run_in_threadpool(
                _process_document, temp_path, extension,
            )
        document = store.add(
            document_id=document_id,
            filename=filename,
            detected_type=detected_type,
            file_size=size,
            extraction=extraction,
            temp_path=temp_path,
            analytics=analytics.model_dump(mode="json"),
            chat_chunks=chat_chunks,
        )
        return document.result_response()
    except UnsupportedFileType as exc:
        _unlink_temp(temp_path)
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except (ResourceLimitExceeded, OverflowError) as exc:
        _unlink_temp(temp_path)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (InvalidFile, ValueError) as exc:
        _unlink_temp(temp_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _unlink_temp(temp_path)
        logger.exception("Document parsing failed for document id %s", document_id)
        raise HTTPException(
            status_code=422,
            detail="The document could not be parsed. Check that it is a valid, supported file.",
        ) from exc


@router.get("/{document_id}/status")
async def document_status(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    return document.status_response()


@router.get("/{document_id}/results")
async def document_results(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    return document.result_response()


@router.get("/{document_id}/analytics")
async def document_analytics(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    return document.analytics or AnalyticsResponse(
        status="no_suitable_data", charts=[], metrics=[], comparison_tables=[], timelines=[], profiles=[],
        warnings=["No chart-ready data is available for this document."],
    ).model_dump(mode="json")


@router.post("/{document_id}/analyze")
async def analyze_uploaded_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    if document.analysis is not None:
        return document.analysis
    try:
        response = await run_analysis(
            document_id=document.document_id,
            source_passages=document.source_passages,
            extracted_text=document.extracted_text,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    payload = response.model_dump(mode="json")
    store.save_analysis(document_id, payload)
    return payload


@router.get("/{document_id}/export/summary.md")
async def export_summary(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    try:
        content = summary_markdown(document)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    filename = f"{safe_export_stem(document.original_filename)}-summary.md"
    return Response(content, media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.get("/{document_id}/export/report.pdf")
async def export_report(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    try:
        content = await run_in_threadpool(report_pdf, document)
    except Exception as exc:
        logger.exception("PDF report generation failed for document id %s", document_id)
        raise HTTPException(status_code=500, detail="The PDF report could not be generated.") from exc
    filename = f"{safe_export_stem(document.original_filename)}-report.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.get("/{document_id}/export/tables/{table_index}.csv")
async def export_table_csv(
    document_id: str,
    table_index: int,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    if table_index < 0 or table_index >= len(document.tables):
        raise HTTPException(status_code=404, detail="That extracted table is not available for this document.")
    table = document.tables[table_index]
    try:
        content = table_csv(table)
    except Exception as exc:
        logger.exception("CSV export failed for document id %s", document_id)
        raise HTTPException(status_code=500, detail="The selected table could not be exported.") from exc
    stem = safe_export_stem(document.original_filename)
    table_stem = safe_export_stem(str(table.get("name") or f"table-{table_index + 1}"))
    filename = f"{stem}-{table_stem}.csv"
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    if not store.delete(document_id):
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    return {"document_id": document_id, "status": "deleted"}
