"""SIS conflict resolution node placeholder (Phase 3).

Resolves or flags contradictions across signals extracted from multiple
sources using source quality weighting and temporal reasoning.
"""

from __future__ import annotations

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal


def conflict_resolution(
    signals: list[Signal],
    documents: list[DocumentInput],
) -> list[Signal]:
    """Resolve contradictions and merge duplicate signals.

    Args:
        signals: Signals produced by extraction/verification.
        documents: Source documents used to support conflict reasoning.

    Returns:
        Signals with updated `conflict_status` and evidence.
    """

    raise NotImplementedError("Phase 2/3/4")

