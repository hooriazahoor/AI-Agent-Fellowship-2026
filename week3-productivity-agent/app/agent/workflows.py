"""
Explicit multi-tool workflow orchestration (Requirement 6).

Unlike the general agent loop (which lets an LLM decide tool-by-tool), these
three workflows deterministically chain multiple *distinct* tool calls in a
fixed sequence, each logged individually to the ExecutionLog. This guarantees
the required "at least three workflows involving multiple tools" regardless
of whether an LLM API key is configured.

  Workflow A: Meeting Notes -> Tasks   (extract_meeting_actions -> approval -> N x create_task)
  Workflow B: Daily Planning           (list_tasks -> detect_overdue_tasks -> generate_work_plan)
  Workflow C: Weekly Review            (list_tasks -> detect_overdue_tasks -> list_tasks[blocked]
                                         -> generate_weekly_report -> recommend_task_priorities)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.database import repository as repo
from app.tools.task_tools import (
    CreateTaskTool, ListTasksTool, DetectOverdueTasksTool, RecommendTaskPrioritiesTool,
)
from app.tools.planning_tools import ExtractMeetingActionsTool, GenerateWorkPlanTool, GenerateWeeklyReportTool

_extract_tool = ExtractMeetingActionsTool()
_create_task_tool = CreateTaskTool()
_list_tasks_tool = ListTasksTool()
_detect_overdue_tool = DetectOverdueTasksTool()
_work_plan_tool = GenerateWorkPlanTool()
_weekly_report_tool = GenerateWeeklyReportTool()
_recommend_tool = RecommendTaskPrioritiesTool()


def _log_step(run_logger, trail: List[Dict], tool, args: Dict[str, Any], result):
    trail.append({"stage": "executing_tool", "detail": f"Running {tool.name}"})
    run_logger.log_tool_call(tool.name, args, result.model_dump())
    trail.append({"stage": "validating_result", "detail": "OK" if result.success else (result.error or "")})


# ---------------------------------------------------------------------------
# Workflow A: Meeting Notes -> Tasks (multi-tool, approval-gated)
# ---------------------------------------------------------------------------

def run_meeting_notes_to_tasks(session_id: str, transcript: str, run_logger, trail: List[Dict]) -> Dict[str, Any]:
    trail.append({"stage": "selecting_tool", "detail": "extract_meeting_actions"})
    args = {"transcript": transcript}
    extraction = _extract_tool.run(args)
    _log_step(run_logger, trail, _extract_tool, args, extraction)

    if not extraction.success:
        return {"status": "completed", "message": f"I couldn't extract meeting information: {extraction.error}"}

    action_items = extraction.data.get("action_items", [])
    if not action_items:
        return {"status": "completed",
                "message": "I read through the notes but didn't find clear action items, so no tasks "
                            "were proposed. Decisions found: " +
                            (", ".join(extraction.data.get("decisions", [])) or "none")}

    proposed = [{
        "title": item["description"][:120],
        "description": f"Auto-extracted from meeting notes. Owner: {item.get('owner') or 'unassigned'}",
        "priority": "Medium",
        "due_date": item.get("deadline"),
        "tags": ["from-meeting"],
    } for item in action_items]

    approval = repo.create_pending_approval(
        session_id=session_id, tool_name="create_tasks_from_extraction",
        tool_args={"tasks": proposed},
        proposed_action=f"Create {len(proposed)} task(s) extracted from the meeting notes.",
        expected_effect="Creates one task per action item found in the transcript.",
        run_id=run_logger.run_id,
    )
    run_logger.set_approval_status("Pending")
    trail.append({"stage": "waiting_approval", "detail": "create_tasks_from_extraction requires approval"})
    bullet_list = "\n".join(f"- {p['title']}" for p in proposed[:8])
    message = (f"### Meeting Notes -> Tasks\n\nFound **{len(proposed)}** action item(s):\n\n{bullet_list}\n\n"
               f"Please review and approve before I create these as tasks.")
    return {"status": "waiting_approval", "message": message, "pending_approval": approval}


def resume_meeting_notes_to_tasks(tool_args: Dict[str, Any], run_logger) -> Dict[str, Any]:
    """Second half of Workflow A: executes after human approval. Calls create_task once
    per proposed task, each logged as its own tool invocation."""
    created = []
    for t in tool_args.get("tasks", []):
        args = {"title": t["title"], "description": t.get("description", ""),
                 "priority": t.get("priority", "Medium"), "due_date": t.get("due_date"),
                 "tags": t.get("tags", [])}
        result = _create_task_tool.run(args)
        if run_logger:
            run_logger.log_tool_call(_create_task_tool.name, args, result.model_dump())
        if result.success:
            created.append(result.data)
    if not created:
        return {"success": False, "message": "No tasks could be created from the extracted action items.",
                "data": {"created_tasks": []}}
    bullet_list = "\n".join(f"- {c['title']} (`{c['id']}`)" for c in created)
    message = f"### Tasks Created\n\nCreated **{len(created)}** task(s) from the meeting notes:\n\n{bullet_list}"
    return {"success": True, "message": message, "data": {"created_tasks": created}}


# ---------------------------------------------------------------------------
# Workflow B: Daily Planning (multi-tool, read-only, no approval needed)
# ---------------------------------------------------------------------------

def run_daily_planning(available_hours: float, date: Optional[str], run_logger, trail: List[Dict]) -> Dict[str, Any]:
    # Step 2: "Agent retrieves pending tasks" - filter explicitly by status=Pending.
    pending_args = {"status": "Pending"}
    listed = _list_tasks_tool.run(pending_args)
    _log_step(run_logger, trail, _list_tasks_tool, pending_args, listed)

    # Step 3: "Agent identifies urgent and overdue items"
    overdue = _detect_overdue_tool.run({})
    _log_step(run_logger, trail, _detect_overdue_tool, {}, overdue)

    # Step 4: "Agent generates an ordered schedule" (considers priority, deadline,
    # status and estimated effort across Pending/In Progress/Blocked tasks internally)
    plan_args = {"available_hours": available_hours, "date": date}
    plan = _work_plan_tool.run(plan_args)
    _log_step(run_logger, trail, _work_plan_tool, plan_args, plan)

    if not plan.success:
        return {"status": "completed", "message": f"### Daily Work Plan\n\nI couldn't build a plan: {plan.error}"}

    n_overdue = overdue.data["total_count"] if overdue.success else 0
    scheduled = plan.data["scheduled"]
    deferred = plan.data["deferred_tasks"]

    # Step 5: "Agent explains its prioritization"
    lines = ["### Daily Work Plan", ""]
    lines.append(f"**Retrieved:** {listed.data['total_count']} pending task(s), **{n_overdue} overdue** overall.")
    lines.append(f"**Scheduled:** {len(scheduled)} task(s) into today's {available_hours}h budget "
                 f"({len(deferred)} deferred).")
    if scheduled:
        lines.append("")
        lines.append("**Priority order** (overdue/urgent items first, then Critical -> High -> Medium -> "
                     "Low priority, sub-sorted by earliest deadline):")
        for t in scheduled[:5]:
            lines.append(f"- {t['title']} ({t['priority']})")
    if plan.data["risk_warnings"]:
        lines.append("")
        lines.append("**Risks flagged:**")
        for r in plan.data["risk_warnings"]:
            lines.append(f"- {r}")
    return {"status": "completed", "message": "\n".join(lines), "data": plan.data}


# ---------------------------------------------------------------------------
# Workflow C: Weekly Review (multi-tool, read-only, no approval needed)
# ---------------------------------------------------------------------------

def run_weekly_review(run_logger, trail: List[Dict]) -> Dict[str, Any]:
    # Step 1: "Agent retrieves tasks from the week" - full snapshot to review;
    # the report tool below further narrows completions to the last 7 days.
    all_tasks = _list_tasks_tool.run({})
    _log_step(run_logger, trail, _list_tasks_tool, {}, all_tasks)

    # Step 2 (part a): "Agent calculates ... overdue tasks"
    overdue = _detect_overdue_tool.run({})
    _log_step(run_logger, trail, _detect_overdue_tool, {}, overdue)

    # Step 3: "Agent identifies blocked items"
    blocked_args = {"status": "Blocked"}
    blocked = _list_tasks_tool.run(blocked_args)
    _log_step(run_logger, trail, _list_tasks_tool, blocked_args, blocked)

    # Step 2 (part b) + Step 4: "Agent calculates completed tasks" and
    # "Agent generates a weekly report"
    report = _weekly_report_tool.run({})
    _log_step(run_logger, trail, _weekly_report_tool, {}, report)

    # Step 5: "Agent recommends priorities for the next week"
    recs = _recommend_tool.run({})
    _log_step(run_logger, trail, _recommend_tool, {}, recs)

    if not report.success:
        return {"status": "completed", "message": f"### Weekly Review\n\nI couldn't generate the weekly report: {report.error}"}

    lines = ["### Weekly Review", ""]
    lines.append(f"- **Completed:** {report.data['completed_count']}")
    lines.append(f"- **Overdue:** {report.data['overdue_count']}")
    lines.append(f"- **Blocked:** {report.data['blocked_count']}")
    lines.append("")
    if recs.success and recs.data["recommendations"]:
        lines.append("**Recommended priorities for next week:**")
        for r in recs.data["recommendations"][:5]:
            lines.append(f"- {r['title']} -> **{r['suggested_priority']}**")
    else:
        lines.append("No priority changes recommended for next week.")
    return {"status": "completed", "message": "\n".join(lines), "data": report.data}