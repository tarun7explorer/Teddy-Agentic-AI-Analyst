"""Use the existing evidence-grounded summary service only when AI is allowed."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.state import DocumentAssessment, SafeErrorCode
from backend.services.ai_service import AIProviderError, provider
from backend.services.schemas import AnalysisResponse
from backend.services.summary_service import analyze_document
from backend.storage.temporary_storage import StoredDocument


class SummaryAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "ai_unavailable", "insufficient_content", "failed"]
    analysis: AnalysisResponse | None = None
    error_code: SafeErrorCode | None = None
    warnings: list[str] = Field(default_factory=list, max_length=16)


def _safe_error_code(error: AIProviderError) -> SafeErrorCode:
    return {
        "ai_unavailable": SafeErrorCode.AI_CONFIGURATION,
        "provider_timeout": SafeErrorCode.PROVIDER_TIMEOUT,
        "provider_unavailable": SafeErrorCode.PROVIDER_UNAVAILABLE,
        "provider_model_unavailable": SafeErrorCode.PROVIDER_MODEL_UNAVAILABLE,
        "provider_authentication_failed": SafeErrorCode.PROVIDER_AUTHENTICATION,
        "provider_rate_limited": SafeErrorCode.PROVIDER_RATE_LIMITED,
        "provider_quota_exhausted": SafeErrorCode.PROVIDER_QUOTA_EXHAUSTED,
        "provider_payment_required": SafeErrorCode.PROVIDER_PAYMENT_REQUIRED,
        "provider_invalid_response": SafeErrorCode.PROVIDER_INVALID_RESPONSE,
    }.get(error.code, SafeErrorCode.SUMMARY_UNAVAILABLE)


class SummaryAgent:
    async def summarize(
        self,
        *,
        document: StoredDocument,
        assessment: DocumentAssessment,
    ) -> SummaryAgentResult:
        if not assessment.supported_type or not document.extracted_text.strip():
            return SummaryAgentResult(
                status="insufficient_content",
                error_code=SafeErrorCode.DOCUMENT_EMPTY,
                warnings=["A source-grounded summary requires extractable document text."],
            )

        provider_status = provider.status()
        if not provider_status.available:
            code = SafeErrorCode.AI_DISABLED if provider_status.code == "ai_disabled" else SafeErrorCode.AI_CONFIGURATION
            return SummaryAgentResult(
                status="ai_unavailable",
                error_code=code,
                warnings=[provider_status.message],
            )

        try:
            analysis = await analyze_document(
                document_id=document.document_id,
                source_passages=document.source_passages,
                extracted_text=document.extracted_text,
            )
            validated = AnalysisResponse.model_validate(analysis)
            return SummaryAgentResult(
                status="completed",
                analysis=validated,
                warnings=validated.warnings[:16],
            )
        except AIProviderError as exc:
            return SummaryAgentResult(
                status="failed",
                error_code=_safe_error_code(exc),
                warnings=[str(exc)[:500]],
            )
        except (ValidationError, ValueError, TypeError):
            return SummaryAgentResult(
                status="failed",
                error_code=SafeErrorCode.PROVIDER_INVALID_RESPONSE,
                warnings=["Summary output did not match the required validated structure."],
            )
