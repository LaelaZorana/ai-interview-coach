"""Runtime configuration, read once from the environment.

Everything here has a safe default so the app boots with zero setup. The only
knobs that change behaviour meaningfully are the LLM provider keys; when none is
present the deterministic offline stub is used automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    # Web / session
    secret_key: str
    database_url: str
    session_cookie: str = "interviewcoach_session"
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days

    # LLM provider selection. provider is one of: "stub", "anthropic", "openai".
    llm_provider: str = "stub"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    openai_model: str = "gpt-4o-mini"

    @property
    def using_real_llm(self) -> bool:
        return self.llm_provider in ("anthropic", "openai")


def _pick_provider() -> str:
    """Choose a provider from env, preferring an explicit override.

    Resolution order:
      1. LLM_PROVIDER env var, if set to a known value.
      2. A present ANTHROPIC_API_KEY -> anthropic.
      3. A present OPENAI_API_KEY -> openai.
      4. Fall back to the offline stub.
    """
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit in ("stub", "anthropic", "openai"):
        return explicit
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "stub"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        secret_key=os.getenv("SECRET_KEY", "dev-insecure-change-me"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./interviewcoach.db"),
        llm_provider=_pick_provider(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
