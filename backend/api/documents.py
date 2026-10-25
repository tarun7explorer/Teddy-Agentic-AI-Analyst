"""Upload, inspect, and delete extracted documents."""

import logging
import asyncio
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path as ApiPath, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.analytics.schemas import AnalyticsResponse
from backend.config import settings
from backend.parsers import PARSER_BY_EXTENSION, parse_document
from backend.agents.document_agent import DocumentAgent
from backend.agents.orchestrator import orchestrator
from backend.rag.chunker import build_document_chunks
from backend.services.export_service import report_pdf, safe_export_stem, summary_markdown, table_csv
from backend.services.ai_service import provider
from backend.services.workflow_schemas import (
    ProviderAvailabilityView,
    VerificationView,
    WorkflowMetadata,
    WorkflowWarningView,
)
from backend.api.workflow_http import api_error, document_not_found, workflow_http_exception
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
        from backend.analytics.data_profiler import profile_document

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
        raise api_error(415, "unsupported_file_type", str(exc)) from exc

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
        assessment = DocumentAgent().assess(document, "analyze")
        warning_code = (
            "unsupported_document_type" if not assessment.supported_type
            else "empty_content" if assessment.extraction_quality == "empty"
            else "partial_extraction"
        )
        metadata = WorkflowMetadata(
            status="not_started",
            partial_result=assessment.extraction_quality in {"partial", "poor", "empty"},
            completed_steps=[],
            warnings=[WorkflowWarningView(code=warning_code, message=warning) for warning in assessment.warnings[:32]],
            document_assessment=assessment.model_dump(mode="json"),
            analytics=analytics,
            evidence=[],
            verification=VerificationView(),
            provider_status=ProviderAvailabilityView.model_validate(provider.status().model_dump()),
        )
        document.workflow = metadata.model_dump(mode="json")
        return document.result_response()
    except UnsupportedFileType as exc:
        _unlink_temp(temp_path)
        raise api_error(415, "unsupported_file_type", str(exc)) from exc
    except (ResourceLimitExceeded, OverflowError) as exc:
        _unlink_temp(temp_path)
        raise api_error(413, "upload_too_large", str(exc)) from exc
    except (InvalidFile, ValueError) as exc:
        _unlink_temp(temp_path)
        raise api_error(422, "invalid_file", str(exc)) from exc
    except Exception as exc:
        _unlink_temp(temp_path)
        logger.exception("Document parsing failed for document id %s", document_id)
        raise api_error(422, "document_parse_failed", "The document could not be parsed. Check that it is a valid, supported file.") from exc


@router.get("/{document_id}/status")
async def document_status(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    return document.status_response()


@router.get("/{document_id}/results")
async def document_results(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    return document.result_response()


@router.get("/{document_id}/analytics")
async def document_analytics(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    return document.analytics or AnalyticsResponse(
        status="no_suitable_data", charts=[], metrics=[], comparison_tables=[], timelines=[], profiles=[],
        warnings=["No chart-ready data is available for this document."],
    ).model_dump(mode="json")


@router.post("/{document_id}/analyze")
async def analyze_uploaded_document(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    workflow = await orchestrator.run(store=store, document_id=document_id, operation="analyze")
    if workflow.analysis is None:
        raise workflow_http_exception(workflow.state, "Document analysis could not be completed.")
    payload = workflow.analysis.model_dump(mode="json")
    if document.analysis is None:
        store.save_analysis(document_id, workflow.analysis.model_dump(mode="json", exclude={"workflow"}))
    return payload


@router.get("/{document_id}/export/summary.md")
async def export_summary(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    try:
        content = summary_markdown(document)
    except ValueError as exc:
        raise api_error(409, "summary_not_available", str(exc)) from exc
    filename = f"{safe_export_stem(document.original_filename)}-summary.md"
    return Response(content, media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.get("/{document_id}/export/report.pdf")
async def export_report(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    try:
        content = await run_in_threadpool(report_pdf, document)
    except Exception as exc:
        logger.exception("PDF report generation failed for document id %s", document_id)
        raise api_error(500, "report_export_failed", "The PDF report could not be generated.") from exc
    filename = f"{safe_export_stem(document.original_filename)}-report.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.get("/{document_id}/export/tables/{table_index}.csv")
async def export_table_csv(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    table_index: int,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    document = store.get(document_id)
    if document is None:
        raise document_not_found()
    if table_index < 0 or table_index >= len(document.tables):
        raise api_error(404, "table_not_found", "That extracted table is not available for this document.")
    table = document.tables[table_index]
    try:
        content = table_csv(table)
    except Exception as exc:
        logger.exception("CSV export failed for document id %s", document_id)
        raise api_error(500, "table_export_failed", "The selected table could not be exported.") from exc
    stem = safe_export_stem(document.original_filename)
    table_stem = safe_export_stem(str(table.get("name") or f"table-{table_index + 1}"))
    filename = f"{stem}-{table_stem}.csv"
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.delete("/{document_id}")
async def delete_document(
    document_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> dict:
    if not store.delete(document_id):
        raise document_not_found()
    return {"document_id": document_id, "status": "deleted"}
