# Personal Productivity and Task Execution Agent

A tool-using AI agent — not a general-purpose chatbot — that organizes tasks, analyzes
meeting notes, and prepares daily and weekly plans. Every request is interpreted, routed
to the right tool (or answered directly), validated, executed when appropriate, reviewed,
and logged. Built with Flask, SQLite, and Google Gemini (OpenAI-compatible endpoint).

---

## 1. Project Title

**Personal Productivity and Task Execution Agent**

## 2. Problem Statement

Knowledge workers and students routinely juggle tasks scattered across meeting notes,
chat threads, and memory. Action items from meetings get lost, priorities aren't
reassessed as deadlines approach, and planning a day or week is manual, repetitive work.
General-purpose chatbots can discuss these problems but can't reliably act on structured
data (create the task, track its status, remember it next session) without either
hallucinating results or requiring the user to double-check everything by hand.

This agent solves that gap: it turns meeting notes into tracked tasks, keeps a
persistent task/note store, generates prioritized daily and weekly plans grounded in
real stored data, and does all of this while never taking a consequential action
(create, update, complete, delete, send) without the user's explicit, reviewable
approval.

## 3. Key Features

- **Tool-using agent**, not a chatbot — decides whether a tool is needed, which tool(s),
  and whether approval is required, before answering.
- **20 tools** across task management, notes, and planning (full catalogue in Section 5).
- **Human-in-the-loop approval** for every write/irreversible action, with an editable
  approval card (Approve / Reject / edit arguments before approving).
- **Three deterministic multi-tool workflows**: Meeting Notes → Tasks, Daily Planning,
  Weekly Review — each chains several real tool calls in a fixed, auditable sequence.
- **Offline heuristic fallback** — the app keeps working (task CRUD, notes, plans,
  reports) even with no LLM API key configured or if the LLM call fails mid-conversation.
- **Session memory** — resolves references like "the second one" against what was
  actually shown earlier in the conversation, and remembers stated preferences
  (e.g. "I usually have 4 hours a day").
- **Full execution logging** — every run records the request, model, tools called,
  arguments, results, approval status, errors, timing, and outcome.
- **Execution limits & loop prevention** — max agent steps, per-tool retry limit, an
  enforced tool-execution timeout, and duplicate-call detection.
- **Export**: reports/plans can be downloaded as Markdown or PDF.
- Clean Flask + vanilla JS UI: Chat (with a live Agent Activity panel), Tasks, Notes,
  Tools (all bonus tools as standalone forms), and Execution Log tabs.

## 4. Architecture Overview

```
User Interface (Flask + HTML/JS)
   |
   v
Agent Controller (app/agent/controller.py)
   |
   v
Intent and Task Analysis (app/agent/nodes.py)
   |
   v
Tool Selection (LLM function-calling, or offline heuristic router)
   |
   v
Human Approval, if required (app/database + UI approval card)
   |
   v
Tool Execution (app/tools/*, with retries + enforced timeout)
   |
   v
Result Validation (app/agent/nodes.py)
   |
   v
Response Generation
   |
   v
Execution Log (app/logging/run_logger.py -> ExecutionLog table)
```

**Project layout:**

```
productivity-agent/
├── app/
│   ├── main.py                 # Flask app + routes (UI layer only)
│   ├── config.py                # env-based settings, no hard-coded secrets
│   ├── seed_data.py              # sample data for demo/evaluation
│   ├── agent/
│   │   ├── controller.py        # orchestration loop, limits, approval flow
│   │   ├── workflows.py         # 3 deterministic multi-tool workflows
│   │   ├── nodes.py             # individual pipeline-stage functions
│   │   ├── prompts.py           # versioned system/tool/approval prompts
│   │   └── state.py             # session memory
│   ├── tools/                   # 20 tools (base.py, task_tools.py, note_tools.py, planning_tools.py)
│   ├── database/                # SQLAlchemy models.py + repository.py
│   ├── services/
│   │   └── llm_service.py       # Gemini/OpenAI-compatible wrapper + offline fallback
│   └── logging/
│       └── run_logger.py        # structured execution logging
├── templates/index.html
├── static/{css,js}
├── tests/                       # automated tests (pytest) + evaluation + experiments
├── docs/                        # prompts, deployment, evaluation & security docs
├── Dockerfile
├── requirements.txt
└── .env.example
```

## 5. Tool Catalogue

| Tool | Description | Approval Required |
|---|---|---|
| `create_task` | Create a new task with title, description, priority, due date and tags. | No |
| `list_tasks` | List tasks, optionally filtered by status, priority, due date range, or tag. | No |
| `update_task` | Update fields on an existing task (title, description, priority, due date, status, tags). | Yes |
| `complete_task` | Mark a task as Completed. Irreversible. | Yes |
| `delete_task` | Permanently delete a task record. Irreversible. | Yes |
| `search_notes` | Search saved notes by keyword, optionally filtered by category or date range. | No |
| `save_note` | Save a new note with title, content, category and tags. | No |
| `delete_note` | Permanently delete a note record. Irreversible. | Yes |
| `extract_meeting_actions` | Extract a structured summary, decisions, action items (owners/deadlines), and unresolved questions from meeting notes/transcript. | No |
| `generate_work_plan` | Generate an ordered daily/weekly work plan considering priority, deadline, status, and estimated effort. | No |
| `detect_overdue_tasks` | Find all tasks that are overdue and not completed/cancelled. | No |
| `estimate_task_effort` | Heuristically estimate how many minutes a task will take. | No |
| `identify_conflicting_deadlines` | Find tasks whose due dates cluster too closely together. | No |
| `recommend_task_priorities` | Recommend priority adjustments based on due dates and status. | No |
| `summarize_notes` | Summarize a set of notes (by query or explicit IDs) into key points. | No |
| `create_reminder` | Create a reminder (stored as a lightweight tagged task). | Yes |
| `draft_followup_email` | Draft a follow-up email from meeting notes (simulated send). | Yes |
| `generate_weekly_report` | Weekly productivity report: completed, overdue, blocked tasks + next-week priorities. | No |
| `convert_meeting_notes_to_tasks` | Extract action items and bulk-create tasks from them. | Yes |
| `export_report` | Export a weekly report or work plan as Markdown/PDF. | No |

## 6. Technology Stack

**Required (per project spec):**
- Python 3.11+
- Google Gemini API (OpenAI-compatible endpoint) — swappable for OpenAI via `.env`
- Pydantic — schema validation for every tool input
- Flask — frontend (chat, tasks, notes, tools, execution log)
- SQLite (via SQLAlchemy) — persistent storage
- Git and GitHub
- Environment variables for all secrets (no hard-coded keys)

**Also used:**
- SQLAlchemy ORM (parameterized queries only, no raw SQL)
- Python `logging` — structured server-side logs
- Pytest — automated test suite
- Docker — containerized deployment
- ReportLab — PDF export/report generation
- Vanilla HTML/CSS/JS frontend (no framework build step)

## 7. Installation Steps

```bash
git clone <your-repo-url>
cd productivity-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in GEMINI_API_KEY (see Section 8)
```

## 8. Environment Variables

Set these in `.env` (see `.env.example` for the full template):

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key (OpenAI-compatible endpoint) | *(required for LLM mode)* |
| `GEMINI_BASE_URL` | Gemini's OpenAI-compatible base URL | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `OPENAI_API_KEY` | Optional — use OpenAI instead of Gemini | *(blank)* |
| `OPENAI_BASE_URL` | Optional — custom OpenAI-compatible endpoint | *(blank)* |
| `OPENAI_MODEL` | OpenAI model name (if using OpenAI) | `gpt-4o-mini` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///data/productivity_agent.db` |
| `FLASK_SECRET_KEY` | Flask session secret | *(change in production)* |
| `FLASK_DEBUG` | Flask debug mode | `True` (set `False` in production) |
| `PORT` | Server port | `5000` |
| `MAX_AGENT_STEPS` | Max tool-selection iterations per turn | `8` |
| `MAX_TOOL_RETRIES` | Max retries per failed tool call | `2` |
| `TOOL_TIMEOUT_SECONDS` | Enforced timeout per tool execution | `30` |

**No LLM key configured?** The app still runs — it falls back to a deterministic
keyword-based router so task/note/plan commands keep working; only free-form
conversational questions are limited.

## 9. How to Run Locally

```bash
python -m app.main
```

Visit `http://localhost:5000`. Click **"Load sample data"** in the sidebar to seed demo
tasks/notes.

## 10. How to Run Tests

```bash
pytest tests/ -v
```

Runs the full automated test suite (task CRUD, invalid IDs, note search, structured
meeting extraction, approval enforcement, tool validation, execution limits, database
persistence, and the three multi-tool workflows).

Additional evaluation/experiment suites:

```bash
python tests/evaluation/run_evaluation.py       # 35-case agent evaluation dataset
python tests/evaluation/generate_report.py      # -> docs/agent_evaluation.xlsx
python tests/experiments/experiment_4_approval_consistency.py
python tests/experiments/experiment_5_max_steps.py
# Experiments 1, 2, 3, 6 require a live LLM API key with quota - see docs/agent_experiments_report.md
```

## 11. Example User Requests

```
"Create three tasks from these meeting notes."
"Show me all high-priority tasks due this week."
"Prepare a daily work plan using my pending tasks."
"Summarize these notes and identify decisions and action items."
"Create a reminder for the project review."
"Search my saved notes for information about the marketing campaign."
"Draft a follow-up email based on these meeting notes."
"Mark the website task as complete."
"Prepare a weekly productivity report."
"Find tasks that are overdue and recommend what I should work on first."
"Explain the difference between High and Critical priority."
```

## 12. Evaluation Results

Full dataset and methodology: `docs/agent_evaluation_report.md` /
`docs/agent_evaluation.xlsx` (35 test cases: Direct Response, Single-Tool, Multi-Tool,
Approval, and Edge Cases).

| Metric | Target | Actual |
|---|---|---|
| Tool Selection Accuracy | ≥ 85% | **100.0%** |
| Argument Accuracy | ≥ 80% | **100.0%** |
| Task Completion Rate | ≥ 80% | **100.0%** |
| Approval Compliance | = 100% | **100.0%** |
| Invalid Action Rate | < 10% | **0.0%** |
| Average Response Time | — | 10.1 ms |
| Recovery Rate | — | 100.0% |

**35 / 35 test cases passed.** See also `docs/agent_experiments_report.md` for
approval-consistency (adversarial prompt testing) and max-agent-steps experiments.

## 13. Screenshots

_(Add screenshots here — e.g. Chat tab with Agent Activity panel, Tasks tab, approval
card, Execution Log tab.)_

<!-- ![Chat view](docs/screenshots/chat.png) -->
<!-- ![Tasks view](docs/screenshots/tasks.png) -->
<!-- ![Approval card](docs/screenshots/approval.png) -->
<!-- ![Execution log](docs/screenshots/execution_log.png) -->

## 14. Demo Link

_(Add a link to a demo video/walkthrough here.)_

## 15. Deployment Link

_(Add the live deployed URL here once deployed — see `docs/deployment.md` for the
Render/Railway/Hugging Face Spaces deployment guide.)_

## 16. Known Limitations

- **No authentication** — the app currently has no login/account system; all tasks,
  notes, and execution logs are readable by anyone who can reach the server. Documented
  as the top open risk before any non-local deployment (see the project's security
  review document).
- **No rate limiting** on any endpoint yet.
- Approval resolution does not yet verify that the resolving session owns the pending
  approval (an IDOR-style gap identified during security review, not yet fixed).
- Deletions are permanent (hard delete) — no undo/soft-delete yet.
- Free-text fields (title, content, transcript) have no `max_length` limit yet.
- Semantic (embedding-based) note search is not implemented; keyword/overlap scoring is
  used instead.
- `draft_followup_email` only simulates sending — no real email is ever sent.
- SQLite persistence resets on redeploy on platforms without a persistent disk (see
  `docs/deployment.md`); use a managed Postgres instance for real persistence.
- Session memory is in-process (a Python dict) — a multi-worker production deployment
  should move it to Redis or the database.

## 17. Future Roadmap

- Add authentication (session-based login or API token) and per-user data ownership.
- Fix the approval-resolution ownership check (IDOR) and add rate limiting
  (Flask-Limiter) per the security review.
- Add `max_length` constraints to all free-text tool inputs.
- Convert `delete_task`/`delete_note` to soft-delete with a "Recently Deleted" view.
- Add a log-retention/purge policy for `ExecutionLog`.
- Run Experiments 1, 2, 3, and 6 (tool description quality, structured vs. unstructured
  output, temperature, model comparison) against a live LLM and fold results back into
  `docs/agent_experiments_report.md`.
- Deploy to Render (or similar) with a persistent Postgres database.
- Real semantic search over notes (embeddings) as an upgrade from keyword search.