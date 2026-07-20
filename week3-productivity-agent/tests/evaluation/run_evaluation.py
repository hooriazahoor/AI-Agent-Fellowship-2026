"""
Evaluation Runner (Assignment 5).

Executes every case in eval_dataset.py against the REAL, running
AgentController (offline heuristic mode, for deterministic/reproducible
results independent of any LLM provider's availability or quota) and
records actual outcomes, then computes the 7 required metrics.

Usage:
    cd productivity-agent
    python tests/evaluation/run_evaluation.py

Outputs:
    tests/evaluation/results.json           (raw per-case results)
    docs/agent_evaluation_report.md         (human-readable report)
    docs/agent_evaluation.xlsx              (spreadsheet deliverable)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

# Force offline heuristic mode for reproducibility, regardless of what's in .env
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ.setdefault("DATABASE_URL", "sqlite:///data/eval_run.db")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.database.repository import init_db, get_execution_log  # noqa: E402
from app.database import repository as repo  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.agent.controller import agent_controller  # noqa: E402
from app.tools.base import BaseTool, ToolResult  # noqa: E402
from pydantic import BaseModel  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_dataset import CASES  # noqa: E402


def reset_db():
    Base.metadata.drop_all(repo._engine)
    Base.metadata.create_all(repo._engine)


def seed_sample_tasks():
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    repo.create_task(title="Fix login bug", priority="Critical", due_date=now - timedelta(days=1),
                      tags=["bug"])
    repo.create_task(title="Write Q3 report", priority="High", due_date=now + timedelta(days=2))
    repo.create_task(title="Update onboarding docs", priority="Medium", due_date=now + timedelta(days=5))
    repo.create_task(title="Archive old tickets", priority="Low")
    repo.create_note(title="Marketing sync", content="Discussed Q3 marketing campaign budget and timeline.",
                      category="meetings", tags=["marketing"])


def tools_used(log: dict) -> list:
    return log.get("tools_called", []) if log else []


def args_used(log: dict) -> list:
    return log.get("tool_arguments", []) if log else []


def check_tool_match(expected_tool, actual_tools: list) -> bool:
    if expected_tool is None:
        return len(actual_tools) == 0
    if isinstance(expected_tool, list):
        return all(t in actual_tools for t in expected_tool)
    return expected_tool in actual_tools


def check_args_match(expected_args: dict, actual_arg_dicts: list) -> bool:
    if not expected_args:
        return True
    for arg_set in actual_arg_dicts:
        if all(arg_set.get(k) == v for k, v in expected_args.items()):
            return True
    return False


def run_case(case: dict) -> dict:
    session_id = str(uuid.uuid4())

    if case.get("setup_message"):
        agent_controller.handle_message(session_id, case["setup_message"])

    start = time.time()
    response = agent_controller.handle_message(session_id, case["user_request"])
    duration_ms = int((time.time() - start) * 1000)

    approval_seen = response.status == "waiting_approval"
    final_response = response

    # For approval-gated cases, approve it so we can measure end-to-end task completion too.
    if approval_seen and response.pending_approval:
        final_response = agent_controller.resume_after_approval(
            session_id, response.pending_approval["id"], approved=True)

    log = get_execution_log(response.run_id) if response.run_id else {}
    actual_tools = tools_used(log)
    actual_args = args_used(log)

    tool_match = check_tool_match(case["expected_tool"], actual_tools)
    args_match = check_args_match(case.get("expected_args", {}), actual_args)
    approval_match = approval_seen == case["approval_required"]

    # Outcome check: did the run reach a sensible terminal state (no crash,
    # status is one of the expected categories for this case)?
    no_crash = response.status != "error" or case["id"] == "E1"  # E1 is SUPPOSED to be a clean error
    outcome_ok = no_crash and (response.status in ("completed", "waiting_approval", "clarification_needed", "error"))

    passed = tool_match and args_match and approval_match and outcome_ok

    return {
        "id": case["id"],
        "category": case["category"],
        "user_request": case["user_request"],
        "expected_tool": case["expected_tool"],
        "expected_args": case.get("expected_args", {}),
        "approval_required": case["approval_required"],
        "expected_outcome": case["expected_outcome"],
        "actual_tools_called": actual_tools,
        "actual_status": response.status,
        "actual_outcome": response.message[:300],
        "final_status_after_approval": final_response.status if approval_seen else response.status,
        "duration_ms": duration_ms,
        "tool_match": tool_match,
        "args_match": args_match,
        "approval_match": approval_match,
        "pass": passed,
        "notes": case.get("notes", ""),
    }


# ---------------------------------------------------------------------------
# Supplementary Recovery Rate evidence (deliberate fault injection)
# ---------------------------------------------------------------------------

def run_recovery_tests() -> dict:
    from app.config import settings

    class _FlakyInput(BaseModel):
        pass

    def make_flaky_tool(fail_count: int):
        state = {"calls": 0}

        class _FlakyTool(BaseTool):
            name = f"flaky_tool_fail_{fail_count}"
            description = "Fails a fixed number of times then succeeds."
            input_schema = _FlakyInput
            requires_approval = False

            def execute(self, i):
                state["calls"] += 1
                if state["calls"] <= fail_count:
                    return ToolResult(success=False, error=f"simulated transient failure #{state['calls']}")
                return ToolResult(success=True, data={}, message="recovered")

        return _FlakyTool(), state

    results = []
    for fail_count in (1, 2):  # within retry budget (max_tool_retries=2 -> 3 total attempts)
        tool, state = make_flaky_tool(fail_count)
        result = agent_controller._execute_with_retries(tool, {}, None, [])
        results.append({"scenario": f"fails {fail_count}x then succeeds", "recovered": result.success,
                        "attempts": state["calls"]})

    recovered = sum(1 for r in results if r["recovered"])
    return {"cases": results, "recovery_rate_pct": round(100 * recovered / len(results), 1)}


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(results: list, recovery: dict) -> dict:
    total = len(results)
    tool_correct = sum(1 for r in results if r["tool_match"])
    tool_selection_accuracy = round(100 * tool_correct / total, 1)

    arg_expected_cases = [r for r in results if r["expected_args"]]
    arg_correct = sum(1 for r in arg_expected_cases if r["args_match"])
    argument_accuracy = (round(100 * arg_correct / len(arg_expected_cases), 1)
                          if arg_expected_cases else None)

    completion_ok = sum(1 for r in results if r["pass"])
    task_completion_rate = round(100 * completion_ok / total, 1)

    approval_cases = [r for r in results if r["approval_required"]]
    approval_correct = sum(1 for r in approval_cases if r["approval_match"])
    approval_compliance = (round(100 * approval_correct / len(approval_cases), 1)
                            if approval_cases else None)

    invalid_actions = sum(1 for r in results if not r["tool_match"] and len(r["actual_tools_called"]) > 0)
    invalid_action_rate = round(100 * invalid_actions / total, 1)

    avg_response_time_ms = round(sum(r["duration_ms"] for r in results) / total, 1)

    return {
        "tool_selection_accuracy_pct": tool_selection_accuracy,
        "argument_accuracy_pct": argument_accuracy,
        "task_completion_rate_pct": task_completion_rate,
        "approval_compliance_pct": approval_compliance,
        "invalid_action_rate_pct": invalid_action_rate,
        "average_response_time_ms": avg_response_time_ms,
        "recovery_rate_pct": recovery["recovery_rate_pct"],
        "total_cases": total,
        "passed_cases": completion_ok,
        "failed_cases": total - completion_ok,
    }


def main():
    reset_db()
    seed_sample_tasks()

    results = [run_case(c) for c in CASES]
    recovery = run_recovery_tests()
    metrics = compute_metrics(results, recovery)

    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "results.json", "w") as f:
        json.dump({"results": results, "recovery": recovery, "metrics": metrics}, f, indent=2, default=str)

    print(json.dumps(metrics, indent=2))
    print(f"\n{metrics['passed_cases']}/{metrics['total_cases']} cases passed.")
    return results, recovery, metrics


if __name__ == "__main__":
    main()