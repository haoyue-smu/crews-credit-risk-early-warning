"""SIS extraction node.

Extracts credit-relevant signals from documents using OpenRouter (via OpenAI SDK).
Each document gets one chat.completions call; char intervals are located with str.find().
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from shared.llm import get_client, MODEL_SIS
from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity

from orchestration.sis.prompts.templates import EXTRACTION_PROMPT

_EXTRACTION_TEMPERATURE = 0

_FORMAT_INSTRUCTIONS = (
    "\n\nReturn a JSON object with a single key \"extractions\" containing an array. "
    "Each element must have exactly these keys:\n"
    "- \"event_type\": one of the allowed EventCategory values\n"
    "- \"event_subtype\": a concise snake_case label\n"
    "- \"severity\": exactly one of: low, medium, high, positive\n"
    "- \"extraction_text\": the exact verbatim span copied from the input text\n\n"
    "If no relevant signals are found, return {\"extractions\": []}."
)


def _extract_one(doc: DocumentInput, client) -> list[Signal]:
    """Run LLM extraction for a single document and return Signal instances."""
    system_prompt = EXTRACTION_PROMPT + _FORMAT_INSTRUCTIONS
    user_prompt = f"Extract credit-relevant signals from this text:\n\n{doc.full_text}"

    response = client.chat.completions.create(
        model=MODEL_SIS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=_EXTRACTION_TEMPERATURE,
    )
    data = json.loads(response.choices[0].message.content)

    signals: list[Signal] = []
    for idx, ex in enumerate(data.get("extractions", [])):
        if not isinstance(ex, dict):
            continue

        extraction_text = str(ex.get("extraction_text", ""))
        try:
            event_type = EventCategory(str(ex.get("event_type", "")))
            severity = Severity(str(ex.get("severity", "")))
        except Exception:
            continue

        # Find char interval in the source text (exact match first, then case-insensitive)
        start = doc.full_text.find(extraction_text)
        if start == -1:
            start = doc.full_text.lower().find(extraction_text.lower())
        if start == -1:
            continue  # Cannot locate span — skip rather than fabricate positions

        evidence = Evidence(
            source_name=doc.source_name,
            document_id=doc.document_id,
            date=doc.published_date,
            snippet=extraction_text,
            char_interval=CharInterval(start=start, end=start + len(extraction_text)),
            source_quality=doc.source_quality_score,
        )
        signals.append(Signal(
            signal_id=f"{doc.document_id}_{idx}",
            event_type=event_type,
            event_subtype=str(ex.get("event_subtype", "")),
            severity=severity,
            confidence=1.0,
            ambiguous=False,
            evidence=[evidence],
        ))

    return signals


def parallel_extract_signals(
    documents: list[DocumentInput],
    max_workers: int = 10,
) -> list[Signal]:
    """Extract signals from all documents using parallel OpenRouter calls.

    Args:
        documents: Documents produced by the RS subgraph.
        max_workers: Max concurrent LLM calls (suitable for paid-tier rate limits).

    Returns:
        Extracted raw signals with evidence and char intervals.
    """
    client = get_client()

    if len(documents) <= 1 or max_workers == 1:
        all_signals: list[Signal] = []
        for doc in documents:
            try:
                all_signals.extend(_extract_one(doc, client))
            except Exception as exc:
                print(f"[extract] Failed on {doc.document_id}: {exc!r}")
        return all_signals

    all_signals = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_doc = {
            executor.submit(_extract_one, doc, client): doc
            for doc in documents
        }
        for fut in as_completed(future_to_doc):
            doc = future_to_doc[fut]
            try:
                all_signals.extend(fut.result())
            except Exception as exc:
                print(f"[extract] Failed on {doc.document_id}: {exc!r}")

    return all_signals
