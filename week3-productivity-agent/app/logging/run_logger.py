"""
Execution logging (Requirement 10). Every agent run is recorded to the
ExecutionLog table via the repository layer. Never logs API keys or raw
chain-of-thought -- only structured operational data.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.database import repository as repo

# Standard Python logging to stdout/file for ops visibility (separate from DB run logs)
logger = logging.getLogger("productivity_agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class RunLogger:
    """One instance per agent run. Accumulates structured events, then
    flushes them to the ExecutionLog table when the run ends."""

    def __init__(self, session_id: str, user_request: str, selected_model: str,
                 _existing_run: Optional[Dict[str, Any]] = None):
        self.session_id = session_id
        self.user_request = user_request
        self.selected_model = selected_model
        self._start = time.time()
        if _existing_run:
            self.run_record = _existing_run
            self.run_id = _existing_run["id"]
            self.tools_called = list(_existing_run.get("tools_called", []))
            self.tool_arguments = list(_existing_run.get("tool_arguments", []))
            self.tool_results = list(_existing_run.get("tool_results", []))
            self.errors = list(_existing_run.get("errors", []))
            self.approval_status = _existing_run.get("approval_status", "Not Required")
            self.step_count = _existing_run.get("step_count", 0)
            logger.info("Run %s resumed for session %s", self.run_id, session_id)
        else:
            self.run_record = repo.create_execution_log(session_id, user_request, selected_model)
            self.run_id = self.run_record["id"]
            self.tools_called: List[str] = []
            self.tool_arguments: List[Dict[str, Any]] = []
            self.tool_results: List[Dict[str, Any]] = []
            self.errors: List[str] = []
            self.approval_status = "Not Required"
            self.step_count = 0
            logger.info("Run %s started for session %s: %r", self.run_id, session_id, user_request)

    @classmethod
    def resume(cls, run_id: str) -> Optional["RunLogger"]:
        record = repo.get_execution_log(run_id)
        if not record:
            return None
        return cls(record["session_id"], record["user_request"], record["selected_model"],
                    _existing_run=record)

    def log_tool_call(self, tool_name: str, args: Dict[str, Any], result_summary: Dict[str, Any]):
        self.tools_called.append(tool_name)
        self.tool_arguments.append(args)
        self.tool_results.append(result_summary)
        self.step_count += 1
        logger.info("Run %s: tool=%s args=%s success=%s", self.run_id, tool_name, args,
                     result_summary.get("success"))

    def log_error(self, message: str):
        self.errors.append(message)
        logger.warning("Run %s error: %s", self.run_id, message)

    def set_approval_status(self, status: str):
        self.approval_status = status

    def finish(self, final_outcome: str) -> Dict[str, Any]:
        duration_ms = int((time.time() - self._start) * 1000)
        updated = repo.update_execution_log(
            self.run_id,
            tools_called=self.tools_called,
            tool_arguments=self.tool_arguments,
            tool_results=self.tool_results,
            errors=self.errors,
            approval_status=self.approval_status,
            end_time=datetime.utcnow(),
            total_duration_ms=duration_ms,
            final_outcome=final_outcome,
            step_count=self.step_count,
        )
        logger.info("Run %s finished in %dms, steps=%d, outcome=%r",
                    self.run_id, duration_ms, self.step_count, final_outcome[:120])
        return updated
