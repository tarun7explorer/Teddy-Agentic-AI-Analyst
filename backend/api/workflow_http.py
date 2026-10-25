"""Safe, stable HTTP mapping for workflow failures."""

from fastapi import HTTPException

from backend.agents.state import SafeErrorCode, WorkflowState


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message, headers={"X-Teddy-Error-Code": code})


def document_not_found() -> HTTPException:
    return api_error(404, "document_not_found", "Document not found or expired.")


_STATUS_BY_ERROR = {
    SafeErrorCode.DOCUMENT_NOT_FOUND: 404,
    SafeErrorCode.UNSUPPORTED_DOCUMENT_TYPE: 415,
    SafeErrorCode.DOCUMENT_EMPTY: 422,
    SafeErrorCode.INVALID_REQUEST: 422,
    SafeErrorCode.AI_DISABLED: 503,
    SafeErrorCode.AI_CONFIGURATION: 503,
    SafeErrorCode.PROVIDER_AUTHENTICATION: 502,
    SafeErrorCode.PROVIDER_RATE_LIMITED: 429,
    SafeErrorCode.PROVIDER_QUOTA_EXHAUSTED: 429,
    SafeErrorCode.PROVIDER_PAYMENT_REQUIRED: 402,
    SafeErrorCode.PROVIDER_TIMEOUT: 504,
    SafeErrorCode.PROVIDER_UNAVAILABLE: 502,
    SafeErrorCode.PROVIDER_MODEL_UNAVAILABLE: 502,
    SafeErrorCode.PROVIDER_INVALID_RESPONSE: 502,
    SafeErrorCode.WORKFLOW_LIMIT: 503,
    SafeErrorCode.INTERNAL_ERROR: 500,
}


def workflow_http_exception(state: WorkflowState, fallback: str) -> HTTPException:
    code = state.error_code or SafeErrorCode.INTERNAL_ERROR
    message = next((warning.message for warning in reversed(state.warnings)), fallback)
    return api_error(_STATUS_BY_ERROR.get(code, 500), code.value, message)
