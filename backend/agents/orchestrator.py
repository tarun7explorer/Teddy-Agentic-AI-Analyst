"""Fixed, bounded workflow coordination for document analysis and chat."""

import asyncio
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.agents.analytics_agent import AnalyticsAgent
from backend.agents.document_agent import DocumentAgent
from backend.agents.research_agent import ResearchAgent
from backend.agents.state import (
    SafeErrorCode,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
    WorkflowWarningCode,
)
from backend.agents.summary_agent import SummaryAgent
from backend.agents.verification_agent import VerificationAgent
from backend.config import settings
from backend.services.ai_service import AIProviderError, provider
from backend.services.chat_schemas import ChatResponse
from backend.services.chat_service import answer_document_question
from backend.services.schemas import AnalysisResponse, SupportedFinding
from backend.services.workflow_schemas import WorkflowMetadata
from backend.storage.temporary_storage import DocumentStore
from backend.tools.calculate_statistics import NumericCalculation, make_calculate_statistics_tool
from backend.tools.document_search import make_document_search_tool
from backend.tools.extract_entities import make_extract_entities_tool
from backend.tools.registry import ToolRegistry
from backend.tools.validate_citations import make_validate_citations_tool


_NUMERIC_QUERY = re.compile(r"\b(total|sum|average|mean|median|percentage|percent|rate|compare|comparison|count|how many|increase|decrease|revenue|cost|amount|statistics?)\b", re.I)
_ANALYSIS_QUERY = "document key findings risks decisions actions important facts"


class WorkflowRunResult(BaseModel):
    """Typed return value while retaining existing public analysis/chat payloads."""

    model_config = ConfigDict(extra="forbid")

    state: WorkflowState
    analysis: AnalysisResponse | None = None
    chat: ChatResponse | None = None


class _WorkflowStop(Exception):
    def __init__(self, code: SafeErrorCode, warning: WorkflowWarningCode, message: str) -> None:
        self.code = code
        self.warning = warning
        self.message = message


class WorkflowOrchestrator:
    """Runs only the fixed application-owned sequence; models cannot plan tasks."""

    def __init__(
        self,
        *,
        document_agent: DocumentAgent | None = None,
        analytics_agent: AnalyticsAgent | None = None,
        research_agent: ResearchAgent | None = None,
        summary_agent: SummaryAgent | None = None,
        verification_agent: VerificationAgent | None = None,
    ) -> None:
        self.document_agent = document_agent or DocumentAgent()
        self.analytics_agent = analytics_agent or AnalyticsAgent()
        self.research_agent = research_agent or ResearchAgent()
        self.summary_agent = summary_agent or SummaryAgent()
        self.verification_agent = verification_agent or VerificationAgent()

    @staticmethod
    def _registry(store: DocumentStore, document_id: str) -> ToolRegistry:
        # Per-run immutable registry: every tool is bound to this exact document.
        return ToolRegistry((
            make_document_search_tool(store=store, allowed_document_id=document_id),
            make_calculate_statistics_tool(store=store, allowed_document_id=document_id),
            make_extract_entities_tool(store=store, allowed_document_id=document_id),
            make_validate_citations_tool(store=store, allowed_document_id=document_id),
        ))

    @staticmethod
    def _begin_step(state: WorkflowState, step: WorkflowStep) -> None:
        if len(state.completed_steps) >= settings.agent_max_steps:
            raise _WorkflowStop(
                SafeErrorCode.WORKFLOW_LIMIT,
                WorkflowWarningCode.WORKFLOW_STEP_LIMIT,
                "The workflow reached its configured step limit; completed local results were retained.",
            )

    async def run(
        self,
        *,
        store: DocumentStore,
        document_id: str,
        operation: Literal["analyze", "chat"],
        question: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> WorkflowRunResult:
        state = WorkflowState(current_document_id=document_id, requested_operation=operation)
        state.start()
        result = WorkflowRunResult(state=state)
        try:
            async with asyncio.timeout(settings.agent_timeout_seconds):
                await self._run_bounded(
                    state=state, result=result, store=store, document_id=document_id,
                    operation=operation, question=question, history=history or [],
                )
        except TimeoutError:
            state.add_warning(
                WorkflowWarningCode.WORKFLOW_TIMEOUT,
                "The workflow exceeded its configured duration; completed results were retained.",
            )
            self._finish_partial_or_failed(state, SafeErrorCode.PROVIDER_TIMEOUT)
        except _WorkflowStop as stop:
            state.add_warning(stop.warning, stop.message)
            self._finish_partial_or_failed(state, stop.code)
        except Exception as error:
            # Never return raw provider, parser, or document text in an error response.
            state.add_warning(
                WorkflowWarningCode.TOOL_FAILED,
                f"The workflow stopped after an internal {type(error).__name__}; completed results were retained.",
            )
            self._finish_partial_or_failed(state, SafeErrorCode.INTERNAL_ERROR)
        result.state = state
        metadata = self._public_metadata(state)
        store.save_workflow(document_id, metadata.model_dump(mode="json"))
        if result.analysis is not None:
            result.analysis.workflow = metadata
        if result.chat is not None:
            result.chat.workflow = metadata
        return result

    @staticmethod
    def _public_metadata(state: WorkflowState) -> WorkflowMetadata:
        from backend.agents.state import VerificationResults

        if state.document_assessment is None:
            assessment_data = {
                "document_type": "unknown", "operation": state.requested_operation,
                "supported_type": False, "sufficient_for_operation": False,
                "extraction_quality": "empty", "extracted_char_count": 0,
                "passage_count": 0, "table_count": 0, "source_reference_count": 0,
                "warnings": [], "unsupported_content": ["assessment_not_available"],
            }
        else:
            assessment_data = state.document_assessment.model_dump(mode="json")
        return WorkflowMetadata(
            status=state.status.value,
            partial_result=state.partial_result,
            completed_steps=[step.value for step in state.completed_steps],
            warnings=[item.model_dump(mode="json") for item in state.warnings],
            error_code=state.error_code.value if state.error_code else None,
            document_assessment=assessment_data,
            analytics=state.analytics_results,
            evidence=[item.model_dump(mode="json") for item in state.retrieved_evidence],
            verification=(state.verification_results or VerificationResults()).model_dump(mode="json"),
            provider_status=provider.status().model_dump(mode="json"),
        )

    async def _run_bounded(
        self,
        *,
        state: WorkflowState,
        result: WorkflowRunResult,
        store: DocumentStore,
        document_id: str,
        operation: Literal["analyze", "chat"],
        question: str | None,
        history: list[dict[str, str]],
    ) -> None:
        document = store.get(document_id)
        if document is None:
            raise _WorkflowStop(
                SafeErrorCode.DOCUMENT_NOT_FOUND, WorkflowWarningCode.DOCUMENT_NOT_FOUND,
                "Document not found or expired.",
            )
        if operation == "chat" and (
            not question or not question.strip() or len(question) > settings.chat_max_question_chars
        ):
            raise _WorkflowStop(
                SafeErrorCode.INVALID_REQUEST, WorkflowWarningCode.EMPTY_CONTENT,
                "A valid document question is required.",
            )

        registry = self._registry(store, document_id)
        self._begin_step(state, WorkflowStep.ASSESS_DOCUMENT)
        assessment = self.document_agent.assess(document, operation)
        state.document_assessment = assessment
        state.record_completed_step(WorkflowStep.ASSESS_DOCUMENT)
        for warning in assessment.warnings[:8]:
            state.add_warning(WorkflowWarningCode.PARTIAL_EXTRACTION, warning)
        if not assessment.supported_type:
            raise _WorkflowStop(
                SafeErrorCode.UNSUPPORTED_DOCUMENT_TYPE,
                WorkflowWarningCode.UNSUPPORTED_DOCUMENT_TYPE,
                "This document type is not supported for the requested operation.",
            )
        if not assessment.sufficient_for_operation:
            raise _WorkflowStop(
                SafeErrorCode.DOCUMENT_EMPTY,
                WorkflowWarningCode.EMPTY_CONTENT,
                "The extracted content is insufficient for the requested operation.",
            )

        self._begin_step(state, WorkflowStep.ANALYTICS)
        run_analytics = operation == "analyze" or bool(_NUMERIC_QUERY.search(question or ""))
        if run_analytics:
            analytics = await self.analytics_agent.run(document_id=document_id, registry=registry)
            state.analytics_results = analytics.analytics
            if analytics.status == "unavailable":
                state.add_warning(WorkflowWarningCode.ANALYTICS_UNAVAILABLE, "Local analytics could not be completed.")
            elif analytics.status == "no_suitable_data":
                state.add_warning(WorkflowWarningCode.NO_ANALYTICS_DATA, "No suitable numeric table data was available.")
        else:
            from backend.agents.analytics_agent import AnalyticsAgentResult
            analytics = AnalyticsAgentResult(status="no_suitable_data", warnings=[])
        if operation == "analyze":
            try:
                entity_result = await registry.execute("extract_entities", {"document_id": document_id, "max_entities": 100})
                state.entity_candidates = entity_result.candidates
            except Exception:
                state.add_warning(WorkflowWarningCode.TOOL_FAILED, "Deterministic entity candidates could not be extracted.")
        state.record_completed_step(WorkflowStep.ANALYTICS)
        calculations: list[NumericCalculation] = analytics.calculations

        self._begin_step(state, WorkflowStep.RETRIEVE_EVIDENCE)
        query = question if operation == "chat" else _ANALYSIS_QUERY
        if operation == "chat" and history and question:
            prior_user = next((item.get("content", "") for item in reversed(history) if item.get("role") == "user"), "")
            if prior_user and len(question.split()) <= 4:
                query = f"{prior_user} {question}"[:settings.chat_max_question_chars]
        research = await self.research_agent.retrieve(
            document_id=document_id, query=query, registry=registry,
            max_results=settings.chat_retrieval_top_k,
        )
        state.retrieved_evidence = research.evidence[:32]
        if research.status == "not_found":
            state.add_warning(WorkflowWarningCode.NO_RELEVANT_EVIDENCE, "No relevant extracted passage was found.")
        elif research.status == "unavailable":
            state.add_warning(WorkflowWarningCode.TOOL_FAILED, "Document evidence retrieval could not complete.")
        state.record_completed_step(WorkflowStep.RETRIEVE_EVIDENCE)

        if operation == "analyze":
            self._begin_step(state, WorkflowStep.GENERATE_SUMMARY)
            if document.analysis is not None:
                try:
                    summary = AnalysisResponse.model_validate(document.analysis)
                    summary_result_status = "completed"
                    summary_error = None
                    summary_warnings: list[str] = []
                except Exception:
                    summary = None
                    summary_result_status = "failed"
                    summary_error = SafeErrorCode.PROVIDER_INVALID_RESPONSE
                    summary_warnings = ["Cached summary did not match the required schema."]
            else:
                summary_result = await self.summary_agent.summarize(document=document, assessment=assessment)
                summary = summary_result.analysis
                summary_result_status = summary_result.status
                summary_error = summary_result.error_code
                summary_warnings = summary_result.warnings
            if summary is not None:
                result.analysis = summary
                state.summary_findings = (
                    summary.five_line_summary + [summary.detailed_summary] + summary.key_takeaways
                    + summary.important_entities + summary.risks + summary.decisions + summary.action_items
                )[:160]
            if summary_result_status != "completed":
                for message in summary_warnings[:8]:
                    state.add_warning(
                        WorkflowWarningCode.AI_UNAVAILABLE if summary_result_status == "ai_unavailable" else WorkflowWarningCode.SUMMARY_FAILED,
                        message,
                    )
            state.record_completed_step(WorkflowStep.GENERATE_SUMMARY)
            self._begin_step(state, WorkflowStep.VERIFY_OUTPUT)
            verification = await self.verification_agent.verify_findings(
                document_id=document_id,
                findings=state.summary_findings,
                calculations=calculations,
                registry=registry,
            )
            state.verification_results = verification
            if verification.status in {"partial", "failed"} and verification.claims_checked:
                state.add_warning(WorkflowWarningCode.VERIFICATION_PARTIAL, "Some findings are only partially verified; quote matching does not establish logical entailment.")
            state.record_completed_step(WorkflowStep.VERIFY_OUTPUT)
            if summary_result_status != "completed":
                if summary_error:
                    self._finish_partial_or_failed(state, summary_error)
                    return
                state.add_warning(WorkflowWarningCode.SUMMARY_FAILED, "Summary generation did not complete.")
                self._finish_partial_or_failed(state, SafeErrorCode.SUMMARY_UNAVAILABLE)
                return
        else:
            self._begin_step(state, WorkflowStep.ANSWER_CHAT)
            if not research.passages:
                chat_result = ChatResponse(
                    document_id=document_id, status="not_found",
                    answer="I couldn't verify an answer from the available extracted content. Try a narrower question or provide additional evidence.",
                    sources=[],
                )
            else:
                try:
                    chat_result = await answer_document_question(
                        document_id=document_id,
                        question=question or "",
                        chunks=document.chat_chunks,
                        history=history,
                        selected_chunks=[item.model_dump() for item in research.passages],
                    )
                except AIProviderError as error:
                    raise _WorkflowStop(
                        self._safe_ai_error(error),
                        WorkflowWarningCode.AI_UNAVAILABLE,
                        str(error),
                    ) from error
            result.chat = chat_result
            state.record_completed_step(WorkflowStep.ANSWER_CHAT)
            self._begin_step(state, WorkflowStep.VERIFY_OUTPUT)
            findings = []
            if chat_result.status == "answered":
                findings = [SupportedFinding(text=chat_result.answer, citations=chat_result.sources)]
            verification = await self.verification_agent.verify_findings(
                document_id=document_id,
                findings=findings,
                calculations=calculations,
                registry=registry,
            )
            state.verification_results = verification
            if verification.status in {"partial", "failed"} and verification.claims_checked:
                state.add_warning(WorkflowWarningCode.VERIFICATION_PARTIAL, "The answer has source provenance checks; logical entailment remains unproven.")
            state.record_completed_step(WorkflowStep.VERIFY_OUTPUT)

        if state.warnings or (state.verification_results and state.verification_results.status == "partial"):
            state.transition_to(WorkflowStatus.PARTIAL, error_code=state.error_code)
        else:
            state.transition_to(WorkflowStatus.COMPLETED)

    @staticmethod
    def _safe_ai_error(error: AIProviderError) -> SafeErrorCode:
        if error.code == "ai_unavailable" and provider.status().code == "ai_disabled":
            return SafeErrorCode.AI_DISABLED
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

    @staticmethod
    def _finish_partial_or_failed(state: WorkflowState, code: SafeErrorCode) -> None:
        has_results = bool(
            state.analytics_results is not None or state.summary_findings
            or state.retrieved_evidence or state.entity_candidates
        )
        if has_results:
            state.transition_to(WorkflowStatus.PARTIAL, error_code=code)
        else:
            state.transition_to(WorkflowStatus.FAILED, error_code=code)


orchestrator = WorkflowOrchestrator()

__all__ = ["WorkflowOrchestrator", "WorkflowRunResult", "orchestrator"]
