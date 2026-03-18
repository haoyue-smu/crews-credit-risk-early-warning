"""Event taxonomy shared across subgraphs.

The project uses this taxonomy for consistent labeling of extracted credit events
and their relative severity.
"""

from __future__ import annotations

from enum import Enum


class EventCategory(str, Enum):
    """High-level event category as defined in the project reference."""

    management_governance = "management_governance"
    legal_regulatory = "legal_regulatory"
    financial_distress_signals = "financial_distress_signals"
    operational_issues = "operational_issues"
    market_industry_risks = "market_industry_risks"
    reputation_sentiment = "reputation_sentiment"
    positive_signals = "positive_signals"


class Severity(str, Enum):
    """Relative severity for extracted signals."""

    low = "low"
    medium = "medium"
    high = "high"
    positive = "positive"

