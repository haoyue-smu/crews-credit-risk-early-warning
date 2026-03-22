"""Prompt templates for LangExtract calls in the SIS subgraph.

Only Phase 2 (extraction) is concretized here; other prompt variants will be
added in later phases.
"""

from __future__ import annotations


EXTRACTION_PROMPT: str = (
    "You are extracting credit-relevant signals from the provided financial/news text "
    "for a single corporate obligor. Use the EventCategory taxonomy for `event_type` "
    "and the Severity taxonomy below for `severity`.\n\n"
    "Allowed EventCategory values:\n"
    "- management_governance\n"
    "- legal_regulatory\n"
    "- financial_distress_signals\n"
    "- operational_issues\n"
    "- market_industry_risks\n"
    "- reputation_sentiment\n"
    "- positive_signals\n\n"
    "Severity — assign exactly one per extraction. Use these criteria:\n"
    "- high: direct financial impact; legal action or material litigation; payment default or "
    "missed payment; regulatory penalty or enforcement; executive termination or forced leadership "
    "change tied to firm risk.\n"
    "- medium: operational disruption; employee dissatisfaction or morale issues; leadership "
    "uncertainty; asset sale difficulties or refinancing stress short of confirmed default.\n"
    "- low: general industry trends not specific to the obligor; minor sentiment shifts; routine "
    "business or reporting updates with no clear credit impact.\n"
    "- positive: new funding or liquidity support; material contract wins; credit upgrades; "
    "or explicit company statements that deny or refute negative credit events AND the text "
    "provides a clear, substantive basis (not mere marketing boilerplate).\n\n"
    "Use `event_subtype` as a concise snake_case label (e.g., debt_restructuring, "
    "denial_of_restructuring, operations_reaffirmation).\n\n"
    "Negative constraints — do NOT extract:\n"
    "- General industry background, sector commentary, or macro narrative unless it is explicitly "
    "tied to this company's credit position.\n"
    "- Boilerplate corporate language, safe-harbor disclaimers, or generic forward-looking "
    "statements with no specific factual claim.\n"
    "- Statements that are not specific to the company's credit risk profile.\n\n"
    "Company pushback and denials:\n"
    "If the source text contains explicit denials, contradictions of negative events, or "
    "reaffirmations of normal operations/payments, extract these as `positive_signals` with an "
    "appropriate `event_subtype` (e.g., denial_of_restructuring, denial_of_default_rumors, "
    "operations_reaffirmation, payment_obligations_reaffirmation). Use exact spans from the text.\n\n"
    "Extraction rules:\n"
    "1. Extract exact text spans from the input. Do NOT paraphrase.\n"
    "2. List extracted signals in the order they appear in the input text.\n"
    "3. For each extracted signal, provide:\n"
    "   - `event_type` (one EventCategory value)\n"
    "   - `event_subtype` (free-form string)\n"
    "   - `severity` (one of: low, medium, high, positive)\n"
    "4. If multiple signals are present, include each as a separate extraction."
)


def get_sis_prompt_templates() -> dict[str, str]:
    """Return prompt templates used by the SIS nodes."""

    return {"EXTRACTION_PROMPT": EXTRACTION_PROMPT}
