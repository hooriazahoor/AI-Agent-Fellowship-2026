import pytest
from app.database import repository as repo
from app.tools.task_tools import CreateTaskTool, ListTasksTool, UpdateTaskTool, CompleteTaskTool
from app.tools.base import ToolValidationError


def test_task_creation():
    tool = CreateTaskTool()
    result = tool.run({"title": "Write report", "priority": "High", "tags": ["work"]})
    assert result.success is True
    assert result.data["title"] == "Write report"
    assert result.data["priority"] == "High"
    assert result.data["status"] == "Pending"


def test_task_listing_with_filters():
    repo.create_task(title="A", priority="Low")
    repo.create_task(title="B", priority="Critical")
    tool = ListTasksTool()
    result = tool.run({"priority": "Critical"})
    assert result.success is True
    assert result.data["total_count"] == 1
    assert result.data["tasks"][0]["title"] == "B"


def test_task_update():
    created = repo.create_task(title="Old title", priority="Low")
    tool = UpdateTaskTool()
    result = tool.run({"task_id": created["id"], "title": "New title", "priority": "High"})
    assert result.success is True
    assert result.data["title"] == "New title"
    assert result.data["priority"] == "High"


def test_invalid_task_id_on_update():
    tool = UpdateTaskTool()
    result = tool.run({"task_id": "task-does-not-exist", "title": "X"})
    assert result.success is False
    assert "Unknown task ID" in result.error


def test_invalid_task_id_on_complete():
    tool = CompleteTaskTool()
    result = tool.run({"task_id": "task-does-not-exist"})
    assert result.success is False
    assert "Unknown task ID" in result.error


def test_complete_task():
    created = repo.create_task(title="Ship feature", priority="Medium")
    tool = CompleteTaskTool()
    result = tool.run({"task_id": created["id"]})
    assert result.success is True
    assert result.data["status"] == "Completed"


def test_tool_input_validation_rejects_bad_priority():
    tool = CreateTaskTool()
    result = tool.run({"title": "X", "priority": "Super Urgent"})
    assert result.success is False
    assert "Invalid tool arguments" in result.error


def test_tool_input_validation_rejects_missing_title():
    tool = CreateTaskTool()
    result = tool.run({"priority": "Low"})
    assert result.success is False


def test_delete_task_requires_approval_and_removes_record():
    from app.tools.task_tools import DeleteTaskTool
    task = repo.create_task(title="Temporary task", priority="Low")
    tool = DeleteTaskTool()
    assert tool.requires_approval is True
    result = tool.run({"task_id": task["id"]})
    assert result.success is True
    assert repo.get_task(task["id"]) is None


def test_delete_task_invalid_id():
    from app.tools.task_tools import DeleteTaskTool
    tool = DeleteTaskTool()
    result = tool.run({"task_id": "task-does-not-exist"})
    assert result.success is False
    assert "Unknown task ID" in result.error


def test_database_persistence():
    created = repo.create_task(title="Persisted task", priority="Medium")
    fetched = repo.get_task(created["id"])
    assert fetched is not None
    assert fetched["title"] == "Persisted task"