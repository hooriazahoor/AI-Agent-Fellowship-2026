"""
Tool registry: instantiates every tool exactly once and exposes it to the
agent controller. Adding a new tool = write the class + register it here.
"""
from app.tools.base import ToolRegistry
from app.tools.task_tools import (
    CreateTaskTool, ListTasksTool, UpdateTaskTool, CompleteTaskTool, DeleteTaskTool,
    DetectOverdueTasksTool, EstimateTaskEffortTool,
    IdentifyConflictingDeadlinesTool, RecommendTaskPrioritiesTool,
)
from app.tools.note_tools import SearchNotesTool, SaveNoteTool, SummarizeNotesTool, DeleteNoteTool
from app.tools.planning_tools import (
    ExtractMeetingActionsTool, GenerateWorkPlanTool, CreateReminderTool,
    DraftFollowupEmailTool, GenerateWeeklyReportTool,
    ConvertMeetingNotesToTasksTool, ExportReportTool,
)

registry = ToolRegistry()

for tool_cls in [
    CreateTaskTool, ListTasksTool, UpdateTaskTool, CompleteTaskTool,          # required 1-4
    SearchNotesTool, SaveNoteTool,                                           # required 5-6
    ExtractMeetingActionsTool, GenerateWorkPlanTool,                         # required 7-8
    DeleteTaskTool, DeleteNoteTool,                                          # bonus: irreversible/delete actions
    DetectOverdueTasksTool, EstimateTaskEffortTool,                          # bonus
    IdentifyConflictingDeadlinesTool, RecommendTaskPrioritiesTool,           # bonus
    SummarizeNotesTool, CreateReminderTool, DraftFollowupEmailTool,          # bonus
    GenerateWeeklyReportTool, ConvertMeetingNotesToTasksTool, ExportReportTool,  # bonus
]:
    registry.register(tool_cls())