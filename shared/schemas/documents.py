"""Input document contract for the SIS subgraph.

SIS consumes documents that have already been fetched and quality-scored by SQ.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    news = "news"
    forum = "forum"
    social = "social"
    filing = "filing"
    web = "web"


class DocumentInput(BaseModel):
    """A single externally sourced document as consumed by SIS."""

    document_id: str
    company_id: str
    source_name: str
    source_type: SourceType
    published_date: datetime
    fetched_date: datetime
    url: str
    full_text: str = Field(min_length=1)
    language: str
    source_quality_score: float = Field(ge=0.0, le=1.0)

    model_config = {"extra": "ignore"}

