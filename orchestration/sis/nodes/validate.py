"""SIS schema validation gate placeholder (Phase 2).

Deterministically validates raw LLM extractions using Pydantic schemas and
routes invalid outputs to retry logic (handled elsewhere in Phase 2).
"""

from __future__ import annotations

from shared.schemas.signals import Signal


def schema_validation_gate(signals: list[Signal]) -> list[Signal]:
    """Validate extracted signals against Pydantic schemas.

    Args:
        signals: Raw extracted signals from `parallel_extract_signals`.

    Returns:
        The subset of signals that pass validation (or are retried upstream).
    """

    raise NotImplementedError("Phase 2/3/4")

