"""Shared configuration loader.

Loads API keys and service settings from the project .env file (or real environment).

Usage
-----
    from shared.config import settings

    # Validate required keys before starting a pipeline stage:
    settings.require_llm()      # raises if OPENROUTER_API_KEY is unset
    settings.require_retrieval() # raises if TAVILY_API_KEY is unset

All LLM calls (FIS, RS, SIS, FRD) go through OpenRouter. Only two API keys
are needed to run the full pipeline:
  - OPENROUTER_API_KEY   — LLM gateway (Gemini, GPT-4, etc. via OpenRouter)
  - TAVILY_API_KEY       — web retrieval for the RS subgraph
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(override=True)


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    # OpenRouter — LLM gateway for all four subgraphs
    openrouter_api_key: Optional[str] = Field(default=None)
    openrouter_model_id: str = Field(default="google/gemini-2.5-flash")

    # Tavily — web retrieval for RS
    tavily_api_key: Optional[str] = Field(default=None)

    # Database (defaults to SQLite; override with a PostgreSQL URL for production)
    database_url: Optional[str] = Field(default=None)

    model_config = {"extra": "ignore"}

    # ------------------------------------------------------------------
    # Validation helpers — call these at the start of each pipeline stage
    # ------------------------------------------------------------------

    def require_llm(self) -> None:
        """Raise if OPENROUTER_API_KEY is not configured.

        Call at the top of any node that uses an LLM so the failure is obvious
        and actionable rather than a cryptic 401 from the API.
        """
        if not self.openrouter_api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to your .env file before running any pipeline stage."
            )

    def require_retrieval(self) -> None:
        """Raise if TAVILY_API_KEY is not configured."""
        if not self.tavily_api_key:
            raise EnvironmentError(
                "TAVILY_API_KEY is not set. "
                "Add it to your .env file before running the RS subgraph."
            )


settings = Settings(
    openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
    tavily_api_key=os.environ.get("TAVILY_API_KEY"),
    database_url=os.environ.get("DATABASE_URL"),
    openrouter_model_id=os.environ.get("OPENROUTER_MODEL_ID", "google/gemini-2.5-flash"),
)
