"""
Experiment 3: Model Temperature (Assignment 6)

Compares three temperature settings (0.0, 0.5, 1.0) on:
  - Tool selection (does it still pick the right tool?)
  - Output consistency (running the SAME prompt 3x - same tool chosen each time?)
  - Hallucination (does it ever propose a tool name that doesn't exist?)
  - Response quality (captured verbatim for manual review - "quality" is
    inherently subjective, so this script records the raw text rather than
    inventing a fake numeric score)

REQUIRES a working LLM API key. Run on your own machine:
    python tests/experiments/experiment_3_temperature.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.llm_service import llm_service, LLMServiceError  # noqa: E402
from app.tools import registry  # noqa: E402
from app.agent.prompts import SYSTEM_PROMPT  # noqa: E402

TEMPERATURES = [0.0, 0.5, 1.0]
REPEATS_PER_TEMPERATURE = 3  # to measure consistency

TEST_PROMPTS = [
    ("Show me all high-priority tasks.", "list_tasks"),
    ("Create a task to review the quarterly budget report.", "create_task"),
    ("Prepare a daily work plan.", "generate_work_plan"),
    ("Search my notes for the marketing campaign.", "search_notes"),
    ("Explain the difference between High and Critical priority.", None),  # should be a direct answer
]

VALID_TOOL_NAMES = set(registry.names())


def call_with_temperature(system_prompt: str, user_message: str, temperature: float) -> dict:
    """Mirrors llm_service.decide() but with a configurable temperature,
    since the shared helper hardcodes temperature=0.2."""
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
    response = llm_service._client.chat.completions.create(
        model=llm_service.model, messages=messages, tools=registry.openai_schemas(),
        tool_choice="auto", temperature=temperature,
    )
    choice = response.choices[0]
    msg = choice.message
    if getattr(msg, "tool_calls", None):
        call = msg.tool_calls[0]
        return {"action": "tool_call", "tool_name": call.function.name, "text": None}
    return {"action": "direct_answer", "tool_name": None, "text": (msg.content or "").strip()}


def main():
    if not llm_service.is_configured:
        print("ERROR: No LLM API key configured. This experiment requires real API calls.")
        sys.exit(1)

    all_results = []
    for temperature in TEMPERATURES:
        print(f"\n=== Temperature {temperature} ===")
        temp_results = []
        for prompt, expected_tool in TEST_PROMPTS:
            trials = []
            for _ in range(REPEATS_PER_TEMPERATURE):
                try:
                    result = call_with_temperature(SYSTEM_PROMPT, prompt, temperature)
                except LLMServiceError as e:
                    result = {"action": "error", "tool_name": None, "text": str(e)}
                trials.append(result)
                time.sleep(1)

            tools_chosen = [t["tool_name"] for t in trials]
            hallucinated = any(t and t not in VALID_TOOL_NAMES for t in tools_chosen)
            consistent = len(set(tools_chosen)) <= 1  # same choice (or same None) every time
            correct = expected_tool is None and all(t["action"] == "direct_answer" for t in trials) or \
                      all(t == expected_tool for t in tools_chosen)

            temp_results.append({
                "prompt": prompt, "expected_tool": expected_tool, "trials": trials,
                "tools_chosen": tools_chosen, "consistent": consistent,
                "hallucinated_tool_name": hallucinated, "correct": correct,
            })
            print(f"  '{prompt[:50]}...' -> {tools_chosen} (consistent={consistent})")

        consistency_rate = round(100 * sum(1 for r in temp_results if r["consistent"]) / len(temp_results), 1)
        accuracy_rate = round(100 * sum(1 for r in temp_results if r["correct"]) / len(temp_results), 1)
        hallucination_rate = round(100 * sum(1 for r in temp_results if r["hallucinated_tool_name"])
                                    / len(temp_results), 1)

        all_results.append({
            "temperature": temperature, "consistency_rate_pct": consistency_rate,
            "tool_selection_accuracy_pct": accuracy_rate, "hallucination_rate_pct": hallucination_rate,
            "details": temp_results,
        })

    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "experiment_3_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + json.dumps([{k: v for k, v in r.items() if k != "details"} for r in all_results], indent=2))
    print("\nResponse-quality note: raw response text for direct-answer prompts is saved in "
          "experiment_3_results.json under details[].trials[].text for manual/qualitative review, "
          "since 'quality' is subjective and shouldn't be reduced to a fabricated score.")


if __name__ == "__main__":
    main()