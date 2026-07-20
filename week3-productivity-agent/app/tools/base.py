"""
Base classes shared by every tool: a Pydantic-validated input/output contract,
a uniform ToolResult wrapper, and a lightweight registry the agent controller
uses for tool selection + JSON-schema generation for the LLM.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, ValidationError


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    message: str = ""


class ToolValidationError(Exception):
    """Raised when tool input fails Pydantic validation."""


class BaseTool(ABC):
    """All tools implement: name, description, input schema, requires_approval, run()."""

    name: str = "base_tool"
    description: str = ""
    input_schema: Type[BaseModel] = BaseModel
    requires_approval: bool = False
    is_write_action: bool = False

    def validate(self, raw_args: Dict[str, Any]) -> BaseModel:
        try:
            return self.input_schema(**raw_args)
        except ValidationError as e:
            raise ToolValidationError(str(e)) from e

    @abstractmethod
    def execute(self, validated_input: BaseModel) -> ToolResult:
        ...

    def run(self, raw_args: Dict[str, Any]) -> ToolResult:
        try:
            validated = self.validate(raw_args)
        except ToolValidationError as e:
            return ToolResult(success=False, error=f"Invalid tool arguments: {e}")
        try:
            return self.execute(validated)
        except Exception as e:  # tool-level error containment
            return ToolResult(success=False, error=str(e))

    def openai_function_schema(self) -> Dict[str, Any]:
        """Convert the Pydantic input schema into an OpenAI-style function/tool schema."""
        schema = self.input_schema.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def all(self):
        return list(self._tools.values())

    def openai_schemas(self):
        return [t.openai_function_schema() for t in self._tools.values()]

    def names(self):
        return list(self._tools.keys())
