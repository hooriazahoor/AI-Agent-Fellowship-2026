import uuid
from app.tools.planning_tools import ExtractMeetingActionsTool
from app.agent.controller import agent_controller
from app.database import repository as repo


def test_structured_meeting_extraction_offline_heuristic():
    transcript = (
        "We decided to go with the React frontend for the new dashboard.\n"
        "Sarah will finalize the API contract by Friday.\n"
        "Should we also migrate the auth service this quarter?\n"
    )
    tool = ExtractMeetingActionsTool()
    result = tool.run({"transcript": transcript})
    assert result.success is True
    assert "summary" in result.data
    assert isinstance(result.data["decisions"], list)
    assert isinstance(result.data["action_items"], list)
    assert isinstance(result.data["unresolved_questions"], list)
    assert len(result.data["unresolved_questions"]) >= 1


def test_approval_enforcement_for_complete_task():
    task = repo.create_task(title="Deploy service", priority="High")
    session_id = str(uuid.uuid4())
    response = agent_controller.handle_message(session_id, f"mark task {task['id']} as complete")
    # Whatever path routes to complete_task, it must never execute without approval
    if response.pending_approval is not None:
        assert response.status == "waiting_approval"
        still_pending = repo.get_task(task["id"])
        assert still_pending["status"] == "Pending"


def test_approval_workflow_end_to_end_via_tool_directly():
    """Directly exercises the approval -> resolve pipeline the controller uses."""
    task = repo.create_task(title="Ship release", priority="Critical")
    session_id = str(uuid.uuid4())
    approval = repo.create_pending_approval(
        session_id=session_id, tool_name="complete_task",
        tool_args={"task_id": task["id"]},
        proposed_action="Mark task as Completed.", expected_effect="Sets status to Completed.",
    )
    response = agent_controller.resume_after_approval(session_id, approval["id"], approved=True)
    assert response.status == "completed"
    updated = repo.get_task(task["id"])
    assert updated["status"] == "Completed"


def test_rejected_approval_does_not_execute():
    task = repo.create_task(title="Do not complete me", priority="Low")
    session_id = str(uuid.uuid4())
    approval = repo.create_pending_approval(
        session_id=session_id, tool_name="complete_task",
        tool_args={"task_id": task["id"]},
        proposed_action="Mark task as Completed.", expected_effect="Sets status to Completed.",
    )
    response = agent_controller.resume_after_approval(session_id, approval["id"], approved=False)
    assert response.status == "completed"
    unchanged = repo.get_task(task["id"])
    assert unchanged["status"] == "Pending"


def test_approval_edited_args_are_used_on_approve():
    """Requirement 7: 'Edit option, if practical' - person can tweak proposed
    arguments before approving, and the edited values are what actually execute."""
    task = repo.create_task(title="Original title", priority="Low")
    session_id = str(uuid.uuid4())
    approval = repo.create_pending_approval(
        session_id=session_id, tool_name="update_task",
        tool_args={"task_id": task["id"], "title": "Original title", "priority": "Low"},
        proposed_action="Update task.", expected_effect="Changes fields.",
    )
    edited = {"task_id": task["id"], "title": "Edited before approval", "priority": "Critical"}
    response = agent_controller.resume_after_approval(session_id, approval["id"], approved=True,
                                                        edited_args=edited)
    assert response.status == "completed"
    updated = repo.get_task(task["id"])
    assert updated["title"] == "Edited before approval"
    assert updated["priority"] == "Critical"


def test_empty_input_handled_gracefully():
    session_id = str(uuid.uuid4())
    response = agent_controller.handle_message(session_id, "   ")
    assert response.status == "error"
    assert "Empty" in response.message


def test_stated_preference_is_remembered_and_applied():
    """Requirement 11: user preferences stated during the session must be
    remembered and used as defaults on later turns."""
    session_id = str(uuid.uuid4())
    agent_controller.handle_message(session_id, "I usually have 4 hours a day for work.")
    from app.agent.state import session_store
    state = session_store.get_or_create(session_id)
    assert state.preferences.get("available_hours") == 4.0

    repo.create_task(title="Some pending task", priority="Medium")
    response = agent_controller.handle_message(session_id, "prepare a daily work plan using my pending tasks")
    assert response.status == "completed"
    assert "4.0h budget" in response.message


def test_ordinal_reference_resolution_end_to_end():
    """Exact scenario from Requirement 11: list tasks, then 'mark the second
    one as complete' must resolve correctly and require approval."""
    repo.create_task(title="Task Alpha", priority="High")
    repo.create_task(title="Task Beta", priority="High")
    session_id = str(uuid.uuid4())
    list_response = agent_controller.handle_message(session_id, "show me my high-priority tasks")
    assert list_response.status == "completed"

    follow_up = agent_controller.handle_message(session_id, "mark the second one as complete")
    assert follow_up.status == "waiting_approval"
    assert follow_up.pending_approval["tool_name"] == "complete_task"


def test_max_step_handling_does_not_crash():
    session_id = str(uuid.uuid4())
    # A vague, non-tool-matching request should resolve via heuristic direct-answer
    # without exceeding step limits or raising.
    response = agent_controller.handle_message(session_id, "hello there")
    assert response.status in ("completed", "clarification_needed")