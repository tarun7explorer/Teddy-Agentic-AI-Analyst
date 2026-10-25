import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.agents.state import (
    SafeErrorCode,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)
from backend.tools.registry import ToolDefinition, ToolNotAllowed, ToolRegistry


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doubled: int


def test_workflow_state_validates_inputs_and_lifecycle():
    state = WorkflowState(current_document_id="doc-123", requested_operation="analyze")
    assert state.status == WorkflowStatus.CREATED
    state.start()
    state.record_completed_step(WorkflowStep.ASSESS_DOCUMENT)
    state.transition_to(WorkflowStatus.PARTIAL)
    assert state.status == WorkflowStatus.PARTIAL
    assert state.partial_result is True
    assert state.ended_at is not None
    assert state.duration_seconds is not None
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        state.transition_to(WorkflowStatus.RUNNING)


def test_workflow_state_rejects_direct_status_mutation_and_unexpected_fields():
    state = WorkflowState(current_document_id="doc-123", requested_operation="chat")
    with pytest.raises(ValueError, match="transition_to"):
        state.status = WorkflowStatus.RUNNING
    with pytest.raises(ValidationError):
        WorkflowState(current_document_id="doc-123", requested_operation="chat", unexpected="x")
    with pytest.raises(ValidationError):
        WorkflowState(current_document_id="doc-123", requested_operation="analyze", started_at=datetime.now())


def test_failed_workflow_requires_safe_error_code():
    state = WorkflowState(current_document_id="doc-123", requested_operation="analyze")
    with pytest.raises(ValueError, match="safe error code"):
        state.transition_to(WorkflowStatus.FAILED)
    with pytest.raises(ValueError):
        state.transition_to(WorkflowStatus.FAILED, error_code="not_a_safe_code")
    state.transition_to(WorkflowStatus.FAILED, error_code=SafeErrorCode.AI_DISABLED)
    assert state.error_code == SafeErrorCode.AI_DISABLED


def test_registry_validates_inputs_and_returns_typed_output():
    registry = ToolRegistry((
        ToolDefinition("double_value", ToolInput, ToolOutput, lambda request: {"doubled": request.value * 2}),
    ))
    result = asyncio.run(registry.execute("double_value", {"value": 4}))
    assert result == ToolOutput(doubled=8)
    with pytest.raises(ValidationError):
        asyncio.run(registry.execute("double_value", {"value": 4, "path": "secret"}))


def test_registry_rejects_unknown_names_and_duplicate_definitions():
    registry = ToolRegistry()
    with pytest.raises(ToolNotAllowed):
        asyncio.run(registry.execute("shell", {"command": "anything"}))
    definition = ToolDefinition("double_value", ToolInput, ToolOutput, lambda request: {"doubled": request.value})
    with pytest.raises(ValueError, match="Duplicate tool"):
        ToolRegistry((definition, definition))
