"""SIS extraction node (Phase 2).

Extracts credit-relevant signals from SQ-produced documents using LangExtract + Gemini.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity

EXTRACTION_TEMPERATURE = 0


def _extractions_from_lx_result(result: Any) -> list[Any]:
    """Best-effort discovery of the extractions list from a LangExtract result."""
    if result is None:
        return []
    if isinstance(result, dict):
        if isinstance(result.get("extractions"), list):
            return result["extractions"]
        for v in result.values():
            found = _extractions_from_lx_result(v)
            if found:
                return found
    if hasattr(result, "extractions") and isinstance(getattr(result, "extractions"), list):
        return list(result.extractions)
    if isinstance(result, list):
        for item in result:
            found = _extractions_from_lx_result(item)
            if found:
                return found
    return []


def _signals_from_lx_result(doc: DocumentInput, result: Any) -> list[Signal]:
    """Map LangExtract output for one document to ``Signal`` instances."""
    signals: list[Signal] = []
    for ex in _extractions_from_lx_result(result):
        # LangExtract may return each extraction either as a plain dict
        # (when using JSON-serialized outputs) or as an Extraction(...) object
        # (when using in-memory results from `lx.extract`).
        if isinstance(ex, dict):
            extraction_class = ex.get("extraction_class")
            attributes = ex.get("attributes", {}) or {}
            ci = ex.get("char_interval", {}) or {}
            extraction_text = ex.get("extraction_text", "") or ""
            extraction_index = ex.get("extraction_index")
            group_index = ex.get("group_index")
            start_pos = ci.get("start_pos")
            end_pos = ci.get("end_pos")
        else:
            extraction_class = getattr(ex, "extraction_class", None)
            attributes = getattr(ex, "attributes", {}) or {}
            extraction_text = getattr(ex, "extraction_text", "") or ""
            extraction_index = getattr(ex, "extraction_index", None)
            group_index = getattr(ex, "group_index", None)
            char_interval_obj = getattr(ex, "char_interval", None)
            start_pos = getattr(char_interval_obj, "start_pos", None) if char_interval_obj is not None else None
            end_pos = getattr(char_interval_obj, "end_pos", None) if char_interval_obj is not None else None

        if extraction_class is None:
            continue

        try:
            event_type = EventCategory(str(extraction_class))
            severity = Severity(attributes["severity"])
        except Exception:
            continue

        event_subtype = str(attributes.get("event_subtype", ""))

        try:
            char_interval = CharInterval(
                start=int(start_pos),
                end=int(end_pos),
            )
        except Exception:
            continue

        evidence = Evidence(
            source_name=doc.source_name,
            document_id=doc.document_id,
            date=doc.published_date,
            snippet=str(extraction_text),
            char_interval=char_interval,
            source_quality=doc.source_quality_score,
        )

        signals.append(
            Signal(
                signal_id=f"{doc.document_id}_{extraction_index}_{group_index}",
                event_type=event_type,
                event_subtype=event_subtype,
                severity=severity,
                confidence=1.0,
                ambiguous=False,
                evidence=[evidence],
            )
        )
    return signals


def parallel_extract_signals(documents: list[DocumentInput]) -> list[Signal]:
    """Extract signals from documents (parallelized LLM extraction).

    Uses Gemini Paid Tier 1–friendly settings: ``extraction_passes=1``,
    ``max_workers=10`` per LangExtract call (no artificial throttling).

    Args:
        documents: Documents produced by SQ for a single company or batch.

    Returns:
        Extracted raw signals with traceability and evidence.
    """
    try:
        import langextract as lx  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "langextract is not installed. Install with `pip install langextract`."
        ) from exc

    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment/.env for extraction.")

    os.environ["LANGEXTRACT_API_KEY"] = gemini_api_key

    from orchestration.sis.prompts.examples import get_sis_example_data
    from orchestration.sis.prompts.templates import EXTRACTION_PROMPT

    examples = get_sis_example_data()
    all_signals: list[Signal] = []

    for doc in documents:
        extract_kwargs = dict(
            text_or_documents=doc.full_text,
            prompt_description=EXTRACTION_PROMPT,
            examples=examples,
            model_id="gemini-2.5-flash",
            extraction_passes=1,
            max_workers=10,
        )
        try:
            # Preferred for LangExtract versions that forward Gemini generation config.
            result = lx.extract(
                **extract_kwargs,
                generation_config={"temperature": EXTRACTION_TEMPERATURE},
            )
        except TypeError:
            try:
                # Some versions may accept direct `temperature`.
                result = lx.extract(
                    **extract_kwargs,
                    temperature=EXTRACTION_TEMPERATURE,
                )
            except TypeError:
                # Backward-compatible fallback if temperature kwargs are unsupported.
                result = lx.extract(**extract_kwargs)
        all_signals.extend(_signals_from_lx_result(doc, result))

    return all_signals
