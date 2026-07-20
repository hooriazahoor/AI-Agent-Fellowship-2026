"""
Task-management tools: Create, List, Update, Complete (required),
plus bonus tools: DetectOverdueTasks, EstimateTaskEffort,
IdentifyConflictingDeadlines, RecommendTaskPriorities.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from dateutil import parser as dateparser

from app.database import repository as repo
from app.tools.base import BaseTool, ToolResult

VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_STATUSES = {"Pending", "In Progress", "Blocked", "Completed", "Cancelled"}


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return dateparser.parse(str(value))


# ---------------------------------------------------------------------------
# Tool 1: Create Task
# ---------------------------------------------------------------------------

class CreateTaskInput(BaseModel):
    title: str = Field(..., min_length=1, description="Task title")
    description: str = Field("", description="Task description")
    priority: str = Field("Medium", description="Low | Medium | High | Critical")
    due_date: Optional[str] = Field(None, description="ISO date/time string, optional")
    tags: List[str] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v):
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v


class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Create a new task with title, description, priority, due date and tags."
    input_schema = CreateTaskInput
    requires_approval = False  # single task creation from direct request does not require approval;
    is_write_action = True     # bulk creation (e.g. from meeting notes) is gated at the workflow level

    def execute(self, i: CreateTaskInput) -> ToolResult:
        due = _parse_date(i.due_date)
        task = repo.create_task(
            title=i.title, description=i.description, priority=i.priority,
            due_date=due, tags=i.tags, source="user",
        )
        return ToolResult(success=True, data=task, message=f"Created task '{task['title']}' ({task['id']}).")


# ---------------------------------------------------------------------------
# Tool 2: List Tasks
# ---------------------------------------------------------------------------

class ListTasksInput(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    due_before: Optional[str] = None
    due_after: Optional[str] = None
    tag: Optional[str] = None


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = "List tasks, optionally filtered by status, priority, due date range, or tag."
    input_schema = ListTasksInput
    requires_approval = False

    def execute(self, i: ListTasksInput) -> ToolResult:
        results = repo.list_tasks(
            status=i.status, priority=i.priority,
            due_before=_parse_date(i.due_before), due_after=_parse_date(i.due_after),
            tag=i.tag,
        )
        return ToolResult(success=True, data={"tasks": results, "total_count": len(results)},
                           message=f"Found {len(results)} matching task(s).")


# ---------------------------------------------------------------------------
# Tool 3: Update Task  (write action -> requires approval)
# ---------------------------------------------------------------------------

class UpdateTaskInput(BaseModel):
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v):
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v

    @field_validator("status")
    @classmethod
    def check_status(cls, v):
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v


class UpdateTaskTool(BaseTool):
    name = "update_task"
    description = "Update fields on an existing task (title, description, priority, due date, status, tags)."
    input_schema = UpdateTaskInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: UpdateTaskInput) -> ToolResult:
        existing = repo.get_task(i.task_id)
        if not existing:
            return ToolResult(success=False, error=f"Unknown task ID: {i.task_id}")
        changes = {k: v for k, v in i.model_dump().items() if k != "task_id" and v is not None}
        if "due_date" in changes:
            changes["due_date"] = _parse_date(changes["due_date"])
        task = repo.update_task(i.task_id, **changes)
        return ToolResult(success=True, data=task, message=f"Updated task '{task['title']}' ({task['id']}).")


# ---------------------------------------------------------------------------
# Tool 4: Complete Task (write action -> requires approval)
# ---------------------------------------------------------------------------

class CompleteTaskInput(BaseModel):
    task_id: str


class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = "Mark a task as Completed. This is irreversible and requires human approval."
    input_schema = CompleteTaskInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: CompleteTaskInput) -> ToolResult:
        existing = repo.get_task(i.task_id)
        if not existing:
            return ToolResult(success=False, error=f"Unknown task ID: {i.task_id}")
        task = repo.complete_task(i.task_id)
        return ToolResult(success=True, data=task,
                           message=f"Marked '{task['title']}' complete at {task['updated_date']}.")


class DeleteTaskInput(BaseModel):
    task_id: str


class DeleteTaskTool(BaseTool):
    name = "delete_task"
    description = "Permanently delete a task record. This is irreversible and requires human approval."
    input_schema = DeleteTaskInput
    requires_approval = True
    is_write_action = True

    def execute(self, i: DeleteTaskInput) -> ToolResult:
        existing = repo.get_task(i.task_id)
        if not existing:
            return ToolResult(success=False, error=f"Unknown task ID: {i.task_id}")
        repo.delete_task(i.task_id)
        return ToolResult(success=True, data={"deleted_task_id": i.task_id},
                           message=f"Deleted task '{existing['title']}' ({i.task_id}).")


# ---------------------------------------------------------------------------
# Bonus Tool: Detect Overdue Tasks
# ---------------------------------------------------------------------------

class DetectOverdueTasksInput(BaseModel):
    pass


class DetectOverdueTasksTool(BaseTool):
    name = "detect_overdue_tasks"
    description = "Find all tasks that are overdue (past due date and not completed/cancelled)."
    input_schema = DetectOverdueTasksInput
    requires_approval = False

    def execute(self, i: DetectOverdueTasksInput) -> ToolResult:
        results = repo.overdue_tasks()
        return ToolResult(success=True, data={"overdue_tasks": results, "total_count": len(results)},
                           message=f"Found {len(results)} overdue task(s).")


# ---------------------------------------------------------------------------
# Bonus Tool: Estimate Task Effort
# ---------------------------------------------------------------------------

class EstimateTaskEffortInput(BaseModel):
    task_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class EstimateTaskEffortTool(BaseTool):
    name = "estimate_task_effort"
    description = "Heuristically estimate how many minutes a task will take, based on its text."
    input_schema = EstimateTaskEffortInput
    requires_approval = False

    def execute(self, i: EstimateTaskEffortInput) -> ToolResult:
        title, description = i.title, i.description
        task = None
        if i.task_id:
            task = repo.get_task(i.task_id)
            if not task:
                return ToolResult(success=False, error=f"Unknown task ID: {i.task_id}")
            title, description = task["title"], task["description"]

        text = f"{title or ''} {description or ''}".lower()
        # simple heuristic model: base effort + keyword weighting
        minutes = 30
        weight_map = {
            "email": 15, "call": 20, "meeting": 45, "review": 30, "write": 60,
            "design": 90, "build": 120, "fix": 45, "research": 60, "deploy": 60,
            "report": 60, "plan": 30, "test": 45, "presentation": 90,
        }
        for kw, w in weight_map.items():
            if kw in text:
                minutes += w
        minutes = min(minutes, 480)  # cap at 8 hours
        if i.task_id:
            repo.update_task(i.task_id, estimated_effort_minutes=minutes)
        return ToolResult(success=True, data={"estimated_effort_minutes": minutes},
                           message=f"Estimated effort: {minutes} minutes.")


# ---------------------------------------------------------------------------
# Bonus Tool: Identify Conflicting Deadlines
# ---------------------------------------------------------------------------

class IdentifyConflictingDeadlinesInput(BaseModel):
    window_hours: int = Field(4, description="Tasks due within this many hours of each other are flagged")


class IdentifyConflictingDeadlinesTool(BaseTool):
    name = "identify_conflicting_deadlines"
    description = "Find tasks whose due dates cluster too closely together, signalling scheduling conflicts."
    input_schema = IdentifyConflictingDeadlinesInput
    requires_approval = False

    def execute(self, i: IdentifyConflictingDeadlinesInput) -> ToolResult:
        tasks = [t for t in repo.list_tasks() if t["due_date"] and t["status"] not in ("Completed", "Cancelled")]
        tasks.sort(key=lambda t: t["due_date"])
        conflicts = []
        for a, b in zip(tasks, tasks[1:]):
            ta = dateparser.parse(a["due_date"])
            tb = dateparser.parse(b["due_date"])
            if abs((tb - ta).total_seconds()) <= i.window_hours * 3600:
                conflicts.append({"task_a": a, "task_b": b, "gap_hours": round(abs((tb - ta).total_seconds()) / 3600, 2)})
        return ToolResult(success=True, data={"conflicts": conflicts, "total_count": len(conflicts)},
                           message=f"Found {len(conflicts)} potential deadline conflict(s).")


# ---------------------------------------------------------------------------
# Bonus Tool: Recommend Task Priorities
# ---------------------------------------------------------------------------

class RecommendTaskPrioritiesInput(BaseModel):
    pass


class RecommendTaskPrioritiesTool(BaseTool):
    name = "recommend_task_priorities"
    description = "Recommend priority adjustments based on due dates and current status."
    input_schema = RecommendTaskPrioritiesInput
    requires_approval = False

    def execute(self, i: RecommendTaskPrioritiesInput) -> ToolResult:
        now = datetime.utcnow()
        recs = []
        for t in repo.list_tasks():
            if t["status"] in ("Completed", "Cancelled") or not t["due_date"]:
                continue
            due = dateparser.parse(t["due_date"])
            hours_left = (due - now).total_seconds() / 3600
            suggested = t["priority"]
            if hours_left < 24 and t["priority"] not in ("Critical",):
                suggested = "Critical"
            elif hours_left < 72 and t["priority"] not in ("Critical", "High"):
                suggested = "High"
            if suggested != t["priority"]:
                recs.append({"task_id": t["id"], "title": t["title"], "current_priority": t["priority"],
                              "suggested_priority": suggested, "hours_until_due": round(hours_left, 1)})
        return ToolResult(success=True, data={"recommendations": recs, "total_count": len(recs)},
                           message=f"{len(recs)} priority adjustment(s) recommended.")