"""SIS verification node (Phase 3).

Uses Gemini to verify that extracted signals are grounded in the source text
and that their description is faithful to the underlying evidence.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from dotenv import load_dotenv

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal


_tls = threading.local()


def _require_gemini_api_key() -> None:
    """Fail fast if verification cannot authenticate (same env pattern as extraction)."""

    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("Missing GEMINI_API_KEY in environment/.env for verification.")


def _thread_verify_client() -> Any:
    """One ``google.genai`` client per worker thread (avoids shared-client issues)."""

    c = getattr(_tls, "client", None)
    if c is not None:
        return c
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment/.env for verification.")
    try:
        from google import genai  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "google-genai is not installed. Install it with `pip install google-genai`."
        ) from exc
    _tls.client = genai.Client(api_key=api_key)
    return _tls.client


def _response_text(response: Any) -> str:
    t = getattr(response, "text", None)
    if t:
        return str(t)
    cands = getattr(response, "candidates", None) or []
    for cand in cands:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not parts:
            continue
        chunks: List[str] = []
        for p in parts:
            txt = getattr(p, "text", None)
            if txt:
                chunks.append(str(txt))
        if chunks:
            return "".join(chunks)
    return ""


_CONTEXT_PAD_CHARS = 200


def _windowed_source_context(full_text: str, start: int, end: int, pad: int = _CONTEXT_PAD_CHARS) -> str:
    """Return ``full_text[start:end]`` expanded by ``pad`` chars on each side, clamped to bounds."""
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
    """Run Gemini verification for a single signal (thread-local client per worker)."""
    decision = "error"
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
    except Exception:  # pragma: no cover - defensive
        source_context = primary_ev.snippet

    prompt = _build_verification_prompt(
        original_text=source_context,
        snippet=primary_ev.snippet,
        event_type=signal.event_type.value,
        event_subtype=signal.event_subtype,
        severity=signal.severity.value,
    )

    try:
        client = _thread_verify_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0},
        )
        text = _response_text(response) or ""
    except Exception as exc:  # pragma: no cover - network/LLM errors
        print(f"[parallel_verify_signals] Gemini call failed for {signal.signal_id}: {exc!r}")
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
        f"[parallel_verify_signals] {signal.signal_id} -> "
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
    """Verify extracted signals against source-grounding evidence using Gemini.

    Runs up to ``max_workers`` concurrent Gemini calls (suitable for Paid Tier 1).

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
    _require_gemini_api_key()

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
