"""Centralized LLM client configuration for all four pipeline subgraphs.

All subgraphs use OpenRouter (openrouter.ai) as the LLM gateway via the
standard OpenAI SDK. OpenRouter is OpenAI API-compatible so no special SDK
is required — just an api_key and a base_url.

To change the model for a specific stage, set the corresponding environment
variable. To change all stages at once, set OPENROUTER_MODEL_ID.

  Environment variables (optional, all fall back to OPENROUTER_MODEL_ID):
    OPENROUTER_MODEL_FIS  — FIS: financial document parsing
    OPENROUTER_MODEL_RS   — RS: query planning + relevance scoring
    OPENROUTER_MODEL_SIS  — SIS: signal extraction, verification, conflict
    OPENROUTER_MODEL_FRD  — FRD: analyst report generation

  Example .env to run everything on a cheaper model:
    OPENROUTER_MODEL_ID=google/gemini-2.0-flash

  Example .env to use a stronger model for report generation:
    OPENROUTER_MODEL_ID=google/gemini-2.5-flash
    OPENROUTER_MODEL_FRD=google/gemini-2.5-pro

Supported OpenRouter model IDs:  https://openrouter.ai/models
"""

import os
from openai import OpenAI, AsyncOpenAI

from shared.config import settings

_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Per-stage model IDs — change these (or the env vars) to swap models
# ---------------------------------------------------------------------------

_default = settings.openrouter_model_id  # from OPENROUTER_MODEL_ID, default: google/gemini-2.5-flash

MODEL_FIS: str = os.environ.get("OPENROUTER_MODEL_FIS") or _default
MODEL_RS: str  = os.environ.get("OPENROUTER_MODEL_RS")  or _default
MODEL_SIS: str = os.environ.get("OPENROUTER_MODEL_SIS") or _default
MODEL_FRD: str = os.environ.get("OPENROUTER_MODEL_FRD") or _default


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------

def get_client() -> OpenAI:
    """Synchronous OpenRouter client — used by FIS, SIS, and FRD."""
    settings.require_llm()
    return OpenAI(base_url=_BASE_URL, api_key=settings.openrouter_api_key)


def get_async_client() -> AsyncOpenAI:
    """Async OpenRouter client — used by RS."""
    settings.require_llm()
    return AsyncOpenAI(base_url=_BASE_URL, api_key=settings.openrouter_api_key)
