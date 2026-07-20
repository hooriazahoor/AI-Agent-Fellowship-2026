"""
Experiment 2: Structured versus Unstructured Output (Assignment 6)

Compares parsing failure rate when the LLM is asked for:
  (a) free-text prose (no schema) - we then try to regex-extract fields, or
  (b) strict JSON matching our Pydantic-shaped schema (json.loads + field checks)

REQUIRES a working LLM API key. Run on your own machine:
    python tests/experiments/experiment_2_structured_vs_unstructured.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.llm_service import llm_service, LLMServiceError  # noqa: E402

TRANSCRIPTS = [
    "We decided to migrate to Postgres. Sarah will finalize the API contract by Friday. "
    "John needs to update the documentation. Should we also migrate the auth service?",
    "The team agreed to launch the website on August 1st. Ali will finalize the homepage. "
    "Sara will test the payment gateway. Next review meeting is Friday.",
    "Budget was approved for Q3. Finance team will send the breakdown by next week. "
    "Marketing needs to finalize the campaign calendar. Are we still on track for the trade show?",
    "Decided to redesign the landing page. Ayesha will draft wireframes by Wednesday. "
    "Bilal will review competitor sites. Should we A/B test the new design?",
    "The bug in the login flow was traced to a session timeout issue. Maria will patch it today. "
    "QA will retest tomorrow. Do we need to notify affected users?",
    "Standup notes: sprint goals reviewed, two blockers identified. Omar will unblock the CI pipeline. "
    "Fatima will pair with a new hire this week.",
    "Client call recap: they want an extra reporting dashboard. David will scope the requirements "
    "by Monday. Is this in scope for the current contract?",
    "Decided to move the office to hybrid schedule starting next month. HR will send the new policy. "
    "Team leads will collect preferences by Friday.",
]

FREE_TEXT_PROMPT = (
    "Summarize this meeting in a natural paragraph. Mention the summary, any decisions made, "
    "action items (with owners and deadlines if mentioned), and any open questions. Write it as "
    "flowing prose, not a list or JSON.\n\nMEETING NOTES:\n{transcript}"
)

STRUCTURED_PROMPT = (
    "Extract structured meeting information from the transcript below. Return ONLY valid JSON, "
    'no markdown fences, with this exact shape:\n'
    '{{"summary": str, "decisions": [str], '
    '"action_items": [{{"description": str, "owner": str or null, "deadline": str or null}}], '
    '"unresolved_questions": [str]}}\n\nTRANSCRIPT:\n{transcript}'
)


def try_parse_free_text(text: str) -> dict:
    """Best-effort regex extraction from free prose - representative of what
    you'd have to do without a schema."""
    has_decision_word = bool(re.search(r"\bdecided|agreed|approved\b", text, re.IGNORECASE))
    action_items = re.findall(r"([A-Z][a-z]+ (?:will|to) [^.]+\.)", text)
    has_question = "?" in text
    ok = len(text.strip()) > 20  # got *something* back
    return {"decisions_found": has_decision_word, "action_items_found": len(action_items),
            "questions_found": has_question, "parse_ok": ok, "raw_length": len(text)}


def try_parse_structured(text: str) -> dict:
    cleaned = re.sub(r"^```json|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        obj = json.loads(cleaned)
        required = {"summary", "decisions", "action_items", "unresolved_questions"}
        missing = required - set(obj.keys())
        return {"parse_ok": len(missing) == 0, "missing_fields": list(missing), "json_valid": True}
    except json.JSONDecodeError as e:
        return {"parse_ok": False, "missing_fields": [], "json_valid": False, "error": str(e)}


def main():
    if not llm_service.is_configured:
        print("ERROR: No LLM API key configured. This experiment requires real API calls.")
        sys.exit(1)

    free_text_results, structured_results = [], []

    for transcript in TRANSCRIPTS:
        try:
            raw = llm_service.generate_text(FREE_TEXT_PROMPT.format(transcript=transcript),
                                            system="You are a helpful meeting-notes assistant.")
            parsed = try_parse_free_text(raw)
        except LLMServiceError as e:
            parsed = {"parse_ok": False, "error": str(e)}
        free_text_results.append(parsed)
        time.sleep(1)

    for transcript in TRANSCRIPTS:
        try:
            raw = llm_service.generate_text(STRUCTURED_PROMPT.format(transcript=transcript),
                                            system="You extract structured meeting data and respond with "
                                                   "strict JSON only.")
            parsed = try_parse_structured(raw)
        except LLMServiceError as e:
            parsed = {"parse_ok": False, "json_valid": False, "error": str(e)}
        structured_results.append(parsed)
        time.sleep(1)

    free_text_failure_rate = round(100 * sum(1 for r in free_text_results if not r["parse_ok"])
                                    / len(free_text_results), 1)
    structured_failure_rate = round(100 * sum(1 for r in structured_results if not r["parse_ok"])
                                     / len(structured_results), 1)

    summary = {
        "free_text_parsing_failure_rate_pct": free_text_failure_rate,
        "structured_json_parsing_failure_rate_pct": structured_failure_rate,
        "n_transcripts": len(TRANSCRIPTS),
    }

    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "experiment_2_results.json", "w") as f:
        json.dump({"summary": summary, "free_text_results": free_text_results,
                   "structured_results": structured_results}, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()