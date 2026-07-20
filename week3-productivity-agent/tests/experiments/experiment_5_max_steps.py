"""
Experiment 5: Maximum Agent Steps (Assignment 6)

Varies MAX_AGENT_STEPS across several limits and observes completion rate,
loop prevention, latency, and a "cost" proxy (number of tool/LLM decision
calls made per run) - using controlled fault injection against the REAL
agent loop in app/agent/controller.py (no LLM API access needed, since this
targets the loop's own step-limiting/duplicate-detection mechanism, not an
LLM's behavior).

Two synthetic decision generators are injected in place of
AgentController._decide_next_action for the duration of each trial:

  Scenario A ("needs K steps"): simulates a well-behaved multi-step agent
  that legitimately needs K sequential tool calls before it has enough
  information to answer. Tests whether completion rate drops once
  MAX_AGENT_STEPS < K.

  Scenario B ("confused/looping agent"): simulates a mis-behaving decision
  step that keeps proposing the SAME tool call forever. Tests whether the
  duplicate-call detector (and the step ceiling as a backstop) reliably
  stops it regardless of MAX_AGENT_STEPS.

Usage:
    python tests/experiments/experiment_5_max_steps.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ.setdefault("DATABASE_URL", "sqlite:///data/experiment_run.db")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.database.repository import init_db  # noqa: E402
from app.database import repository as repo  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.agent.controller import AgentController  # noqa: E402
from app.config import settings  # noqa: E402
from app.services.llm_service import llm_service  # noqa: E402

STEP_LIMITS_TO_TEST = [1, 2, 3, 5, 8, 16]


def make_scenario_a_decider(required_steps: int):
    """Needs exactly `required_steps` tool calls (list_tasks, alternating with
    detect_overdue_tasks) before it's ready to answer directly."""
    call_count = {"n": 0}

    def fake_decide(self, state, user_text, trail):
        call_count["n"] += 1
        if call_count["n"] < required_steps:
            tool = "list_tasks" if call_count["n"] % 2 == 1 else "detect_overdue_tasks"
            return {"action": "tool_call", "tool_name": tool, "tool_args": {"_call": call_count["n"]}}
        return {"action": "direct_answer", "answer": f"Done after {call_count['n']} steps."}

    return fake_decide, call_count


def make_scenario_b_decider():
    """Always proposes the exact same tool call - a 'confused agent' that
    never converges. Should be caught by duplicate-call detection."""
    def fake_decide(self, state, user_text, trail):
        return {"action": "tool_call", "tool_name": "list_tasks", "tool_args": {"status": "Pending"}}
    return fake_decide


def run_trial(max_steps: int, decider_factory, scenario_name: str, needed_steps: int = None) -> dict:
    object.__setattr__(settings, "max_agent_steps", max_steps)
    controller = AgentController()

    if scenario_name == "A":
        fake_decide, call_count = decider_factory(needed_steps)
    else:
        fake_decide = decider_factory()
        call_count = None

    original = AgentController._decide_next_action
    AgentController._decide_next_action = fake_decide
    original_client = llm_service._client
    original_provider = llm_service.provider
    original_model = getattr(llm_service, "model", None)
    llm_service._client = object()  # pretend configured so the loop doesn't single-shot short-circuit;
                                     # _decide_next_action itself is fully replaced, so no real API call happens
    llm_service.provider = "test-harness"
    llm_service.model = "synthetic-decider"
    try:
        start = time.time()
        response = controller.handle_message(str(uuid.uuid4()), "synthetic test request")
        duration_ms = round((time.time() - start) * 1000, 2)
    finally:
        AgentController._decide_next_action = original
        llm_service._client = original_client
        llm_service.provider = original_provider
        llm_service.model = original_model

    completed_successfully = (
        response.status == "completed" and "reached the maximum number of steps" not in response.message
        and "repeated identical tool call" not in response.message
    )
    hit_step_ceiling = "reached the maximum number of steps" in response.message
    caught_loop = "repeated step" in response.message

    return {
        "scenario": scenario_name,
        "max_agent_steps": max_steps,
        "needed_steps": needed_steps,
        "actual_tool_calls_made": len(response.tool_calls),
        "completed_successfully": completed_successfully,
        "hit_step_ceiling": hit_step_ceiling,
        "caught_loop": caught_loop,
        "duration_ms": duration_ms,
        "final_message": response.message[:150],
    }


def main():
    Base.metadata.drop_all(repo._engine)
    Base.metadata.create_all(repo._engine)
    repo.create_task(title="Sample task", priority="Medium")

    results = []

    # Scenario A: legitimately multi-step tasks of varying difficulty (2-10 steps needed)
    for max_steps in STEP_LIMITS_TO_TEST:
        for needed in [2, 4, 6, 10]:
            results.append(run_trial(max_steps, make_scenario_a_decider, "A", needed_steps=needed))

    # Scenario B: confused/looping agent - should always be caught quickly
    for max_steps in STEP_LIMITS_TO_TEST:
        results.append(run_trial(max_steps, make_scenario_b_decider, "B"))

    object.__setattr__(settings, "max_agent_steps", 8)  # restore default

    # ---- Aggregate per max_agent_steps setting ----
    summary = {}
    for max_steps in STEP_LIMITS_TO_TEST:
        subset_a = [r for r in results if r["scenario"] == "A" and r["max_agent_steps"] == max_steps]
        subset_b = [r for r in results if r["scenario"] == "B" and r["max_agent_steps"] == max_steps]
        completion_rate = round(100 * sum(1 for r in subset_a if r["completed_successfully"]) / len(subset_a), 1)
        avg_latency_a = round(sum(r["duration_ms"] for r in subset_a) / len(subset_a), 2)
        avg_cost_a = round(sum(r["actual_tool_calls_made"] for r in subset_a) / len(subset_a), 2)
        loop_always_caught = all(r["caught_loop"] or r["hit_step_ceiling"] for r in subset_b)
        avg_latency_b = round(sum(r["duration_ms"] for r in subset_b) / len(subset_b), 2)
        avg_cost_b = round(sum(r["actual_tool_calls_made"] for r in subset_b) / len(subset_b), 2)

        summary[max_steps] = {
            "scenario_a_completion_rate_pct": completion_rate,
            "scenario_a_avg_latency_ms": avg_latency_a,
            "scenario_a_avg_tool_calls_cost_proxy": avg_cost_a,
            "scenario_b_loop_always_prevented": loop_always_caught,
            "scenario_b_avg_latency_ms": avg_latency_b,
            "scenario_b_avg_tool_calls_cost_proxy": avg_cost_b,
        }

    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "experiment_5_results.json", "w") as f:
        json.dump({"raw_trials": results, "summary_by_step_limit": summary}, f, indent=2)

    print(json.dumps(summary, indent=2))
    return results, summary


if __name__ == "__main__":
    main()