"""SIS extraction node placeholder (Phase 2).

Responsible for extracting credit-relevant signals from SQ-produced documents
using LangExtract + Gemini.
"""

from __future__ import annotations

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal


def parallel_extract_signals(documents: list[DocumentInput]) -> list[Signal]:
    """Extract signals from documents (parallelized LLM extraction).

    Args:
        documents: Documents produced by SQ for a single company or batch.

    Returns:
        Extracted raw signals with traceability (`char_interval`) and evidence.
    """

    raise NotImplementedError("Phase 2/3/4")

