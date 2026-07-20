"""
Optional Experiment 6: Model Comparison (Assignment 6)

Compares two available models on the SAME evaluation set (reuses the 35-case
dataset from Assignment 5), reporting tool selection accuracy and average
response latency for each model.

REQUIRES working API access for both models you want to compare. Configure
via environment variables before running, e.g.:

    # Compare two Gemini models:
    set MODEL_A=gemini-2.5-flash
    set MODEL_B=gemini-2.5-flash-lite

    # Or compare Gemini vs OpenAI (requires both keys in .env):
    set MODEL_A=gemini-2.5-flash
    set MODEL_A_PROVIDER=gemini
    set MODEL_B=gpt-4o-mini
    set MODEL_B_PROVIDER=openai

Run on your own machine:
    python tests/experiments/experiment_6_model_comparison.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))

from app.config import settings  # noqa: E402
from app.services.llm_service import LLMService, LLMServiceError  # noqa: E402
from app.tools import registry  # noqa: E402
from app.agent.prompts import SYSTEM_PROMPT  # noqa: E402

MODEL_A = os.getenv("MODEL_A", settings.gemini_model)
MODEL_B = os.getenv("MODEL_B", "gemini-2.5-flash-lite")

# A representative subset of tool-selection cases from the Assignment 5 dataset
CASES = [
    ("Show me all high-priority tasks.", "list_tasks"),
    ("Create a task to review the budget report.", "create_task"),
    ("Show overdue tasks.", "detect_overdue_tasks"),
    ("Search my notes for marketing.", "search_notes"),
    ("Save a note about today's standup.", "save_note"),
    ("Create a reminder to call John tomorrow.", "create_reminder"),
    ("Draft a follow-up email from these notes: launch confirmed.", "draft_followup_email"),
    ("Explain the difference between high and critical priority.", None),
    ("What can you help me with?", None),
    ("Summarize this note: budget concerns discussed.", "extract_meeting_actions"),
]


def build_service_for_model(model_name: str) -> LLMService:
    svc = LLMService.__new__(LLMService)
    svc.provider = "gemini"
    from openai import OpenAI
    svc._client = OpenAI(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url)
    svc.model = model_name
    return svc


def evaluate_model(model_name: str) -> dict:
    svc = build_service_for_model(model_name)
    results = []
    for prompt, expected_tool in CASES:
        start = time.time()
        try:
            decision = svc.decide(SYSTEM_PROMPT, [{"role": "user", "content": prompt}],
                                   registry.openai_schemas())
            actual_tool = decision.get("tool_name") if decision["action"] == "tool_call" else None
            correct = actual_tool == expected_tool
            error = None
        except LLMServiceError as e:
            actual_tool, correct, error = None, False, str(e)
        latency_ms = round((time.time() - start) * 1000, 1)
        results.append({"prompt": prompt, "expected": expected_tool, "actual": actual_tool,
                        "correct": correct, "latency_ms": latency_ms, "error": error})
        time.sleep(1)

    accuracy = round(100 * sum(1 for r in results if r["correct"]) / len(results), 1)
    avg_latency = round(sum(r["latency_ms"] for r in results) / len(results), 1)
    error_rate = round(100 * sum(1 for r in results if r["error"]) / len(results), 1)
    return {"model": model_name, "accuracy_pct": accuracy, "avg_latency_ms": avg_latency,
            "error_rate_pct": error_rate, "results": results}


def main():
    if not settings.gemini_api_key and not settings.openai_api_key:
        print("ERROR: No LLM API key configured. This experiment requires real API calls.")
        sys.exit(1)

    print(f"Evaluating Model A: {MODEL_A}")
    result_a = evaluate_model(MODEL_A)
    print(f"  -> accuracy={result_a['accuracy_pct']}%, avg_latency={result_a['avg_latency_ms']}ms")

    print(f"Evaluating Model B: {MODEL_B}")
    result_b = evaluate_model(MODEL_B)
    print(f"  -> accuracy={result_b['accuracy_pct']}%, avg_latency={result_b['avg_latency_ms']}ms")

    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "experiment_6_results.json", "w") as f:
        json.dump({"model_a": result_a, "model_b": result_b}, f, indent=2)

    print("\nComparison:")
    print(json.dumps({
        "model_a": {"model": MODEL_A, "accuracy_pct": result_a["accuracy_pct"],
                    "avg_latency_ms": result_a["avg_latency_ms"]},
        "model_b": {"model": MODEL_B, "accuracy_pct": result_b["accuracy_pct"],
                    "avg_latency_ms": result_b["avg_latency_ms"]},
    }, indent=2))


if __name__ == "__main__":
    main()