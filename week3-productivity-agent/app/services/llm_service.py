"""
LLM Service: thin wrapper around an OpenAI-compatible chat completions API.

Supports two providers, selected automatically from environment variables:
  1. OpenAI (or any OpenAI-compatible endpoint) if OPENAI_API_KEY is set.
  2. Gemini's OpenAI-compatible endpoint if GEMINI_API_KEY is set.

If neither key is configured, the service runs in "offline" mode using
deterministic heuristic fallbacks so the rest of the application (tools,
tests, UI) keeps working -- this satisfies the "Missing API key" error
handling requirement without hard-crashing the whole app.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("productivity_agent.llm_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class LLMServiceError(Exception):
    """Raised for unrecoverable LLM API failures (invalid response, network, etc.)."""


def _friendly_llm_error(e: Exception) -> str:
    """Converts a raw provider exception (which may contain a huge JSON dump with
    internal URLs/quota details) into a short, human-readable message. Never
    exposes raw stack traces or the full provider payload to the end user."""
    text = str(e).lower()
    if "429" in text or "resource_exhausted" in text or "quota" in text or "rate limit" in text:
        return "the AI model's free-tier request quota has been reached for now - please try again later"
    if "401" in text or "invalid api key" in text or "unauthorized" in text or "permission" in text:
        return "the configured AI model API key was rejected - check GEMINI_API_KEY/OPENAI_API_KEY"
    if "timeout" in text or "timed out" in text:
        return "the AI model took too long to respond"
    if "connection" in text or "network" in text:
        return "couldn't connect to the AI model service"
    return "the AI model returned an unexpected error"


class LLMService:
    def __init__(self):
        self.provider = settings.active_provider
        self._client = None
        if self.provider != "none":
            try:
                from openai import OpenAI
                if self.provider == "openai":
                    self._client = OpenAI(
                        api_key=settings.openai_api_key,
                        base_url=settings.openai_base_url or None,
                    )
                    self.model = settings.openai_model
                else:
                    self._client = OpenAI(
                        api_key=settings.gemini_api_key,
                        base_url=settings.gemini_base_url,
                    )
                    self.model = settings.gemini_model
            except Exception:
                # SDK import or client construction failed -- fall back to offline mode
                self._client = None
                self.provider = "none"

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Structured decision-making call used by the Agent Controller
    # ------------------------------------------------------------------
    def decide(self, system_prompt: str, messages: List[Dict[str, str]],
               tool_schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Ask the LLM to decide whether to call a tool or answer directly.
        Returns a normalized dict: {"action": "tool_call"|"direct_answer",
                                     "tool_name": str|None, "tool_args": dict|None,
                                     "answer": str|None}
        """
        if not self.is_configured:
            raise LLMServiceError("No LLM API key configured (missing GEMINI_API_KEY / OPENAI_API_KEY).")

        full_messages = [{"role": "system", "content": system_prompt}] + messages
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                tools=tool_schemas,
                tool_choice="auto",
                temperature=0.2,
                timeout=settings.tool_timeout_seconds,
            )
        except Exception as e:
            logger.warning("Raw LLM API error (full detail, not shown in UI): %r", e)
            raise LLMServiceError(f"LLM API error: {_friendly_llm_error(e)}") from e

        try:
            choice = response.choices[0]
        except Exception as e:
            raise LLMServiceError("the AI model returned an unexpected response") from e

        msg = choice.message
        if getattr(msg, "tool_calls", None):
            call = msg.tool_calls[0]
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                raise LLMServiceError("the AI model returned malformed tool arguments") from e
            return {"action": "tool_call", "tool_name": call.function.name, "tool_args": args, "answer": None}

        return {"action": "direct_answer", "tool_name": None, "tool_args": None,
                "answer": (msg.content or "").strip()}

    # ------------------------------------------------------------------
    # Free-text generation helper (used for summarization, drafting, etc.)
    # ------------------------------------------------------------------
    def generate_text(self, prompt: str, system: str = "You are a helpful productivity assistant.") -> str:
        if not self.is_configured:
            raise LLMServiceError("No LLM API key configured (missing GEMINI_API_KEY / OPENAI_API_KEY).")
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                temperature=0.3,
                timeout=settings.tool_timeout_seconds,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("Raw LLM API error (full detail, not shown in UI): %r", e)
            raise LLMServiceError(f"LLM API error: {_friendly_llm_error(e)}") from e

    def summarize_text(self, text: str, instruction: str) -> str:
        try:
            return self.generate_text(f"{instruction}\n\nTEXT:\n{text}")
        except LLMServiceError:
            return self._offline_summarize(text)

    def extract_meeting_actions(self, transcript: str) -> Dict[str, Any]:
        """Structured extraction: summary, decisions, action_items, unresolved_questions."""
        schema_hint = (
            "Return ONLY valid JSON with this exact shape, no markdown fences:\n"
            '{"summary": str, "decisions": [str], '
            '"action_items": [{"description": str, "owner": str or null, "deadline": str or null}], '
            '"unresolved_questions": [str]}'
        )
        if self.is_configured:
            try:
                raw = self.generate_text(
                    f"Extract structured meeting information from the transcript below.\n{schema_hint}\n\n"
                    f"TRANSCRIPT:\n{transcript}",
                    system="You extract structured meeting data and respond with strict JSON only.",
                )
                cleaned = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE).strip()
                return json.loads(cleaned)
            except (LLMServiceError, json.JSONDecodeError):
                pass  # fall through to heuristic extraction
        return self._offline_extract_meeting_actions(transcript)

    # ------------------------------------------------------------------
    # Offline heuristic fallbacks (no API key / API failure)
    # ------------------------------------------------------------------
    def _offline_generate(self, prompt: str) -> str:
        return ("[Offline mode - no LLM API key configured] I can't generate free-form text right now, "
                "but structured tools (tasks, notes, plans) still work normally.")

    def _offline_summarize(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        bullets = [s.strip() for s in sentences if s.strip()][:5]
        return "\n".join(f"- {b}" for b in bullets) if bullets else "(nothing to summarize)"

    def _offline_extract_meeting_actions(self, transcript: str) -> Dict[str, Any]:
        raw_lines = [l for l in transcript.splitlines() if l.strip()]
        if len(raw_lines) <= 1:
            # single-line input (e.g. pasted as one paragraph) -> split into sentences instead
            raw_lines = re.split(r"(?<=[.!?])\s+", transcript.strip())
        lines = [l.strip("-• \t") for l in raw_lines if l.strip()]
        decisions, action_items, questions = [], [], []
        for line in lines:
            low = line.lower()
            if "?" in line:
                questions.append(line)
            elif any(k in low for k in ("decided", "agreed", "will go with", "approved")):
                decisions.append(line)
            elif any(k in low for k in ("action:", "todo", "to do", "will ", "needs to", "must ", "should ")):
                owner = None
                m = re.match(r"([A-Z][a-z]+)\s*(?:will|to|needs to|must|should)", line)
                if m:
                    owner = m.group(1)
                action_items.append({"description": line, "owner": owner, "deadline": None})
        summary = self._offline_summarize(transcript)
        return {
            "summary": summary,
            "decisions": decisions,
            "action_items": action_items,
            "unresolved_questions": questions,
        }


llm_service = LLMService()