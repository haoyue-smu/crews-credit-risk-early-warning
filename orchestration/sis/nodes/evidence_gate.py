"""SIS evidence_gate node (Phase 3/4).

Evaluates evidence strength after conflict_resolution, sets routing hints and notes,
builds optional TargetedRetrievalRequest objects (RS not wired — logged only).

Scheme A: no signals are dropped; all are included in SISOutput for FRD.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from shared.schemas.documents import DocumentInput, SourceType
from shared.schemas.retrieval import TargetedRetrievalRequest
from shared.schemas.signals import ConflictStatus, ResolutionPath, SISMetadata, SISOutput, Signal
from shared.taxonomy import Severity


def _docs_by_id(documents: List[DocumentInput]) -> Dict[str, DocumentInput]:
    return {d.document_id: d for d in documents}


def _company_id_from_documents(documents: List[DocumentInput]) -> str:
    if not documents:
        return "unknown"
    return documents[0].company_id


def _documents_touched_by_signals(signals: List[Signal]) -> int:
    ids: set[str] = set()
    for sig in signals:
        for ev in sig.evidence:
            ids.add(ev.document_id)
    return len(ids)


def _infer_target_source_types(primary_source_value: str) -> List[str]:
    """Suggest source types to fetch when current primary evidence is thin or narrow."""
    p = (primary_source_value or "").lower()
    if p == SourceType.forum.value:
        return ["news", "filing"]
    if p == SourceType.social.value:
        return ["news", "filing", "web"]
    if p == SourceType.web.value:
        return ["news", "filing"]
    if p == SourceType.news.value:
        return ["filing", "web"]
    if p == SourceType.filing.value:
        return ["news", "web"]
    return ["news", "filing", "web"]


def _keywords_from_signal(sig: Signal) -> List[str]:
    """Derive search keywords from subtype + evidence snippet (deduped, stable order)."""
    raw = sig.event_subtype.replace("-", "_")
    parts = [p.lower() for p in raw.split("_") if len(p) > 2]
    snippet = sig.evidence[0].snippet if sig.evidence else ""
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", snippet)
    extra = [w.lower() for w in words[:10]]
    out: List[str] = []
    seen: set[str] = set()
    for k in parts + extra:
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    if not out:
        out = [sig.event_subtype.lower() if sig.event_subtype else "credit_risk"]
    return out[:15]


def _build_retrieval_request(
    sig: Signal,
    company_id: str,
    docs_by_id: Dict[str, DocumentInput],
) -> TargetedRetrievalRequest:
    primary_st = "unknown"
    if sig.evidence:
        doc = docs_by_id.get(sig.evidence[0].document_id)
        if doc is not None:
            primary_st = doc.source_type.value
    targets = _infer_target_source_types(primary_st)
    kws = _keywords_from_signal(sig)
    ctx = (
        f"signal_id={sig.signal_id}; high-severity '{sig.event_subtype}' "
        f"({sig.event_type.value}) with confidence {sig.confidence:.2f}; "
        f"primary_evidence_source_type={primary_st}; seek corroboration."
    )
    return TargetedRetrievalRequest(
        company_id=company_id,
        keywords=kws,
        target_source_types=targets,
        signal_context=ctx,
    )


def evidence_gate(
    signals: List[Signal],
    documents: List[DocumentInput],
) -> Tuple[SISOutput, List[TargetedRetrievalRequest]]:
    """Apply evidence strength policy and build FRD payload + optional retrieval intents.

    Args:
        signals: Output of conflict_resolution (mutated in place with route/notes).
        documents: Source documents (company_id, source_type for retrieval hints).

    Returns:
        (``SISOutput``, list of ``TargetedRetrievalRequest`` — not sent until RS exists).
    """
    company_id = _company_id_from_documents(documents)
    docs_by_id = _docs_by_id(documents)
    retrieval_requests: List[TargetedRetrievalRequest] = []

    for sig in signals:
        notes: List[str] = list(sig.evidence_notes)
        conf = float(sig.confidence)
        amb_in = sig.ambiguous
        cs = sig.conflict_status
        ev_empty = len(sig.evidence) == 0

        sig.resolution_path = ResolutionPath.auto

        def append_high_sev_retrieval() -> None:
            """Rule 5: high severity + confidence < 0.5 → retrieval intent (RS placeholder)."""
            if sig.severity != Severity.high or conf >= 0.5:
                return
            if cs == ConflictStatus.disputed:
                return
            req = _build_retrieval_request(sig, company_id, docs_by_id)
            retrieval_requests.append(req)
            if "high_severity_low_confidence" not in notes:
                notes.append("high_severity_low_confidence")
            sig.evidence_route = "targeted_retrieval"

        # Rule 4: disputed — FRD direct only; no targeted_retrieval queue.
        if cs == ConflictStatus.disputed:
            sig.evidence_route = "frd_direct"
            sig.ambiguous = True
            if "disputed_sources" not in notes:
                notes.append("disputed_sources")
            sig.evidence_notes = notes
            continue

        # Rule 3: weak evidence
        if conf < 0.4 or ev_empty:
            sig.evidence_route = "frd_direct"
            sig.ambiguous = True
            if "weak_evidence" not in notes:
                notes.append("weak_evidence")
            append_high_sev_retrieval()
            sig.evidence_notes = notes
            continue

        # Rule 1: strong
        if conf >= 0.7 and not amb_in:
            sig.evidence_route = "frd_direct"
            sig.ambiguous = False
            sig.evidence_notes = notes
            continue

        # Rule 2: moderate
        if (0.4 <= conf < 0.7) or (cs == ConflictStatus.resolved):
            sig.evidence_route = "frd_direct"
            if not sig.ambiguous:
                sig.ambiguous = True
            append_high_sev_retrieval()
            sig.evidence_notes = notes
            continue

        # Fallback (e.g. high confidence but already ambiguous)
        sig.evidence_route = "frd_direct"
        sig.ambiguous = True
        append_high_sev_retrieval()
        sig.evidence_notes = notes

    for req in retrieval_requests:
        print(
            f"[RETRIEVAL_NEEDED] company={req.company_id}, keywords={req.keywords}, "
            f"target_sources={req.target_source_types}, context={req.signal_context}"
        )

    now = datetime.now(timezone.utc)
    auto_verified = sum(1 for s in signals if s.confidence >= 0.7 and not s.ambiguous)
    ambiguous_n = sum(1 for s in signals if s.ambiguous)

    metadata = SISMetadata(
        documents_processed=max(_documents_touched_by_signals(signals), len(documents)),
        signals_extracted=len(signals),
        signals_auto_verified=auto_verified,
        signals_ambiguous=ambiguous_n,
        signals_pending_review=0,
        signals_rejected=0,
        timestamp=now,
    )

    output = SISOutput(
        company_id=company_id,
        signals=signals,
        metadata=metadata,
    )
    return output, retrieval_requests
