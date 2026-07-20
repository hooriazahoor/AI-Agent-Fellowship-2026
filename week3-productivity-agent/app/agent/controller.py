"""
Agent Controller: orchestrates the full pipeline required by the spec:

  User Interface -> Agent Controller -> Intent and Task Analysis ->
  Tool Selection -> Human Approval (if required) -> Tool Execution ->
  Result Validation -> Response Generation -> Execution Log

Implements: agent decision logic (Req 5), multi-step workflows (Req 6),
human approval (Req 7), error handling (Req 8), execution limits (Req 9),
execution logging (Req 10), session memory (Req 11).
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import repository as repo
from app.tools import registry
from app.tools.base import ToolResult
from app.services.llm_service import llm_service, LLMServiceError
from app.agent.state import session_store, SessionState
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.nodes import interpret_request, try_resolve_reference, needs_approval, validate_result
from app.logging.run_logger import RunLogger, logger


@dataclass
class AgentResponse:
    status: str  # "completed" | "waiting_approval" | "error" | "clarification_needed"
    message: str
    status_trail: List[Dict[str, str]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status,
            "message": self.message,
            "status_trail": self.status_trail,
            "tool_calls": self.tool_calls,
            "pending_approval": self.pending_approval,
            "run_id": self.run_id,
        }


class AgentController:
    def __init__(self):
        self.registry = registry
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-exec")

    # ------------------------------------------------------------------
    def handle_message(self, session_id: str, user_text: str) -> AgentResponse:
        state = session_store.get_or_create(session_id)
        trail: List[Dict[str, str]] = []

        interpreted = interpret_request(user_text)
        if not interpreted["valid"]:
            trail.append({"stage": "error", "detail": interpreted["reason"]})
            return AgentResponse(status="error", message=interpreted["reason"], status_trail=trail)

        trail.append({"stage": "thinking", "detail": "Interpreting your request"})
        state.add_message("user", user_text)
        self._extract_preferences(user_text, state)

        model_label = (f"{llm_service.provider}:{llm_service.model}" if llm_service.is_configured
                       else "offline-heuristic")
        run_logger = RunLogger(session_id, user_text, model_label)

        # -- Deterministic multi-tool workflow interception (Requirement 6) --
        # These three workflows always chain multiple distinct tool calls in a fixed
        # sequence (logged individually), regardless of whether an LLM is configured.
        workflow = self._detect_workflow(user_text, state)
        if workflow is not None:
            return self._run_workflow(session_id, state, workflow, run_logger, trail)

        called_signatures = set()  # duplicate tool-call detection
        step = 0
        final_message = ""
        tool_calls_log: List[Dict[str, Any]] = []

        try:
            while step < settings.max_agent_steps:
                step += 1
                state.step_count_this_turn = step

                decision = self._decide_next_action(state, user_text, trail)

                if decision["action"] == "direct_answer":
                    trail.append({"stage": "responding", "detail": "Composing final response"})
                    final_message = decision["answer"] or "I don't have anything further to add."
                    break

                if decision["action"] == "clarify":
                    trail.append({"stage": "clarifying", "detail": decision["question"]})
                    run_logger.finish(final_outcome=f"Clarification requested: {decision['question']}")
                    state.add_message("assistant", decision["question"])
                    return AgentResponse(status="clarification_needed", message=decision["question"],
                                          status_trail=trail, run_id=run_logger.run_id)

                # -- tool_call path --
                tool_name = decision["tool_name"]
                tool_args = decision["tool_args"] or {}
                trail.append({"stage": "selecting_tool", "detail": tool_name})

                tool = self.registry.get(tool_name)
                if tool is None:
                    msg = f"Unsupported request: no tool named '{tool_name}' is available."
                    run_logger.log_error(msg)
                    trail.append({"stage": "error", "detail": msg})
                    final_message = msg
                    break

                signature = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, default=str)}"
                if signature in called_signatures:
                    msg = "Detected a repeated identical tool call - stopping to avoid a loop."
                    trail.append({"stage": "error", "detail": msg})
                    run_logger.log_error(msg)
                    final_message = ("I ran into a repeated step while handling this request, so I "
                                      "stopped early. Here's what I found so far: " +
                                      self._summarize_tool_calls(tool_calls_log))
                    break
                called_signatures.add(signature)

                # -- Human Approval stage --
                if needs_approval(tool):
                    trail.append({"stage": "waiting_approval", "detail": f"{tool_name} requires approval"})
                    approval = repo.create_pending_approval(
                        session_id=session_id, tool_name=tool_name, tool_args=tool_args,
                        proposed_action=self._describe_action(tool_name, tool_args),
                        expected_effect=tool.description, run_id=run_logger.run_id,
                    )
                    run_logger.set_approval_status("Pending")
                    run_logger.finish(final_outcome="Awaiting human approval before executing a write action.")
                    state.add_message("assistant", f"[Awaiting approval for {tool_name}]")
                    return AgentResponse(
                        status="waiting_approval",
                        message=f"This action ({tool_name}) needs your approval before I proceed.",
                        status_trail=trail, pending_approval=approval, run_id=run_logger.run_id,
                    )

                # -- Tool Execution stage (with retries + timeout handled inside tool.run) --
                trail.append({"stage": "executing_tool", "detail": f"Running {tool_name}"})
                result = self._execute_with_retries(tool, tool_args, run_logger, trail)

                # -- Result Validation stage --
                validation = validate_result(result)
                trail.append({"stage": "validating_result",
                              "detail": "OK" if validation["sufficient"] else validation["reason"]})

                run_logger.log_tool_call(tool_name, tool_args, result.model_dump())
                tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result.model_dump()})
                state.remember_tool_output(tool_name, result.data if result.success else None)

                if not result.success:
                    final_message = f"I couldn't complete that: {result.error}"
                    break

                if not llm_service.is_configured or decision.get("used_fallback"):
                    # The heuristic router does single-shot tool selection (it re-reads the
                    # original request rather than reasoning over tool results), so looping again
                    # would just re-select the same tool. Stop here with the tool's own message.
                    final_message = result.message
                    break

                # feed the tool result back as context for the next decision step
                state.add_message(
                    "assistant",
                    f"[tool_result:{tool_name}] {json.dumps(_safe_preview(result.data), default=str)[:1500]}"
                )
            else:
                final_message = ("I reached the maximum number of steps for this request. "
                                  "Here's what I found so far: " + self._summarize_tool_calls(tool_calls_log))
                trail.append({"stage": "error", "detail": "Maximum agent steps reached"})

        except LLMServiceError as e:
            trail.append({"stage": "error", "detail": str(e)})
            run_logger.log_error(str(e))
            final_message = (f"I couldn't reach the AI model ({e}). Structured actions like listing or "
                              f"creating tasks still work directly - try rephrasing as a direct command.")
        except Exception as e:  # last-resort containment so the UI never sees a stack trace
            trail.append({"stage": "error", "detail": "Unexpected internal error"})
            run_logger.log_error(str(e))
            final_message = "Something went wrong while processing that request. Please try again."

        state.add_message("assistant", final_message)
        run_logger.finish(final_outcome=final_message[:500])
        trail.append({"stage": "done", "detail": "Response ready"})
        return AgentResponse(status="completed", message=final_message, status_trail=trail,
                              tool_calls=tool_calls_log, run_id=run_logger.run_id)

    # ------------------------------------------------------------------
    def request_action(self, session_id: str, tool_name: str, tool_args: Dict[str, Any]) -> AgentResponse:
        """Entry point for direct UI actions (e.g. 'Mark Complete' / 'Edit' buttons on a
        task card) that bypass the chat/LLM decision step but still go through the same
        validation, approval, execution, logging and result-validation pipeline."""
        state = session_store.get_or_create(session_id)
        trail: List[Dict[str, str]] = [{"stage": "selecting_tool", "detail": tool_name}]

        tool = self.registry.get(tool_name)
        if tool is None:
            return AgentResponse(status="error", message=f"Unsupported request: no tool named '{tool_name}'.")

        run_logger = RunLogger(session_id, f"[UI action] {tool_name}", "ui-direct-action")

        if needs_approval(tool):
            trail.append({"stage": "waiting_approval", "detail": f"{tool_name} requires approval"})
            approval = repo.create_pending_approval(
                session_id=session_id, tool_name=tool_name, tool_args=tool_args,
                proposed_action=self._describe_action(tool_name, tool_args),
                expected_effect=tool.description, run_id=run_logger.run_id,
            )
            run_logger.set_approval_status("Pending")
            run_logger.finish(final_outcome="Awaiting human approval before executing a write action.")
            return AgentResponse(status="waiting_approval",
                                  message=f"This action ({tool_name}) needs your approval before I proceed.",
                                  status_trail=trail, pending_approval=approval, run_id=run_logger.run_id)

        result = self._execute_with_retries(tool, tool_args, run_logger, trail)
        validation = validate_result(result)
        trail.append({"stage": "validating_result",
                      "detail": "OK" if validation["sufficient"] else validation["reason"]})
        run_logger.log_tool_call(tool_name, tool_args, result.model_dump())
        state.remember_tool_output(tool_name, result.data if result.success else None)
        final_message = result.message if result.success else f"I couldn't complete that: {result.error}"
        run_logger.finish(final_outcome=final_message[:500])
        trail.append({"stage": "done", "detail": "Response ready"})
        return AgentResponse(status="completed", message=final_message, status_trail=trail,
                              tool_calls=[{"tool": tool_name, "args": tool_args, "result": result.model_dump()}],
                              run_id=run_logger.run_id)

    def resume_after_approval(self, session_id: str, approval_id: str, approved: bool,
                               edited_args: Optional[Dict[str, Any]] = None) -> AgentResponse:
        """Executes (or rejects) a tool that was paused for human approval.
        If edited_args is provided (Requirement 7: 'Edit option, if practical'), it
        overrides the originally-proposed arguments before execution."""
        state = session_store.get_or_create(session_id)
        record = repo.resolve_approval(approval_id, approved)
        if record is None:
            return AgentResponse(status="error", message="Approval request not found.")

        if edited_args is not None and approved:
            record["tool_args"] = edited_args

        run_logger = RunLogger.resume(record["run_id"]) if record.get("run_id") else None
        trail = [{"stage": "approval_resolved", "detail": "Approved" if approved else "Rejected"}]
        if edited_args is not None and approved:
            trail.append({"stage": "thinking", "detail": "Arguments were edited before approval"})

        if not approved:
            msg = "Understood - I won't perform that action. Control is back with you."
            if run_logger:
                run_logger.set_approval_status("Rejected")
                run_logger.finish(final_outcome=msg)
            state.add_message("assistant", msg)
            return AgentResponse(status="completed", message=msg, status_trail=trail,
                                  run_id=run_logger.run_id if run_logger else None)

        # -- Workflow A resume: bulk task creation from a prior meeting-notes extraction --
        if record["tool_name"] == "create_tasks_from_extraction":
            from app.agent import workflows
            outcome = workflows.resume_meeting_notes_to_tasks(record["tool_args"], run_logger)
            trail.append({"stage": "validating_result", "detail": "OK" if outcome["success"] else "Failed"})
            state.remember_tool_output("create_task", outcome["data"])
            if run_logger:
                run_logger.set_approval_status("Approved")
                run_logger.finish(final_outcome=outcome["message"][:500])
            state.add_message("assistant", outcome["message"])
            trail.append({"stage": "done", "detail": "Response ready"})
            return AgentResponse(status="completed", message=outcome["message"], status_trail=trail,
                                  tool_calls=[{"tool": "create_task", "args": t, "result": c}
                                              for t, c in zip(record["tool_args"].get("tasks", []),
                                                               outcome["data"].get("created_tasks", []))],
                                  run_id=run_logger.run_id if run_logger else None)

        tool = self.registry.get(record["tool_name"])
        if tool is None:
            msg = f"Unsupported request: tool '{record['tool_name']}' no longer available."
            return AgentResponse(status="error", message=msg, status_trail=trail)

        result = self._execute_with_retries(tool, record["tool_args"], run_logger, trail) if run_logger \
            else tool.run(record["tool_args"])
        validation = validate_result(result)
        trail.append({"stage": "validating_result",
                      "detail": "OK" if validation["sufficient"] else validation["reason"]})

        state.remember_tool_output(record["tool_name"], result.data if result.success else None)
        final_message = result.message if result.success else f"I couldn't complete that: {result.error}"

        if run_logger:
            run_logger.set_approval_status("Approved")
            run_logger.log_tool_call(record["tool_name"], record["tool_args"], result.model_dump())
            run_logger.finish(final_outcome=final_message[:500])

        state.add_message("assistant", final_message)
        trail.append({"stage": "done", "detail": "Response ready"})
        return AgentResponse(status="completed", message=final_message, status_trail=trail,
                              tool_calls=[{"tool": record["tool_name"], "args": record["tool_args"],
                                           "result": result.model_dump()}],
                              run_id=run_logger.run_id if run_logger else None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _decide_next_action(self, state: SessionState, user_text: str, trail: List[Dict]) -> Dict[str, Any]:
        """Tool Selection / Intent stage. Uses the LLM if configured, otherwise
        a deterministic keyword-based fallback router."""
        resolved_ref = try_resolve_reference(state, user_text)

        if llm_service.is_configured:
            try:
                messages = state.to_history_messages()
                if resolved_ref:
                    messages = messages + [{"role": "system",
                                             "content": f"Resolved reference -> task_id={resolved_ref['id']} "
                                                        f"title={resolved_ref['title']!r}"}]
                if state.preferences:
                    messages = messages + [{"role": "system",
                                             "content": f"Known user preferences from this session: "
                                                        f"{state.preferences}. Use these as defaults when the "
                                                        f"user doesn't specify otherwise."}]
                decision = llm_service.decide(SYSTEM_PROMPT, messages, self.registry.openai_schemas())
                if decision["action"] == "tool_call":
                    return {"action": "tool_call", "tool_name": decision["tool_name"],
                            "tool_args": decision["tool_args"]}
                return {"action": "direct_answer", "answer": decision["answer"]}
            except LLMServiceError as e:
                # Graceful degradation (Requirement 8: LLM API error): don't stop the
                # conversation - fall back to the deterministic router for this turn,
                # and record the reason in the Activity panel (not the chat bubble).
                trail.append({"stage": "error",
                              "detail": f"AI model unavailable ({e}) - using basic command matching"})
                fallback = self._heuristic_route(user_text, state, resolved_ref)
                fallback["used_fallback"] = True
                if fallback["action"] == "direct_answer":
                    fallback["answer"] += ("\n\n_(The AI model was unavailable for this request, so I "
                                           "used basic command matching instead. Structured commands still "
                                           "work normally.)_")
                return fallback

        # ---- Offline heuristic router (no LLM key configured) ----
        result = self._heuristic_route(user_text, state, resolved_ref)
        result["used_fallback"] = True
        return result

    def _relative_due_before(self, text: str) -> Optional[str]:
        """Parses common relative date phrases ('today', 'this week', ...) into an
        ISO due_before boundary, so heuristic routing can apply date filters too."""
        from datetime import datetime, timedelta
        low = text.lower()
        now = datetime.utcnow()
        if "this week" in low:
            days_until_end = 6 - now.weekday()  # Monday=0 .. Sunday=6
            return (now + timedelta(days=days_until_end + 1)).replace(
                hour=0, minute=0, second=0, microsecond=0).isoformat()
        if "next week" in low:
            days_until_next_end = 13 - now.weekday()
            return (now + timedelta(days=days_until_next_end + 1)).replace(
                hour=0, minute=0, second=0, microsecond=0).isoformat()
        if "tomorrow" in low:
            return (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        if "today" in low:
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        return None

    def _default_remind_at(self, text: str) -> str:
        """Parses a rough reminder time from free text, defaulting to tomorrow 9am
        if nothing specific is mentioned."""
        from datetime import datetime, timedelta
        low = text.lower()
        now = datetime.utcnow()
        if "today" in low:
            target = now
        elif "next week" in low:
            target = now + timedelta(days=7)
        else:
            target = now + timedelta(days=1)  # default: tomorrow
        return target.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

    def _heuristic_route(self, text: str, state: SessionState, resolved_ref: Optional[Dict]) -> Dict[str, Any]:
        low = text.lower()

        # -- Direct-answer knowledge questions about the app's own priority/status
        # definitions: no task data is needed, so no tool should be called. --
        if re.search(r"\b(difference|distinguish)\b.*\bpriorit", low) or \
           re.search(r"\bwhat (is|does|are)\b.*\bpriorit(y|ies)\b", low):
            return {"action": "direct_answer", "answer": (
                "Priority levels from highest to lowest urgency:\n"
                "- **Critical** - urgent, blocks other work, needs immediate attention\n"
                "- **High** - important and time-sensitive, but not blocking\n"
                "- **Medium** - normal priority, the default for most tasks\n"
                "- **Low** - can wait, no immediate deadline pressure"
            )}
        if re.search(r"\b(difference|distinguish)\b.*\bstatus", low) or \
           re.search(r"\bwhat (is|does|are)\b.*\bstatus(es)?\b", low):
            return {"action": "direct_answer", "answer": (
                "Task statuses:\n"
                "- **Pending** - not started yet\n"
                "- **In Progress** - actively being worked on\n"
                "- **Blocked** - can't proceed until something else is resolved\n"
                "- **Completed** - finished\n"
                "- **Cancelled** - no longer needed"
            )}

        if resolved_ref and any(k in low for k in ("complete", "done", "finish")):
            return {"action": "tool_call", "tool_name": "complete_task", "tool_args": {"task_id": resolved_ref["id"]}}
        if resolved_ref and any(k in low for k in ("update", "change", "reschedule")):
            return {"action": "tool_call", "tool_name": "update_task", "tool_args": {"task_id": resolved_ref["id"]}}
        if resolved_ref and any(k in low for k in ("delete", "remove")):
            return {"action": "tool_call", "tool_name": "delete_task", "tool_args": {"task_id": resolved_ref["id"]}}

        if re.search(r"\boverdue\b", low):
            return {"action": "tool_call", "tool_name": "detect_overdue_tasks", "tool_args": {}}
        if re.search(r"\bweekly (report|review)\b", low):
            return {"action": "tool_call", "tool_name": "generate_weekly_report", "tool_args": {}}
        if re.search(r"\bwork plan\b|\bdaily plan\b|\bprepare (a |my )?(daily )?(work )?plan\b"
                     r"|\bplan (my|for) (the )?day\b", low):
            return {"action": "tool_call", "tool_name": "generate_work_plan",
                    "tool_args": {"available_hours": 8}}
        if re.search(r"\bsearch\b.*\bnotes?\b|\bfind\b.*\bnotes?\b", low):
            query = re.sub(r".*(?:about|for)\s+", "", text, flags=re.IGNORECASE).strip(" .?!") or text
            return {"action": "tool_call", "tool_name": "search_notes", "tool_args": {"query": query}}
        if re.search(r"\bremind(er)?\b", low) and not re.search(r"\bmeeting notes|transcript\b", low):
            title = re.sub(r".*(?:create|set|add)?\s*(?:a |an )?reminder\s*(?:for|to)?", "",
                            text, flags=re.IGNORECASE).strip(" .") or text
            return {"action": "tool_call", "tool_name": "create_reminder",
                    "tool_args": {"title": title, "remind_at": self._default_remind_at(text)}}
        if re.search(r"\b(draft|write|compose)\b.*\b(follow.?up )?email\b", low):
            return {"action": "tool_call", "tool_name": "draft_followup_email",
                    "tool_args": {"meeting_notes": text}}
        if re.search(r"\bmark\b.*\bcomplete\b|\bcomplete\b.*\btask\b", low) and not resolved_ref:
            return {"action": "clarify", "question": "Which task should I mark complete? Please give the task ID "
                                                       "or list tasks first."}
        if re.search(r"\bcreate\b.*\btask", low) or low.startswith("add task"):
            title = re.sub(r".*create (a )?(reminder|task)( for| to)?", "", text, flags=re.IGNORECASE).strip(" .")
            args = {"title": title or text}
            preferred_priority = state.preferences.get("default_priority")
            if preferred_priority and not re.search(r"\b(low|medium|high|critical)\b", low):
                args["priority"] = preferred_priority
            return {"action": "tool_call", "tool_name": "create_task", "tool_args": args}
        if re.search(r"\bhigh.priority\b|\bcritical\b", low) and "task" in low:
            priority = "Critical" if "critical" in low else "High"
            args = {"priority": priority}
            due_before = self._relative_due_before(text)
            if due_before:
                args["due_before"] = due_before
            return {"action": "tool_call", "tool_name": "list_tasks", "tool_args": args}
        if re.search(r"\bshow\b|\blist\b|\ball .*tasks\b", low) and "task" in low:
            args = {}
            due_before = self._relative_due_before(text)
            if due_before:
                args["due_before"] = due_before
            return {"action": "tool_call", "tool_name": "list_tasks", "tool_args": args}
        if re.search(r"meeting notes|transcript", low) and ("task" in low or "convert" in low):
            return {"action": "tool_call", "tool_name": "convert_meeting_notes_to_tasks",
                    "tool_args": {"transcript": text}}
        if re.search(r"summarize|decisions|action items", low):
            return {"action": "tool_call", "tool_name": "extract_meeting_actions", "tool_args": {"transcript": text}}
        if re.search(r"\bsave\b.*\bnote\b", low):
            return {"action": "tool_call", "tool_name": "save_note",
                    "tool_args": {"title": text[:60], "content": text}}

        return {"action": "direct_answer",
                "answer": ("I can help with tasks, notes, and plans - try things like 'show my high-priority "
                           "tasks', 'create a task ...', or 'prepare a daily work plan'. "
                           "(Running in offline mode: no LLM API key configured, so free-form questions "
                           "are limited.)")}

    def _extract_preferences(self, text: str, state: SessionState) -> None:
        """Detects preferences the person states in plain language during the
        conversation (Requirement 11) and stores them in session memory so later
        turns can use them as defaults instead of asking again."""
        low = text.lower()

        m = re.search(r"i (?:usually |typically |normally )?(?:have|work|get)\s+(\d+(?:\.\d+)?)\s*hours?"
                       r"(?:\s+(?:a|per)\s+day)?", low)
        if m:
            state.preferences["available_hours"] = float(m.group(1))

        m = re.search(r"(?:always|usually|by default|normally) (?:set|use|make)?\s*(?:the )?priority"
                       r"\s*(?:to|as)\s+(low|medium|high|critical)", low)
        if m:
            state.preferences["default_priority"] = m.group(1).capitalize()

        m = re.search(r"\bmy name is (\w+)\b|\bcall me (\w+)\b", low)
        if m:
            state.preferences["name"] = (m.group(1) or m.group(2)).capitalize()

    def _detect_workflow(self, text: str, state: Optional[SessionState] = None) -> Optional[Dict[str, Any]]:
        """Recognizes the 3 required multi-tool workflows from natural-language phrasing,
        independent of LLM configuration."""
        low = text.lower()

        if re.search(r"\bweekly (report|review|productivity report)\b|\bthis week'?s (productivity )?report\b"
                     r"|\bweek'?s (productivity )?report\b", low):
            return {"name": "weekly_review"}

        if re.search(r"\bdaily (work )?plan\b|\bprepare a (daily )?(work )?plan\b|\bplan (my|for) (the )?day\b",
                     low) or ("work plan" in low and "weekly" not in low):
            hours_match = re.search(r"(\d+(?:\.\d+)?)\s*hours?", low)
            preferred_hours = state.preferences.get("available_hours") if state else None
            hours = float(hours_match.group(1)) if hours_match else (preferred_hours or 8.0)
            return {"name": "daily_plan", "available_hours": hours}

        if (re.search(r"meeting notes|transcript", low) and
            re.search(r"\btasks?\b|\bconvert\b|\bcreate\b|\bextract\b", low) and
            len(text.split()) > 6) or \
           re.search(r"\bconvert (this|these|the following)( notes)?\s*(into|to)\s*tasks?\b", low):
            return {"name": "meeting_notes_to_tasks", "transcript": text}

        return None

    def _run_workflow(self, session_id: str, state: SessionState, workflow: Dict[str, Any],
                       run_logger: RunLogger, trail: List[Dict]) -> AgentResponse:
        from app.agent import workflows

        name = workflow["name"]
        trail.append({"stage": "thinking", "detail": f"Running multi-step workflow: {name}"})
        try:
            if name == "meeting_notes_to_tasks":
                result = workflows.run_meeting_notes_to_tasks(session_id, workflow["transcript"], run_logger, trail)
            elif name == "daily_plan":
                result = workflows.run_daily_planning(workflow["available_hours"], None, run_logger, trail)
            elif name == "weekly_review":
                result = workflows.run_weekly_review(run_logger, trail)
            else:
                result = {"status": "completed", "message": "Unknown workflow."}
        except Exception as e:
            trail.append({"stage": "error", "detail": "Workflow failed"})
            run_logger.log_error(str(e))
            run_logger.finish(final_outcome=f"Workflow error: {e}")
            return AgentResponse(status="error", message="Something went wrong running that workflow.",
                                  status_trail=trail, run_id=run_logger.run_id)

        if result["status"] == "waiting_approval":
            run_logger.finish(final_outcome="Awaiting human approval before creating tasks.")
            state.add_message("assistant", f"[Awaiting approval for {name}]")
            return AgentResponse(status="waiting_approval", message=result["message"], status_trail=trail,
                                  pending_approval=result["pending_approval"], run_id=run_logger.run_id)

        trail.append({"stage": "responding", "detail": "Composing final response"})
        trail.append({"stage": "done", "detail": "Response ready"})
        state.add_message("assistant", result["message"])
        run_logger.finish(final_outcome=result["message"][:500])
        return AgentResponse(status="completed", message=result["message"], status_trail=trail,
                              run_id=run_logger.run_id)

    def _execute_with_retries(self, tool, tool_args: Dict[str, Any], run_logger: Optional[RunLogger],
                               trail: List[Dict]) -> ToolResult:
        attempts = 0
        last_result = None
        while attempts <= settings.max_tool_retries:
            attempts += 1
            last_result = self._run_tool_with_timeout(tool, tool_args)
            if last_result.success:
                return last_result
            trail.append({"stage": "retrying_tool", "detail": f"Attempt {attempts} failed: {last_result.error}"})
            if run_logger:
                run_logger.log_error(f"{tool.name} attempt {attempts} failed: {last_result.error}")
        return last_result

    def _run_tool_with_timeout(self, tool, tool_args: Dict[str, Any]) -> ToolResult:
        """Runs a tool in a worker thread and enforces settings.tool_timeout_seconds,
        regardless of what the tool does internally (DB call, LLM call, etc.)."""
        future = self._executor.submit(tool.run, tool_args)
        try:
            return future.result(timeout=settings.tool_timeout_seconds)
        except FutureTimeoutError:
            return ToolResult(success=False,
                               error=f"'{tool.name}' timed out after {settings.tool_timeout_seconds}s.")
        except Exception as e:  # containment: a tool must never crash the agent loop
            return ToolResult(success=False, error=f"Unexpected error running '{tool.name}': {e}")

    def _describe_action(self, tool_name: str, args: Dict[str, Any]) -> str:
        descriptions = {
            "update_task": f"Update task {args.get('task_id')} with new values.",
            "complete_task": f"Mark task {args.get('task_id')} as Completed.",
            "create_reminder": f"Create a reminder titled '{args.get('title')}'.",
            "draft_followup_email": "Draft (simulate sending) a follow-up email from meeting notes.",
            "convert_meeting_notes_to_tasks": "Create multiple tasks extracted from meeting notes.",
        }
        return descriptions.get(tool_name, f"Execute {tool_name} with the given arguments.")

    def _summarize_tool_calls(self, tool_calls_log: List[Dict[str, Any]]) -> str:
        if not tool_calls_log:
            return "no results were gathered."
        if len(tool_calls_log) == 1:
            tc = tool_calls_log[0]
            r = tc["result"]
            outcome = r.get("message", "done") if r.get("success") else r.get("error")
            return f"`{tc['tool']}` -> {outcome}"
        lines = ["**Steps taken:**", ""]
        for tc in tool_calls_log:
            r = tc["result"]
            outcome = r.get("message", "done") if r.get("success") else r.get("error")
            lines.append(f"- `{tc['tool']}`: {outcome}")
        return "\n".join(lines)


def _safe_preview(data: Any) -> Any:
    """Truncate large tool outputs before feeding back into conversation context."""
    if isinstance(data, dict):
        return {k: _safe_preview(v) for k, v in list(data.items())[:8]}
    if isinstance(data, list):
        return [_safe_preview(x) for x in data[:5]]
    return data


agent_controller = AgentController()