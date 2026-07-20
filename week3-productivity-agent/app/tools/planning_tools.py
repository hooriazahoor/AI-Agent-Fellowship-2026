"""
Planning tools: Extract Meeting Actions, Generate Work Plan (required Tools 7-8),
plus bonus tools: Create Reminder, Draft Follow-up Email, Generate Weekly Report,
Convert Meeting Notes Into Tasks, Export Report.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel, Field
from dateutil import parser as dateparser

from app.database import repository as repo
from app.tools.base import BaseTool, ToolResult
from app.services.llm_service import llm_service

VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}


# ---------------------------------------------------------------------------
# Tool 7: Extract Meeting Actions
# ---------------------------------------------------------------------------

class ExtractMeetingActionsInput(BaseModel):
    transcript: str = Field(..., min_length=1, description="Meeting notes or transcript text")


class ExtractMeetingActionsTool(BaseTool):
    name = "extract_meeting_actions"
    description = ("Extract a structured summary, decisions, action items (with owners/deadlines "
                    "when available), and unresolved questions from meeting notes or a transcript.")
    input_schema = ExtractMeetingActionsInput
    requires_approval = False

    def execute(self, i: ExtractMeetingActionsInput) -> ToolResult:
        result = llm_service.extract_meeting_actions(i.transcript)
        return ToolResult(success=True, data=result,
                           message=f"Extracted {len(result.get('action_items', []))} action item(s) "
                                   f"and {len(result.get('decisions', []))} decision(s).")


# ---------------------------------------------------------------------------
# Tool 8: Generate Work Plan
# ---------------------------------------------------------------------------

class GenerateWorkPlanInput(BaseModel):
    available_hours: float = Field(..., gt=0, description="Hours available for the plan")
    date: Optional[str] = Field(None, description="Date the plan is for (default: today)")
    task_ids: Optional[List[str]] = Field(None, description="Restrict plan to these task IDs; default all pending")
    user_priorities: Optional[List[str]] = Field(default_factory=list, description="Tags/keywords user cares about")


class GenerateWorkPlanTool(BaseTool):
    name = "generate_work_plan"
    description = ("Generate an ordered daily/weekly work plan from pending tasks, considering "
                    "priority, deadline, status, and estimated effort. Highlights risks and defers "
                    "tasks that don't fit the available hours.")
    input_schema = GenerateWorkPlanInput
    requires_approval = False

    def execute(self, i: GenerateWorkPlanInput) -> ToolResult:
        if i.task_ids:
            candidates = [t for t in repo.list_tasks() if t["id"] in i.task_ids]
        else:
            candidates = [t for t in repo.list_tasks() if t["status"] in ("Pending", "In Progress", "Blocked")]

        priority_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        now = datetime.utcnow()

        def sort_key(t):
            due = dateparser.parse(t["due_date"]) if t["due_date"] else now + timedelta(days=3650)
            user_boost = 0
            if i.user_priorities:
                haystack = f"{t['title']} {' '.join(t['tags'])}".lower()
                if any(p.lower() in haystack for p in i.user_priorities):
                    user_boost = -1
            return (user_boost, priority_rank.get(t["priority"], 2), due)

        candidates.sort(key=sort_key)

        budget_minutes = i.available_hours * 60
        scheduled, deferred, risks = [], [], []
        used = 0.0
        for t in candidates:
            effort = t.get("estimated_effort_minutes") or 45
            if t["status"] == "Blocked":
                risks.append(f"'{t['title']}' is Blocked and cannot be completed until unblocked.")
                deferred.append(t)
                continue
            if t["due_date"]:
                due = dateparser.parse(t["due_date"])
                if due < now:
                    risks.append(f"'{t['title']}' is overdue (was due {due.date()}).")
            if used + effort <= budget_minutes:
                scheduled.append({**t, "estimated_effort_minutes": effort})
                used += effort
            else:
                deferred.append(t)

        if used < budget_minutes * 0.5 and len(candidates) <= len(scheduled):
            risks.append("Plenty of spare capacity today - consider pulling in lower-priority tasks.")
        if deferred and any(d["priority"] in ("Critical", "High") for d in deferred):
            risks.append("Some high/critical priority tasks did not fit in the available hours.")

        plan = {
            "date": i.date or now.date().isoformat(),
            "available_hours": i.available_hours,
            "scheduled": scheduled,
            "deferred_tasks": deferred,
            "recommended_focus_areas": [t["title"] for t in scheduled[:3]],
            "risk_warnings": risks,
            "total_scheduled_minutes": used,
        }
        return ToolResult(success=True, data=plan,
                           message=f"Scheduled {len(scheduled)} task(s), deferred {len(deferred)}.")


# ---------------------------------------------------------------------------
# Bonus Tool: Create Reminder  (write action -> requires approval)
# ---------------------------------------------------------------------------

class CreateReminderInput(BaseModel):
    title: str = Field(..., min_length=1)
    remind_at: str = Field(..., description="ISO date/time string for the reminder")
    notes: str = ""


class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = "Create a reminder (stored as a lightweight task tagged 'reminder')."
    input_schema = CreateReminderInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: CreateReminderInput) -> ToolResult:
        due = dateparser.parse(i.remind_at)
        task = repo.create_task(
            title=f"Reminder: {i.title}", description=i.notes, priority="Medium",
            due_date=due, tags=["reminder"], source="agent",
        )
        return ToolResult(success=True, data=task, message=f"Reminder set for {due.isoformat()}.")


# ---------------------------------------------------------------------------
# Bonus Tool: Draft Follow-up Email  (write/output action -> requires approval to "send")
# ---------------------------------------------------------------------------

class DraftFollowupEmailInput(BaseModel):
    meeting_notes: str = Field(..., min_length=1)
    recipient_name: Optional[str] = None
    tone: str = Field("professional", description="professional | friendly | concise")


class DraftFollowupEmailTool(BaseTool):
    name = "draft_followup_email"
    description = "Draft a follow-up email based on meeting notes (simulated send - requires approval)."
    input_schema = DraftFollowupEmailInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: DraftFollowupEmailInput) -> ToolResult:
        extraction = llm_service.extract_meeting_actions(i.meeting_notes)
        greeting = f"Hi {i.recipient_name}," if i.recipient_name else "Hi all,"
        action_lines = "\n".join(
            f"- {a['description']}" + (f" (Owner: {a['owner']})" if a.get("owner") else "")
            for a in extraction.get("action_items", [])
        ) or "- (no action items identified)"
        decision_lines = "\n".join(f"- {d}" for d in extraction.get("decisions", [])) or "- (no decisions recorded)"

        body = (
            f"{greeting}\n\nThanks for the discussion. Quick recap:\n\n"
            f"Summary:\n{extraction.get('summary', '')}\n\n"
            f"Decisions:\n{decision_lines}\n\n"
            f"Action Items:\n{action_lines}\n\n"
            f"Please let me know if anything is missing.\n\nBest regards"
        )
        return ToolResult(success=True, data={"subject": "Follow-up: Meeting Recap", "body": body},
                           message="Draft follow-up email prepared (simulated send, not actually sent).")


# ---------------------------------------------------------------------------
# Bonus Tool: Generate Weekly Report
# ---------------------------------------------------------------------------

class GenerateWeeklyReportInput(BaseModel):
    week_start: Optional[str] = None


class GenerateWeeklyReportTool(BaseTool):
    name = "generate_weekly_report"
    description = "Generate a weekly productivity report: completed, overdue, blocked tasks and next-week priorities."
    input_schema = GenerateWeeklyReportInput
    requires_approval = False

    def execute(self, i: GenerateWeeklyReportInput) -> ToolResult:
        start = dateparser.parse(i.week_start) if i.week_start else datetime.utcnow() - timedelta(days=7)
        end = start + timedelta(days=7)
        all_tasks = repo.list_tasks()

        completed = [t for t in all_tasks if t["status"] == "Completed" and t["updated_date"]
                     and start.isoformat() <= t["updated_date"] <= end.isoformat()]
        overdue = repo.overdue_tasks()
        blocked = [t for t in all_tasks if t["status"] == "Blocked"]
        pending_high = [t for t in all_tasks if t["status"] in ("Pending", "In Progress")
                         and t["priority"] in ("High", "Critical")]

        report = {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "completed_count": len(completed),
            "completed_tasks": completed,
            "overdue_count": len(overdue),
            "overdue_tasks": overdue,
            "blocked_count": len(blocked),
            "blocked_tasks": blocked,
            "recommended_next_week_priorities": [t["title"] for t in pending_high[:5]],
        }
        return ToolResult(success=True, data=report,
                           message=f"Weekly report: {len(completed)} completed, {len(overdue)} overdue, "
                                   f"{len(blocked)} blocked.")


# ---------------------------------------------------------------------------
# Bonus Tool: Convert Meeting Notes Into Tasks  (write action -> requires approval)
# ---------------------------------------------------------------------------

class ConvertMeetingNotesToTasksInput(BaseModel):
    transcript: str = Field(..., min_length=1)
    default_priority: str = "Medium"


class ConvertMeetingNotesToTasksTool(BaseTool):
    name = "convert_meeting_notes_to_tasks"
    description = ("Extract action items from meeting notes and create tasks from them. "
                    "Creates multiple tasks, so it requires human approval.")
    input_schema = ConvertMeetingNotesToTasksInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: ConvertMeetingNotesToTasksInput) -> ToolResult:
        extraction = llm_service.extract_meeting_actions(i.transcript)
        created = []
        for item in extraction.get("action_items", []):
            due = None
            if item.get("deadline"):
                try:
                    due = dateparser.parse(item["deadline"])
                except Exception:
                    due = None
            task = repo.create_task(
                title=item["description"][:120],
                description=f"Auto-created from meeting notes. Owner: {item.get('owner') or 'unassigned'}",
                priority=i.default_priority if i.default_priority in VALID_PRIORITIES else "Medium",
                due_date=due, tags=["from-meeting"], source="meeting_notes",
            )
            created.append(task)
        return ToolResult(success=True, data={"created_tasks": created, "total_count": len(created)},
                           message=f"Created {len(created)} task(s) from meeting notes.")


# ---------------------------------------------------------------------------
# Bonus Tool: Export Report as Markdown
# ---------------------------------------------------------------------------

class ExportReportInput(BaseModel):
    report_type: str = Field("weekly", description="weekly | plan")
    content: dict = Field(..., description="The report/plan data to export")


class ExportReportTool(BaseTool):
    name = "export_report"
    description = "Export a weekly report or work plan as a Markdown document."
    input_schema = ExportReportInput
    requires_approval = False

    def execute(self, i: ExportReportInput) -> ToolResult:
        c = i.content
        if i.report_type == "weekly":
            md = (
                f"# Weekly Productivity Report\n\n"
                f"**Period:** {c.get('period_start', '')} to {c.get('period_end', '')}\n\n"
                f"- Completed: {c.get('completed_count', 0)}\n"
                f"- Overdue: {c.get('overdue_count', 0)}\n"
                f"- Blocked: {c.get('blocked_count', 0)}\n\n"
                f"## Next Week Priorities\n" +
                "\n".join(f"- {p}" for p in c.get("recommended_next_week_priorities", []))
            )
        else:
            md = (
                f"# Work Plan - {c.get('date', '')}\n\n"
                f"**Available hours:** {c.get('available_hours', '')}\n\n"
                f"## Scheduled\n" + "\n".join(f"- {t['title']}" for t in c.get("scheduled", [])) +
                f"\n\n## Deferred\n" + "\n".join(f"- {t['title']}" for t in c.get("deferred_tasks", [])) +
                f"\n\n## Risks\n" + "\n".join(f"- {r}" for r in c.get("risk_warnings", []))
            )
        return ToolResult(success=True, data={"markdown": md}, message="Report exported as Markdown.")
