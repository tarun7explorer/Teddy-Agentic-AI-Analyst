"""Typed allowlist for application-owned tools; no model-defined callables."""

import asyncio
import inspect
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Generic, TypeVar

from pydantic import BaseModel


InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ToolNotAllowed(ValueError):
    """Raised when a caller requests a tool outside the application allowlist."""

    code = "tool_not_allowed"


class ToolExecutionError(RuntimeError):
    """Safe wrapper for tool failures; callers should not expose underlying details."""

    code = "tool_execution_failed"


@dataclass(frozen=True)
class ToolDefinition(Generic[InputModel, OutputModel]):
    name: str
    input_model: type[InputModel]
    output_model: type[OutputModel]
    handler: Callable[[InputModel], OutputModel | dict[str, Any] | Awaitable[OutputModel | dict[str, Any]]]

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError("Tool names must be lowercase application identifiers.")
        if not issubclass(self.input_model, BaseModel) or not issubclass(self.output_model, BaseModel):
            raise TypeError("Tool input and output types must be Pydantic models.")
        if self.input_model.model_config.get("extra") != "forbid":
            raise TypeError("Tool input models must reject unexpected fields (extra='forbid').")
        if self.output_model.model_config.get("extra") != "forbid":
            raise TypeError("Tool output models must reject unexpected fields (extra='forbid').")
        if not callable(self.handler):
            raise TypeError("Tool handler must be an application-owned callable.")


class ToolRegistry:
    """Immutable registry whose names and handlers are supplied by application code."""

    def __init__(self, definitions: tuple[ToolDefinition[Any, Any], ...] = ()) -> None:
        tools: dict[str, ToolDefinition[Any, Any]] = {}
        for definition in definitions:
            if definition.name in tools:
                raise ValueError(f"Duplicate tool name: {definition.name}.")
            tools[definition.name] = definition
        self._tools = MappingProxyType(tools)

    @property
    def allowed_names(self) -> frozenset[str]:
        return frozenset(self._tools)

    async def execute(self, name: str, payload: object) -> BaseModel:
        if not isinstance(name, str):
            raise ToolNotAllowed("Requested tool is not registered.")
        definition = self._tools.get(name)
        if definition is None:
            raise ToolNotAllowed("Requested tool is not registered.")
        request = definition.input_model.model_validate(payload)
        try:
            if inspect.iscoroutinefunction(definition.handler):
                result = await definition.handler(request)
            else:
                result = await asyncio.to_thread(definition.handler, request)
            if inspect.isawaitable(result):
                result = await result
            return definition.output_model.model_validate(result)
        except ToolNotAllowed:
            raise
        except Exception as exc:
            # Do not propagate exception text that could include source text or secrets.
            raise ToolExecutionError(f"Tool '{name}' failed safely.") from exc


# The process-wide registry stays empty because tools require an explicit document
# scope. WorkflowOrchestrator builds an immutable allowlist bound to one document.
tool_registry = ToolRegistry()
