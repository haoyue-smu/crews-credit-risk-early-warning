"""Targeted retrieval request contract sent from SIS back to RS.

This model follows Section 6.3: when evidence is weak, SIS instructs RS
to re-plan targeted searches (instead of parallel fetching).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TargetedRetrievalRequest(BaseModel):
    """Retrieval intent and constraints for RS re-planning."""

    company_id: str
    keywords: list[str] = Field(min_length=1)
    target_source_types: list[str] = Field(min_length=1)
    signal_context: str = Field(min_length=1)

    model_config = {"extra": "ignore"}

    @field_validator("keywords")
    @classmethod
    def keywords_non_empty(cls, v: list[str]) -> list[str]:
        if any(not kw or not kw.strip() for kw in v):
            raise ValueError("keywords must be non-empty strings")
        return v

