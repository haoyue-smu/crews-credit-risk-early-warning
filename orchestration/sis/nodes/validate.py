"""SIS schema validation gate (Phase 3).

Deterministically validates raw LLM extractions using Pydantic schemas and
routes invalid outputs to retry logic. This node is fully deterministic.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Evidence, Signal


def _validate_evidence(
    evidence: Evidence,
    documents_by_id: Dict[str, DocumentInput],
) -> Tuple[bool, bool, str | None]:
    """Validate a single Evidence instance.

    Returns:
        (is_valid, has_soft_warning, reason_if_invalid)
    """

    doc = documents_by_id.get(evidence.document_id)
    if doc is None:
        return False, False, f"document_id {evidence.document_id!r} not found"

    ci = evidence.char_interval
    if ci.start < 0 or ci.end < 0 or ci.end <= ci.start:
        return False, False, "invalid char_interval ordering or negative index"

    soft_warning = False
    if ci.end > len(doc.full_text):
        soft_warning = True

    if not evidence.snippet:
        return False, soft_warning, "empty evidence snippet"

    return True, soft_warning, None


def schema_validation_gate(
    signals: List[Signal],
    documents: List[DocumentInput],
    retry_counts: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Validate extracted signals against Pydantic schemas and document text.

    Args:
        signals: Raw extracted signals from `parallel_extract_signals`.
        documents: Original `DocumentInput` list for the batch.
        retry_counts: Optional mapping of document_id -> current retry count.

    Returns:
        A dict with three paths:
        - ``valid_signals``: signals that passed validation cleanly.
        - ``retry_needed``: list of document_ids that should be re-extracted.
        - ``passed_with_warnings``: signals that had validation issues but are
          being allowed through.
    """

    documents_by_id: Dict[str, DocumentInput] = {d.document_id: d for d in documents}
    retry_counts = retry_counts or {}

    valid_signals: List[Signal] = []
    passed_with_warnings: List[Signal] = []

    total_by_doc: Dict[str, int] = defaultdict(int)
    failed_by_doc: Dict[str, List[Signal]] = defaultdict(list)

    for signal in signals:
        primary_doc_id = signal.evidence[0].document_id if signal.evidence else None
        if primary_doc_id is None:
            failed_by_doc["<unknown>"].append(signal)
            continue

        total_by_doc[primary_doc_id] += 1

        is_valid = True
        has_soft_warning = False
        reason: str | None = None

        if not signal.evidence:
            is_valid = False
            reason = "no evidence attached"
        else:
            for ev in signal.evidence:
                ev_valid, ev_soft, ev_reason = _validate_evidence(
                    ev,
                    documents_by_id,
                )
                if ev_soft:
                    has_soft_warning = True
                if not ev_valid:
                    is_valid = False
                    reason = ev_reason
                    break

        if is_valid:
            if has_soft_warning:
                passed_with_warnings.append(signal)
            else:
                valid_signals.append(signal)
        else:
            failed_by_doc[primary_doc_id].append(signal)
            if reason:
                print(f"[schema_validation_gate] Signal {signal.signal_id} invalid: {reason}")

    retry_needed: List[str] = []

    for doc_id, total in total_by_doc.items():
        if total == 0:
            continue
        failed = len(failed_by_doc.get(doc_id, []))
        failure_rate = failed / float(total)
        current_retries = retry_counts.get(doc_id, 0)

        if failed > 0 and failure_rate > 0.3 and current_retries < 2:
            retry_needed.append(doc_id)
        elif failed > 0:
            for sig in failed_by_doc[doc_id]:
                passed_with_warnings.append(sig)

    return {
        "valid_signals": valid_signals,
        "retry_needed": retry_needed,
        "passed_with_warnings": passed_with_warnings,
    }

