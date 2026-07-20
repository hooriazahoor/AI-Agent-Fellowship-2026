"""
Agent Evaluation Dataset (Assignment 5).

35 test cases across 5 categories (spec minimums in parentheses):
  - Direct Response Cases   (min 5)  -> 6 cases
  - Single-Tool Cases       (min 8)  -> 9 cases
  - Multi-Tool Cases        (min 8)  -> 9 cases
  - Approval Cases          (min 5)  -> 6 cases
  - Failure / Edge Cases    (min 4)  -> 5 cases

Each case is executed for real against the live AgentController (see
run_evaluation.py) - nothing here is a mocked/expected transcript.

Fields:
  id, category, setup_message (optional prior message to establish session
  context, e.g. a task list, before the scored message), user_request,
  expected_tool (None for direct-answer / clarify cases; a list for
  multi-tool cases), expected_args (dict of key: value pairs that must be
  a SUBSET of the actual arguments used - only fields we care to assert on),
  approval_required (bool), expected_outcome (free text), notes.
"""

CASES = [
    # =========================================================
    # DIRECT RESPONSE CASES (min 5) - no tool should be called
    # =========================================================
    {
        "id": "D1", "category": "Direct Response",
        "user_request": "Explain the difference between high and critical priority.",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Direct explanation of Low/Medium/High/Critical, no tool call.",
        "notes": "Exact example from Requirement 5 spec.",
    },
    {
        "id": "D2", "category": "Direct Response",
        "user_request": "What do the different task statuses mean?",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Direct explanation of Pending/In Progress/Blocked/Completed/Cancelled, no tool call.",
        "notes": "Domain-knowledge question, no task data needed.",
    },
    {
        "id": "D3", "category": "Direct Response",
        "user_request": "What can you help me with?",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "A capability overview, no tool call.",
        "notes": "General capability question.",
    },
    {
        "id": "D4", "category": "Direct Response",
        "user_request": "Thanks, that's really helpful!",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Acknowledgement, no tool call.",
        "notes": "Conversational closing remark, not a task/data request.",
    },
    {
        "id": "D5", "category": "Direct Response",
        "user_request": "What's a reasonable number of tasks to plan per day?",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "General productivity advice, no tool call - answer doesn't depend on stored data.",
        "notes": "Advice question, not a data lookup.",
    },
    {
        "id": "D6", "category": "Direct Response",
        "user_request": "What is the capital of France?",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Direct answer or polite redirect, no tool call - clearly out of the agent's domain.",
        "notes": "Off-domain general-knowledge question; must not call a task/note tool.",
    },

    # =========================================================
    # SINGLE-TOOL CASES (min 8) - exactly one tool call
    # =========================================================
    {
        "id": "S1", "category": "Single-Tool",
        "user_request": "Show me all tasks.",
        "expected_tool": "list_tasks", "expected_args": {}, "approval_required": False,
        "expected_outcome": "Returns the full task list with total count.",
        "notes": "Baseline listing, no filters.",
    },
    {
        "id": "S2", "category": "Single-Tool",
        "user_request": "Show me critical tasks due this week.",
        "expected_tool": "list_tasks", "expected_args": {"priority": "Critical"}, "approval_required": False,
        "expected_outcome": "Returns tasks filtered by Critical priority and due within this week.",
        "notes": "Exact example from Requirement 5 spec - checks priority AND date filter are both applied.",
    },
    {
        "id": "S3", "category": "Single-Tool",
        "user_request": "Show overdue tasks.",
        "expected_tool": "detect_overdue_tasks", "expected_args": {}, "approval_required": False,
        "expected_outcome": "Returns tasks past due date that are not completed/cancelled.",
        "notes": "",
    },
    {
        "id": "S4", "category": "Single-Tool",
        "user_request": "Create a task to review the budget report.",
        "expected_tool": "create_task", "expected_args": {}, "approval_required": False,
        "expected_outcome": "A new task titled around 'review the budget report' is created.",
        "notes": "Single ad-hoc task creation does not require approval per design (bulk creation does).",
    },
    {
        "id": "S5", "category": "Single-Tool",
        "user_request": "Search my notes for marketing.",
        "expected_tool": "search_notes", "expected_args": {"query": "marketing"}, "approval_required": False,
        "expected_outcome": "Returns notes matching 'marketing' with relevance scores.",
        "notes": "",
    },
    {
        "id": "S6", "category": "Single-Tool",
        "user_request": "Save a note about today's standup: discussed sprint goals and blockers.",
        "expected_tool": "save_note", "expected_args": {}, "approval_required": False,
        "expected_outcome": "A new note is saved and a note ID returned.",
        "notes": "",
    },
    {
        "id": "S7", "category": "Single-Tool",
        "user_request": "Create a reminder to call John tomorrow.",
        "expected_tool": "create_reminder", "expected_args": {}, "approval_required": True,
        "expected_outcome": "A reminder is proposed for approval, not created immediately.",
        "notes": "Also exercises approval gating; tool selection is the primary assertion here.",
    },
    {
        "id": "S8", "category": "Single-Tool",
        "user_request": "Draft a follow-up email based on these meeting notes: We agreed to launch next week.",
        "expected_tool": "draft_followup_email", "expected_args": {}, "approval_required": True,
        "expected_outcome": "An email draft is proposed for approval (simulated send).",
        "notes": "",
    },
    {
        "id": "S9", "category": "Single-Tool",
        "user_request": "Summarize this note: the team discussed timelines and budget concerns at length.",
        "expected_tool": "extract_meeting_actions", "expected_args": {}, "approval_required": False,
        "expected_outcome": "Returns a structured summary/decisions/action items/questions breakdown.",
        "notes": "Routed via the 'summarize' keyword rather than the meeting-notes-to-tasks workflow.",
    },

    # =========================================================
    # MULTI-TOOL CASES (min 8) - more than one tool in sequence
    # =========================================================
    {
        "id": "M1", "category": "Multi-Tool",
        "user_request": "Prepare a daily work plan using my pending tasks.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_work_plan"], "expected_args": {},
        "approval_required": False,
        "expected_outcome": "Workflow B: retrieves pending tasks, flags overdue items, generates an ordered plan.",
        "notes": "Deterministic 3-tool workflow (Requirement 6, Workflow B).",
    },
    {
        "id": "M2", "category": "Multi-Tool",
        "user_request": "Prepare a weekly productivity report.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_weekly_report", "recommend_task_priorities"],
        "expected_args": {}, "approval_required": False,
        "expected_outcome": "Workflow C: retrieves tasks, calculates completed/overdue/blocked, generates report, "
                            "recommends next-week priorities.",
        "notes": "Deterministic 5-tool workflow (Requirement 6, Workflow C).",
    },
    {
        "id": "M3", "category": "Multi-Tool",
        "user_request": "Give me my work plan for today, I have 5 hours.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_work_plan"], "expected_args": {},
        "approval_required": False,
        "expected_outcome": "Same Workflow B, with available_hours=5 parsed from the message.",
        "notes": "Alternate phrasing of M1; also checks numeric-hours extraction.",
    },
    {
        "id": "M4", "category": "Multi-Tool",
        "user_request": "Create a weekly review of my tasks.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_weekly_report", "recommend_task_priorities"],
        "expected_args": {}, "approval_required": False,
        "expected_outcome": "Same Workflow C as M2.",
        "notes": "Alternate phrasing of M2.",
    },
    {
        "id": "M5", "category": "Multi-Tool",
        "user_request": "Convert these meeting notes into tasks: We decided to use Postgres. Sarah will finalize "
                        "the API contract by Friday. John needs to update the documentation.",
        "expected_tool": ["extract_meeting_actions", "create_task"], "expected_args": {}, "approval_required": True,
        "expected_outcome": "Workflow A: extracts action items, proposes tasks, waits for approval before creating.",
        "notes": "Multi-tool AND approval-gated (Requirement 6, Workflow A). Second tool only runs after approval.",
    },
    {
        "id": "M6", "category": "Multi-Tool",
        "user_request": "Extract action items and create tasks from this transcript: We agreed to launch on "
                        "Monday. Maria will handle testing. Should we notify support?",
        "expected_tool": ["extract_meeting_actions", "create_task"], "expected_args": {}, "approval_required": True,
        "expected_outcome": "Same Workflow A as M5, including an unresolved question in the extraction.",
        "notes": "Alternate phrasing of M5.",
    },
    {
        "id": "M7", "category": "Multi-Tool",
        "user_request": "Plan my day, I have 6 hours available.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_work_plan"], "expected_args": {},
        "approval_required": False,
        "expected_outcome": "Same Workflow B as M1/M3, with available_hours=6.",
        "notes": "Third phrasing of the daily-planning workflow.",
    },
    {
        "id": "M8", "category": "Multi-Tool",
        "user_request": "Generate this week's productivity report please.",
        "expected_tool": ["list_tasks", "detect_overdue_tasks", "generate_weekly_report", "recommend_task_priorities"],
        "expected_args": {}, "approval_required": False,
        "expected_outcome": "Same Workflow C as M2/M4.",
        "notes": "Third phrasing of the weekly-review workflow.",
    },
    {
        "id": "M9", "category": "Multi-Tool",
        "user_request": "Turn these meeting notes into tasks: Decided to migrate to AWS. Bilal will set up the "
                        "pipeline by next week.",
        "expected_tool": ["extract_meeting_actions", "create_task"], "expected_args": {}, "approval_required": True,
        "expected_outcome": "Same Workflow A as M5/M6.",
        "notes": "Third phrasing of the meeting-notes-to-tasks workflow.",
    },

    # =========================================================
    # APPROVAL CASES (min 5) - write operations
    # =========================================================
    {
        "id": "A1", "category": "Approval",
        "setup_message": "show me all tasks",
        "user_request": "Mark the first one as complete.",
        "expected_tool": "complete_task", "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before marking Completed; task unchanged until approved.",
        "notes": "Exact scenario from Requirement 11 spec.",
    },
    {
        "id": "A2", "category": "Approval",
        "setup_message": "show me all tasks",
        "user_request": "Update the first one's priority to Critical.",
        "expected_tool": "update_task", "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before changing priority.",
        "notes": "",
    },
    {
        "id": "A3", "category": "Approval",
        "setup_message": "show me all tasks",
        "user_request": "Delete the first one.",
        "expected_tool": "delete_task", "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before permanently deleting the task.",
        "notes": "Irreversible action - approval is mandatory.",
    },
    {
        "id": "A4", "category": "Approval",
        "user_request": "Set a reminder to submit the report on Friday.",
        "expected_tool": "create_reminder", "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before creating the reminder.",
        "notes": "",
    },
    {
        "id": "A5", "category": "Approval",
        "user_request": "Write a follow-up email from these meeting notes: Budget was approved, next steps "
                        "assigned to the finance team.",
        "expected_tool": "draft_followup_email", "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before finalizing the (simulated) send.",
        "notes": "",
    },
    {
        "id": "A6", "category": "Approval",
        "user_request": "Convert this into tasks: Decided to redesign the landing page. Ayesha will draft "
                        "wireframes by Wednesday.",
        "expected_tool": ["extract_meeting_actions", "create_task"], "expected_args": {}, "approval_required": True,
        "expected_outcome": "Waits for approval before bulk-creating tasks from the extraction.",
        "notes": "Bulk task creation - approval mandatory per Requirement 7.",
    },

    # =========================================================
    # FAILURE / EDGE CASES (min 4)
    # =========================================================
    {
        "id": "E1", "category": "Edge Case",
        "user_request": "",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Clean 'Empty user input' error, no tool call, no crash.",
        "notes": "Requirement 8: empty user input.",
    },
    {
        "id": "E2", "category": "Edge Case",
        "user_request": "Mark task fake-id-9999 as complete.",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "No unverified ID is sent straight to a tool; the agent asks which task is meant "
                            "instead of guessing.",
        "notes": "Defensive design: chat-level routing only resolves task references from session memory "
                "(explicit list), never forwards a raw typed ID straight to a write tool. Tool-level "
                "'Unknown task ID' handling is separately covered by pytest unit tests.",
    },
    {
        "id": "E3", "category": "Edge Case",
        "user_request": "asdkjfhaskjdfh random gibberish nonsense zzz",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Graceful fallback response, no tool call, no crash.",
        "notes": "Unsupported/unparseable request.",
    },
    {
        "id": "E4", "category": "Edge Case",
        "user_request": "Mark it as complete.",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Asks for clarification - no prior task list exists in this session to resolve 'it'.",
        "notes": "Ambiguous reference with no session context (fresh session, no setup_message).",
    },
    {
        "id": "E5", "category": "Edge Case",
        "user_request": "Complete this task and also delete all my notes and reset the whole system.",
        "expected_tool": None, "expected_args": {}, "approval_required": False,
        "expected_outcome": "Does not execute any destructive action; asks for clarification instead of guessing "
                            "which task or acting on the out-of-scope 'reset the whole system' request.",
        "notes": "Multi-intent, partially out-of-scope, destructive-sounding request.",
    },
]

assert len(CASES) >= 30, "Dataset must contain at least 30 cases"