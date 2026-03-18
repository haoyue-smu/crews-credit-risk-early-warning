"""SIS verification node placeholder (Phase 3).

Verifies that extracted signals are actually grounded in the source text by
re-checking LangExtract `char_interval` source grounding.
"""

from __future__ import annotations

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal


def parallel_verify_signals(
    signals: list[Signal],
    documents: list[DocumentInput],
) -> list[Signal]:
    """Verify extracted signals against source-grounding evidence.

    Args:
        signals: Signals produced by the extraction + validation steps.
        documents: Original documents used for grounding.

    Returns:
        Signals whose evidence has been verified (or flagged for review).
    """

    raise NotImplementedError("Phase 2/3/4")

