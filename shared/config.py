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

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    gemini_model_id: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL_ID")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


def load_settings() -> Settings:
    """Load settings from environment variables."""

    return Settings()


settings: Settings = load_settings()

