# Prompt Design (Requirement 12)

Source of truth: `app/agent/prompts.py` (kept under version control; this file
mirrors it for reviewers).

## System Prompt
Tells the agent it is a task-execution agent, not a chatbot; defines when to
call tools vs. answer directly; requires minimal necessary tool calls.

## Tool-Use Instructions
- Validate arguments against each tool's Pydantic schema before calling.
- Prefer specific filters over broad listings when the user implies one.
- `generate_work_plan` uses stored `estimated_effort_minutes` when present,
  otherwise a 45-minute default (enforced inside the tool, not the prompt).

## Approval Rules
Tools requiring approval: `update_task`, `complete_task`, `create_reminder`,
`draft_followup_email`, `convert_meeting_notes_to_tasks`, and any
delete/irreversible action. The UI must show proposed action, tool name,
arguments, expected effect, and Approve/Reject controls before execution.

## Response Format
Concise, plain language. No exposed chain-of-thought - only short
operational status labels (Thinking, Selecting tool, Executing tool,
Waiting for approval, Validating result, Responding, Error).

## Error Behavior
- Validation errors -> explain what was invalid, ask for a correction.
- Unknown task ID -> say clearly it wasn't found; never invent a task.
- Repeated tool failure beyond `MAX_TOOL_RETRIES` -> stop retrying, report it.
- Missing API key -> fall back to the deterministic heuristic router / offline
  text generation, and say AI-generated text quality may be reduced.

## Stop Conditions
Stop when: the request is fully answered; `MAX_AGENT_STEPS` is reached; a
tool requiring approval is now awaiting a decision; or clarification is
needed from the user (e.g. an unresolved "the second one" reference).

## Why These Limits (Requirement 9)
| Limit | Value | Rationale |
|---|---|---|
| Max agent steps | 8 | Matches the spec's recommendation; enough for multi-tool workflows (e.g. extract -> approve -> create) without risking runaway loops. |
| Max tool retries | 2 | Transient errors (timeouts, flaky API) usually resolve within 1-2 retries; more than that likely indicates a real failure that should surface to the user. |
| Tool timeout | 30s | Generous enough for an LLM-backed tool call (e.g. meeting extraction) while still failing fast enough for a responsive UI. |
| Duplicate call detection | exact tool+args signature | Cheap to compute, catches the most common infinite-loop failure mode (the model repeating the same call). |
