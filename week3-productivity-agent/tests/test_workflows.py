import uuid
from app.agent.controller import agent_controller
from app.database import repository as repo


def test_workflow_daily_planning_calls_multiple_tools():
    repo.create_task(title="Task A", priority="High")
    repo.create_task(title="Task B", priority="Low")
    session_id = str(uuid.uuid4())
    response = agent_controller.handle_message(session_id, "prepare a daily work plan using my pending tasks")
    assert response.status == "completed"
    log = repo.get_execution_log(response.run_id)
    assert set(["list_tasks", "detect_overdue_tasks", "generate_work_plan"]).issubset(set(log["tools_called"]))


def test_workflow_weekly_review_calls_multiple_tools():
    repo.create_task(title="Task C", priority="Medium")
    session_id = str(uuid.uuid4())
    response = agent_controller.handle_message(session_id, "prepare a weekly productivity report")
    assert response.status == "completed"
    log = repo.get_execution_log(response.run_id)
    assert "generate_weekly_report" in log["tools_called"]
    assert "recommend_task_priorities" in log["tools_called"]
    assert log["tools_called"].count("list_tasks") >= 2  # all tasks + blocked-only pass


def test_workflow_meeting_notes_to_tasks_end_to_end():
    session_id = str(uuid.uuid4())
    transcript = ("Please convert these meeting notes into tasks: We decided to use Postgres. "
                  "Sarah will finalize the API contract by Friday. John needs to update the docs.")
    response = agent_controller.handle_message(session_id, transcript)
    assert response.status == "waiting_approval"
    assert response.pending_approval["tool_name"] == "create_tasks_from_extraction"

    approved = agent_controller.resume_after_approval(session_id, response.pending_approval["id"], approved=True)
    assert approved.status == "completed"
    assert len(approved.tool_calls) >= 1
    log = repo.get_execution_log(response.run_id)
    assert "extract_meeting_actions" in log["tools_called"]
    assert "create_task" in log["tools_called"]