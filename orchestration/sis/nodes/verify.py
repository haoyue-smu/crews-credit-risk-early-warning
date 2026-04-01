"""SIS verification node.

Verifies that extracted signals are grounded in their source documents.
Uses OpenRouter (via OpenAI SDK) with per-thread clients for ThreadPoolExecutor safety.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from openai import OpenAI

from shared.llm import get_client, MODEL_SIS
from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal

_tls = threading.local()


def _thread_openai_client() -> OpenAI:
    """One OpenAI client per worker thread."""
    c = getattr(_tls, "client", None)
    if c is not None:
        return c
    _tls.client = get_client()
    return _tls.client


_CONTEXT_PAD_CHARS = 200


def _windowed_source_context(full_text: str, start: int, end: int, pad: int = _CONTEXT_PAD_CHARS) -> str:
    """Return full_text[start:end] expanded by pad chars on each side, clamped to bounds."""
    n = len(full_text)
    lo = max(0, start - pad)
    hi = min(n, end + pad)
    return full_text[lo:hi]


def _build_verification_prompt(
    original_text: str,
    snippet: str,
    event_type: str,
    event_subtype: str,
    severity: str,
) -> str:
    """Construct a focused verification prompt.

    ``original_text`` should be the windowed passage (char_interval ± padding), not the bare span.
    """
    return (
        "You are verifying whether a structured credit-risk signal is grounded in the source document.\n\n"
        "SOURCE CONTEXT (document excerpt; the grounded span lies within this window; "
        "it may be shorter than the full passage shown):\n"
        f"{original_text}\n\n"
        "STRUCTURED SIGNAL (to verify):\n"
        f"- event_type: {event_type}\n"
        f"- event_subtype: {event_subtype}\n"
        f"- severity: {severity}\n"
        f"- evidence_snippet (extracted span, may be a fragment): {snippet!r}\n\n"
        "Decision criteria — choose exactly one:\n"
        "- yes: The signal's event_type, event_subtype, and severity are all directly and "
        "unambiguously supported by the source context. The evidence_snippet fairly represents "
        "what the text asserts.\n"
        "- partial: The signal is directionally correct but the source is broader, more nuanced, "
        "hedged, or the severity is debatable. Also choose partial if the evidence_snippet is only "
        "a small fragment of a longer statement and full support requires the surrounding context "
        "in ways that make the label or severity uncertain.\n"
        "- no: The signal is not supported, is contradicted by the source context, or describes a "
        "claim the source does not actually make (including over-specific or inverted meaning).\n\n"
        "Respond with JSON only: a single object with one key \"decision\" whose value is one of "
        "\"yes\", \"partial\", or \"no\" (lowercase)."
    )


def _verify_one_signal(
    signal: Signal,
    documents_by_id: Dict[str, DocumentInput],
) -> Dict[str, Any]:
    """Run LLM verification for a single signal (thread-local client per worker)."""
    original_confidence = float(signal.confidence)
    adjusted_confidence = original_confidence

    if not signal.evidence:
        return {
            "signal": signal,
            "verification_decision": "no_evidence",
            "original_confidence": original_confidence,
            "adjusted_confidence": adjusted_confidence,
        }

    primary_ev = signal.evidence[0]
    doc = documents_by_id.get(primary_ev.document_id)
    if doc is None:
        return {
            "signal": signal,
            "verification_decision": "document_not_found",
            "original_confidence": original_confidence,
            "adjusted_confidence": adjusted_confidence,
        }

    ci = primary_ev.char_interval
    try:
        source_context = _windowed_source_context(doc.full_text, ci.start, ci.end)
    except Exception:
        source_context = primary_ev.snippet

    prompt = _build_verification_prompt(
        original_text=source_context,
        snippet=primary_ev.snippet,
        event_type=signal.event_type.value,
        event_subtype=signal.event_subtype,
        severity=signal.severity.value,
    )

    try:
        client = _thread_openai_client()
        response = client.chat.completions.create(
            model=MODEL_SIS,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = response.choices[0].message.content or ""
    except Exception as exc:
        print(f"[verify] LLM call failed for {signal.signal_id}: {exc!r}")
        return {
            "signal": signal,
            "verification_decision": "error",
            "original_confidence": original_confidence,
            "adjusted_confidence": adjusted_confidence,
        }

    decision = "partial"
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and isinstance(payload.get("decision"), str):
            decision = payload["decision"].strip().lower()
    except Exception:
        lowered = text.lower()
        if " no" in lowered or lowered.startswith("no"):
            decision = "no"
        elif "yes" in lowered:
            decision = "yes"
        else:
            decision = "partial"

    if decision == "partial":
        adjusted_confidence *= 0.5
    elif decision == "no":
        adjusted_confidence *= 0.2

    print(
        f"[verify] {signal.signal_id} -> "
        f"decision={decision}, confidence={adjusted_confidence:.2f}"
    )

    return {
        "signal": signal,
        "verification_decision": decision,
        "original_confidence": original_confidence,
        "adjusted_confidence": adjusted_confidence,
    }


def parallel_verify_signals(
    signals: List[Signal],
    documents: List[DocumentInput],
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    """Verify extracted signals against source-grounding evidence via OpenRouter.

    Args:
        signals: Signals produced by the extraction + validation steps.
        documents: Original documents used for grounding.
        max_workers: Maximum concurrent verification requests.

    Returns:
        A list of dicts with:
        - ``signal``: the original Signal instance
        - ``verification_decision``: one of "yes", "partial", "no", or "error"
        - ``adjusted_confidence``: float confidence after verification
    """
    documents_by_id: Dict[str, DocumentInput] = {d.document_id: d for d in documents}

    if max_workers < 1:
        max_workers = 1

    if len(signals) <= 1 or max_workers == 1:
        return [_verify_one_signal(s, documents_by_id) for s in signals]

    results_by_index: Dict[int, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_verify_one_signal, sig, documents_by_id): i
            for i, sig in enumerate(signals)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            results_by_index[idx] = fut.result()

    return [results_by_index[i] for i in range(len(signals))]
