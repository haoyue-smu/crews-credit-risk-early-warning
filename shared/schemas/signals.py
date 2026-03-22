"""SIS output and its supporting signal/evidence schemas.

These models follow the contracts in the project reference:
- Section 6.2: SIS output to FRD
- Includes HITL-related fields: `resolution_path` and `review_status`
- Includes traceability: `char_interval`
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from shared.taxonomy import EventCategory, Severity


class CharInterval(BaseModel):
    """Start/end character offsets for source-grounded evidence."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def check_order(self) -> "CharInterval":
        if self.end < self.start:
            raise ValueError("char_interval end must be >= start")
        return self


class ConflictStatus(str, Enum):
    no_conflict = "no_conflict"
    resolved = "resolved"
    disputed = "disputed"


class ResolutionPath(str, Enum):
    auto = "auto"
    pending = "pending"
    completed = "completed"


class ReviewStatus(str, Enum):
    verified = "verified"
    rejected = "rejected"
    forwarded = "forwarded"


class Evidence(BaseModel):
    """A single grounded evidence snippet supporting a signal."""

    source_name: str
    document_id: str
    date: datetime
    snippet: str = Field(min_length=1)
    char_interval: CharInterval
    source_quality: float = Field(ge=0.0, le=1.0)

    model_config = {"extra": "ignore"}


class Signal(BaseModel):
    """A single credit-relevant signal produced by SIS."""

    signal_id: str
    event_type: EventCategory
    # Free-form, specific subtype (grows over time without enum changes).
    event_subtype: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguous: bool

    conflict_status: ConflictStatus = ConflictStatus.no_conflict
    resolution_path: ResolutionPath = ResolutionPath.auto
    review_status: Optional[ReviewStatus] = None

    # Traceability: each Evidence carries its own LangExtract grounding interval.
    evidence: list[Evidence] = Field(default_factory=list)

    # evidence_gate: routing intent for FRD / RS (Scheme A: all signals still delivered to FRD).
    evidence_route: Literal["frd_direct", "targeted_retrieval"] = "frd_direct"
    evidence_notes: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def check_review_status_rules(self) -> "Signal":
        if self.resolution_path != ResolutionPath.completed and self.review_status is not None:
            raise ValueError("review_status must be null unless resolution_path is 'completed'")
        if self.resolution_path == ResolutionPath.completed and self.review_status is None:
            raise ValueError("review_status must be set when resolution_path is 'completed'")
        return self


class SISMetadata(BaseModel):
    """Processing metadata for SIS output to FRD."""

    documents_processed: int = Field(ge=0)
    signals_extracted: int = Field(ge=0)
    signals_auto_verified: int = Field(ge=0)
    signals_ambiguous: int = Field(ge=0)
    signals_pending_review: int = Field(ge=0)
    signals_rejected: int = Field(ge=0)
    timestamp: datetime

    model_config = {"extra": "ignore"}


class SISOutput(BaseModel):
    """SIS output contract consumed by FRD."""

    company_id: str
    signals: list[Signal]
    metadata: SISMetadata

    model_config = {"extra": "ignore"}

