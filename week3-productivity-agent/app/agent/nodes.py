"""
Individual pipeline stage functions mirroring the required architecture:

  Intent and Task Analysis -> Tool Selection -> Human Approval (if required)
  -> Tool Execution -> Result Validation -> Response Generation

Each function is small, pure where possible, and independently testable.
The orchestration/looping lives in agent/controller.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent.state import SessionState
from app.tools.base import ToolResult


def interpret_request(user_input: str) -> Dict[str, Any]:
    """Basic request interpretation / guard clauses before involving the LLM."""
    text = (user_input or "").strip()
    if not text:
        return {"valid": False, "reason": "Empty user input. Please type a request."}
    return {"valid": True, "text": text}


def try_resolve_reference(state: SessionState, text: str) -> Optional[Dict[str, Any]]:
    """Attempt to resolve pronoun/ordinal references ('the second one') using
    session memory before asking the LLM to guess."""
    low = text.lower()
    reference_words = ("second one", "first one", "third one", "last one", "that task", "it",
                        "second", "first", "third", "fourth", "fifth")
    if any(w in low for w in reference_words):
        return state.resolve_ordinal_reference(text)
    return None


def needs_approval(tool) -> bool:
    return bool(getattr(tool, "requires_approval", False))


def validate_result(tool_result: ToolResult) -> Dict[str, Any]:
    """Result Validation stage: checks tool output is sufficient / not an error."""
    if not tool_result.success:
        return {"sufficient": False, "reason": tool_result.error or "Tool reported failure."}
    return {"sufficient": True, "reason": ""}


def build_status(stage: str, detail: str = "") -> Dict[str, str]:
    """Short operational status message for the UI (never chain-of-thought)."""
    return {"stage": stage, "detail": detail}
