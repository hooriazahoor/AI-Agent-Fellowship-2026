import time
import uuid
from app.agent.controller import AgentController
from app.tools.base import BaseTool, ToolResult
from pydantic import BaseModel
from app.config import settings


class _SlowInput(BaseModel):
    pass


class _SlowTool(BaseTool):
    name = "slow_tool_for_testing"
    description = "Deliberately sleeps longer than the configured timeout."
    input_schema = _SlowInput
    requires_approval = False

    def execute(self, i):
        time.sleep(settings.tool_timeout_seconds + 2)
        return ToolResult(success=True, data={}, message="should never get here")


def test_tool_execution_timeout_is_enforced(monkeypatch):
    object.__setattr__(settings, "tool_timeout_seconds", 1)
    object.__setattr__(settings, "max_tool_retries", 0)
    try:
        controller = AgentController()
        result = controller._run_tool_with_timeout(_SlowTool(), {})
        assert result.success is False
        assert "timed out" in result.error.lower()
    finally:
        object.__setattr__(settings, "tool_timeout_seconds", 30)
        object.__setattr__(settings, "max_tool_retries", 2)


def test_repeated_tool_failure_stops_after_max_retries(monkeypatch):
    object.__setattr__(settings, "max_tool_retries", 2)

    class _AlwaysFailsInput(BaseModel):
        pass

    class _AlwaysFailsTool(BaseTool):
        name = "always_fails_for_testing"
        description = "Always fails."
        input_schema = _AlwaysFailsInput
        requires_approval = False
        call_count = 0

        def execute(self, i):
            _AlwaysFailsTool.call_count += 1
            return ToolResult(success=False, error="simulated failure")

    controller = AgentController()
    tool = _AlwaysFailsTool()
    result = controller._execute_with_retries(tool, {}, None, [])
    assert result.success is False
    assert _AlwaysFailsTool.call_count == 3  # initial attempt + 2 retries