"""
Agent state / session memory (Requirement 11).

Kept server-side, keyed by Flask session id, in a simple in-memory store.
Tracks recent messages, tasks/notes referenced, previous tool outputs, and
user preferences stated during the session -- so follow-ups like
"mark the second one as complete" resolve correctly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionState:
    session_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)          # {"role", "content"}
    last_listed_tasks: List[Dict[str, Any]] = field(default_factory=list)  # for "the second one"
    last_listed_notes: List[Dict[str, Any]] = field(default_factory=list)
    last_tool_outputs: List[Dict[str, Any]] = field(default_factory=list)  # rolling window
    preferences: Dict[str, Any] = field(default_factory=dict)              # e.g. default work hours
    step_count_this_turn: int = 0

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # keep memory bounded
        self.messages = self.messages[-30:]

    def remember_tool_output(self, tool_name: str, data: Any):
        self.last_tool_outputs.append({"tool": tool_name, "data": data})
        self.last_tool_outputs = self.last_tool_outputs[-10:]
        if tool_name == "list_tasks" and isinstance(data, dict):
            self.last_listed_tasks = data.get("tasks", [])
        if tool_name == "search_notes" and isinstance(data, dict):
            self.last_listed_notes = data.get("notes", [])

    def resolve_ordinal_reference(self, phrase: str) -> Optional[Dict[str, Any]]:
        """Resolve phrases like 'the second one', 'the first task' against the
        last list of tasks shown in this session."""
        ordinals = {
            "first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
            "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "last": -1,
        }
        low = phrase.lower()
        for word, idx in ordinals.items():
            if word in low and self.last_listed_tasks:
                try:
                    return self.last_listed_tasks[idx]
                except IndexError:
                    return None
        return None

    def to_history_messages(self) -> List[Dict[str, str]]:
        return list(self.messages)


class SessionStore:
    """Simple in-memory session store. Suitable for a single-process dev/demo
    deployment; swap for Redis in a production multi-worker deployment."""

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def reset(self, session_id: str):
        self._sessions.pop(session_id, None)


session_store = SessionStore()
