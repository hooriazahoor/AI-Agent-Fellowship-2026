"""
Centralized, environment-based configuration.
No secrets are hard-coded anywhere in this codebase -- everything is read
from environment variables (via a local .env file during development).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # LLM provider selection: prefer OpenAI-compatible custom config if provided,
    # otherwise fall back to Gemini's OpenAI-compatible endpoint.
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    )
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/productivity_agent.db")
    )

    flask_secret_key: str = field(
        default_factory=lambda: os.getenv("FLASK_SECRET_KEY", "dev-only-insecure-key")
    )
    flask_debug: bool = field(default_factory=lambda: _get_bool("FLASK_DEBUG", True))
    port: int = field(default_factory=lambda: _get_int("PORT", 5000))

    max_agent_steps: int = field(default_factory=lambda: _get_int("MAX_AGENT_STEPS", 8))
    max_tool_retries: int = field(default_factory=lambda: _get_int("MAX_TOOL_RETRIES", 2))
    tool_timeout_seconds: int = field(default_factory=lambda: _get_int("TOOL_TIMEOUT_SECONDS", 30))

    @property
    def active_provider(self) -> str:
        """Which LLM provider is active: 'openai', 'gemini', or 'none'."""
        if self.openai_api_key:
            return "openai"
        if self.gemini_api_key:
            return "gemini"
        return "none"


settings = Settings()
