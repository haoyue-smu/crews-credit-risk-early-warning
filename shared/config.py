"""Shared configuration loader.

Loads API keys and service configuration from the project `.env` file.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    # Optional fallback
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    
    # Primary LLM Gateway
    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model_id: str = Field(default="google/gemini-2.5-flash", alias="OPENROUTER_MODEL_ID")
    
    # Retrieval Tools
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


def load_settings() -> Settings:
    """Load settings from environment variables."""
    import os
    return Settings(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        tavily_api_key=os.environ.get("TAVILY_API_KEY"),
        database_url=os.environ.get("DATABASE_URL"),
        openrouter_model_id=os.environ.get("OPENROUTER_MODEL_ID", "google/gemini-2.5-flash")
    )


settings: Settings = load_settings()

