"""
Experiment 1: Tool Description Quality (Assignment 6)

Compares tool-selection accuracy when tools are given SHORT (one-line)
descriptions versus the app's current DETAILED descriptions, using the
same battery of requests for both.

REQUIRES a working LLM API key (GEMINI_API_KEY or OPENAI_API_KEY) with
available quota - this makes real API calls and cannot be run in a
sandboxed/offline environment. Run this on your own machine:

    python tests/experiments/experiment_1_tool_description_quality.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///data/experiment_run.db")

from app.services.llm_service import llm_service, LLMServiceError  # noqa: E402
from app.tools import registry  # noqa: E402
from app.agent.prompts import SYSTEM_PROMPT  # noqa: E402

# Short, one-line descriptions (deliberately terse, no field-level guidance)
SHORT_DESCRIPTIONS = {
    "create_task": "Create a task.",
    "list_tasks": "List tasks.",
    "update_task": "Update a task.",
    "complete_task": "Complete a task.",
    "delete_task": "Delete a task.",
    "search_notes": "Search notes.",
    "save_note": "Save a note.",
    "extract_meeting_actions": "Extract meeting info.",
    "generate_work_plan": "Make a work plan.",
    "detect_overdue_tasks": "Find overdue tasks.",
    "estimate_task_effort": "Estimate effort.",
    "identify_conflicting_deadlines": "Find conflicts.",
    "recommend_task_priorities": "Recommend priorities.",
    "summarize_notes": "Summarize notes.",
    "create_reminder": "Create a reminder.",
    "draft_followup_email": "Draft an email.",
    "generate_weekly_report": "Weekly report.",
    "convert_meeting_notes_to_tasks": "Convert notes to tasks.",
    "export_report": "Export a report.",
}

# (request, expected_tool) - unambiguous single-tool cases only, since this
# experiment isolates description quality, not multi-step reasoning.
TEST_CASES = [
    ("Show me all tasks.", "list_tasks"),
    ("Show me critical tasks.", "list_tasks"),
    ("Create a task to review the budget.", "create_task"),
    ("Search my notes for marketing.", "search_notes"),
    ("Save a note about today's standup.", "save_note"),
    ("Show overdue tasks.", "detect_overdue_tasks"),
    ("How long will 'write report' take?", "estimate_task_effort"),
    ("Are any of my deadlines conflicting?", "identify_conflicting_deadlines"),
    ("What priorities should I adjust?", "recommend_task_priorities"),
    ("Summarize my notes about the campaign.", "summarize_notes"),
    ("Remind me to call John tomorrow.", "create_reminder"),
    ("Draft a follow-up email from these notes: budget approved.", "draft_followup_email"),
    ("Give me this week's productivity report.", "generate_weekly_report"),
    ("Delete the task about archiving tickets.", "delete_task"),
    ("Extract action items from: Sarah will finalize the contract by Friday.", "extract_meeting_actions"),
]


def run_batch(description_map: dict | None, label: str) -> dict:
    originals = {}
    if description_map:
        for tool in registry.all():
            if tool.name in description_map:
                originals[tool.name] = tool.description
                tool.description = description_map[tool.name]

    results = []
    try:
        for request, expected_tool in TEST_CASES:
            try:
                decision = llm_service.decide(SYSTEM_PROMPT, [{"role": "user", "content": request}],
                                               registry.openai_schemas())
                actual_tool = decision.get("tool_name")
                correct = actual_tool == expected_tool
            except LLMServiceError as e:
                actual_tool, correct = f"ERROR: {e}", False
            results.append({"request": request, "expected": expected_tool, "actual": actual_tool,
                            "correct": correct})
            time.sleep(1)  # be gentle on free-tier rate limits
    finally:
        for name, desc in originals.items():
            registry.get(name).description = desc

    accuracy = round(100 * sum(1 for r in results if r["correct"]) / len(results), 1)
    return {"label": label, "accuracy_pct": accuracy, "results": results}


def main():
    if not llm_service.is_configured:
        print("ERROR: No LLM API key configured (GEMINI_API_KEY / OPENAI_API_KEY).")
        print("This experiment requires real API calls and cannot run offline.")
        print("Set your key in .env and re-run.")
        sys.exit(1)

    print("Running with SHORT descriptions...")
    short_run = run_batch(SHORT_DESCRIPTIONS, "short_descriptions")
    print(f"  -> {short_run['accuracy_pct']}% accuracy")

    print("Running with DETAILED (current) descriptions...")
    detailed_run = run_batch(None, "detailed_descriptions")
    print(f"  -> {detailed_run['accuracy_pct']}% accuracy")

    summary = {
        "short_descriptions_accuracy_pct": short_run["accuracy_pct"],
        "detailed_descriptions_accuracy_pct": detailed_run["accuracy_pct"],
        "delta_pct_points": round(detailed_run["accuracy_pct"] - short_run["accuracy_pct"], 1),
    }
    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "experiment_1_results.json", "w") as f:
        json.dump({"summary": summary, "short_run": short_run, "detailed_run": detailed_run}, f, indent=2)

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nSaved detailed results to {out_dir / 'experiment_1_results.json'}")


if __name__ == "__main__":
    main()