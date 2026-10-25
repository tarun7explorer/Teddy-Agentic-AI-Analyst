"""Run existing Python analytics through the document-scoped tool registry."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.analytics.schemas import AnalyticsResponse
from backend.tools.calculate_statistics import CalculateStatisticsOutput, NumericCalculation
from backend.tools.registry import ToolNotAllowed, ToolRegistry, ToolExecutionError


class AnalyticsAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "no_suitable_data", "unavailable"]
    analytics: AnalyticsResponse | None = None
    calculations: list[NumericCalculation] = Field(default_factory=list, max_length=500)
    input_scope: str = Field(default="", max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=32)


class AnalyticsAgent:
    async def run(self, *, document_id: str, registry: ToolRegistry) -> AnalyticsAgentResult:
        try:
            result = await registry.execute("calculate_statistics", {"document_id": document_id})
            typed = CalculateStatisticsOutput.model_validate(result)
        except (ToolNotAllowed, ToolExecutionError, ValidationError, ValueError):
            return AnalyticsAgentResult(
                status="unavailable",
                warnings=["Deterministic analytics could not be calculated for this document."],
            )
        return AnalyticsAgentResult(
            status=typed.status,
            analytics=typed.analytics,
            calculations=typed.calculations,
            input_scope=typed.input_scope,
            warnings=typed.warnings,
        )
