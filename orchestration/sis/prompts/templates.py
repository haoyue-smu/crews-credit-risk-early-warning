"""Prompt templates for LangExtract calls in the SIS subgraph.

Only Phase 2 (extraction) is concretized here; other prompt variants will be
added in later phases.
"""

from __future__ import annotations


EXTRACTION_PROMPT: str = (
    "You are extracting credit-relevant signals from the provided financial/news text "
    "for a corporate client. Use the EventCategory taxonomy for the `event_type` "
    "field and the project Severity taxonomy for the `severity` field.\n\n"
    "Allowed EventCategory values:\n"
    "- management_governance\n"
    "- legal_regulatory\n"
    "- financial_distress_signals\n"
    "- operational_issues\n"
    "- market_industry_risks\n"
    "- reputation_sentiment\n"
    "- positive_signals\n\n"
    "Allowed severity values: low, medium, high, positive.\n\n"
    "Use `event_subtype` as a free-form specific event name (e.g., debt_restructuring, ceo_departure).\n\n"
    "Extraction rules:\n"
    "1. Extract exact text spans from the input. Do NOT paraphrase.\n"
    "2. List extracted signals in the order they appear in the input text.\n"
    "3. For each extracted signal, provide:\n"
    "   - `event_type` (one value from EventCategory)\n"
    "   - `event_subtype` (free-form string specific to the event)\n"
    "   - `severity` (one value from Severity: low/medium/high/positive)\n"
    "4. If multiple signals are present, include each as a separate extraction."
)


def get_sis_prompt_templates() -> dict[str, str]:
    """Return prompt templates used by the SIS nodes."""

    return {"EXTRACTION_PROMPT": EXTRACTION_PROMPT}

