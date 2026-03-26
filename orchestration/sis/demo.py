"""Streamlit demo for the SIS pipeline (Hyflux test data).

Run from repo root (use ``python -m`` when ``streamlit`` is not on PATH):
  python -m streamlit run orchestration/sis/demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    # Ensure `shared.*` and `orchestration.*` imports work under `streamlit run`.
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv()

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal, SISOutput
from shared.schemas.retrieval import TargetedRetrievalRequest
from shared.taxonomy import EventCategory, Severity

from orchestration.sis.nodes.extract import parallel_extract_signals
from orchestration.sis.nodes.validate import schema_validation_gate
from orchestration.sis.nodes.verify import parallel_verify_signals
from orchestration.sis.nodes.conflict import conflict_resolution
from orchestration.sis.nodes.evidence_gate import evidence_gate


def _hyflux_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "local" / "hyflux"


def _load_docs() -> List[DocumentInput]:
    root = _hyflux_root()
    docs: List[DocumentInput] = []
    for path in sorted(root.glob("doc_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        docs.append(DocumentInput.model_validate(payload))
    return docs


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _severity_color(sev: str) -> str:
    sev_norm = (sev or "").lower()
    if sev_norm == "high":
        return "#ff6666"
    if sev_norm == "medium":
        return "#ffb347"
    if sev_norm == "low":
        return "#ffea7a"
    if sev_norm == "positive":
        return "#7CFC98"
    return "#d9d9d9"


def _windowed_context(full_text: str, start: int, end: int, pad: int = 200) -> str:
    n = len(full_text)
    lo = max(0, start - pad)
    hi = min(n, end + pad)
    return full_text[lo:hi]


def _signals_from_extraction_results_cached(
    extraction_results_path: Path,
    docs: List[DocumentInput],
) -> List[Signal]:
    """Mirror the extraction->Signal mapping used by run_validation/run_verification."""
    full_text_to_doc: Dict[str, DocumentInput] = {d.full_text: d for d in docs}
    signals: List[Signal] = []
    records = _load_jsonl(extraction_results_path)
    for payload in records:
        text = payload.get("text", "") or ""
        doc = full_text_to_doc.get(text)
        if doc is None:
            continue
        for ex in payload.get("extractions", []):
            extraction_class = ex.get("extraction_class")
            attributes = ex.get("attributes", {}) or {}
            ci = ex.get("char_interval", {}) or {}
            event_type = EventCategory(extraction_class)
            severity = Severity(attributes["severity"])
            event_subtype = str(attributes["event_subtype"])

            char_interval = CharInterval(
                start=int(ci["start_pos"]),
                end=int(ci["end_pos"]),
            )
            evidence = Evidence(
                source_name=doc.source_name,
                document_id=doc.document_id,
                date=doc.published_date,
                snippet=str(ex.get("extraction_text", "")),
                char_interval=char_interval,
                source_quality=doc.source_quality_score,
            )
            signals.append(
                Signal(
                    signal_id=f"{doc.document_id}_{ex.get('extraction_index')}_{ex.get('group_index')}",
                    event_type=event_type,
                    event_subtype=event_subtype,
                    severity=severity,
                    confidence=1.0,
                    ambiguous=False,
                    evidence=[evidence],
                )
            )
    return signals


@st.cache_data(show_spinner=False)
def load_cached_bundle() -> Dict[str, Any]:
    root = _hyflux_root()

    docs = _load_docs()
    docs_by_id = {d.document_id: d for d in docs}

    extraction_path = root / "extraction_results.jsonl"
    validation_path = root / "validation_results.jsonl"
    verification_path = root / "verification_results.jsonl"
    conflict_path = root / "conflict_results.jsonl"
    sis_output_path = root / "sis_output.jsonl"

    signals_extracted = _signals_from_extraction_results_cached(extraction_path, docs)

    # Validation records: {signal_id, document_id, status}
    validation_records = _load_jsonl(validation_path)
    valid_ids = {r.get("signal_id") for r in validation_records if r.get("status") == "valid"}
    warning_ids = {r.get("signal_id") for r in validation_records if r.get("status") == "warning"}
    retry_doc_ids = sorted({str(r.get("document_id")) for r in validation_records if r.get("status") == "retry"})

    # Verification records: one JSONL per signal_id with confidence/decision.
    verification_records = _load_jsonl(verification_path)
    ver_by_sid = {r.get("signal_id"): r for r in verification_records}

    # Conflict results: first line summary; remaining lines are per-signal dicts.
    conflict_items = _load_jsonl(conflict_path)
    conflict_summary: Dict[str, Any] = {}
    conflict_signals: List[Dict[str, Any]] = []
    if conflict_items:
        if conflict_items[0].get("_conflict_summary"):
            conflict_summary = {k: conflict_items[0][k] for k in conflict_items[0] if k != "_conflict_summary"}
            conflict_signals = conflict_items[1:]
        else:
            conflict_signals = conflict_items

    # SIS output bundle (created by run_evidence_gate.py)
    sis_raw_lines = _load_jsonl(sis_output_path)
    sis_output_bundle = sis_raw_lines[0] if sis_raw_lines else {}
    sis_output = SISOutput.model_validate(sis_output_bundle.get("sis_output", {})) if sis_output_bundle else None
    retrieval_requests = [TargetedRetrievalRequest.model_validate(r) for r in sis_output_bundle.get("targeted_retrieval_requests", [])]

    return {
        "docs": docs,
        "docs_by_id": docs_by_id,
        "signals_extracted": signals_extracted,
        "validation_records": validation_records,
        "valid_ids": valid_ids,
        "warning_ids": warning_ids,
        "retry_doc_ids": retry_doc_ids,
        "verification_records": verification_records,
        "ver_by_sid": ver_by_sid,
        "conflict_summary": conflict_summary,
        "conflict_signals": conflict_signals,
        "sis_output": sis_output,
        "retrieval_requests": retrieval_requests,
    }


def _df_signals(signals: List[Signal]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for s in signals:
        src = s.evidence[0].source_name if s.evidence else ""
        rows.append(
            {
                "signal_id": s.signal_id,
                "event_type": s.event_type.value,
                "event_subtype": s.event_subtype,
                "severity": s.severity.value,
                "confidence": s.confidence,
                "source_name": src,
            }
        )
    return pd.DataFrame(rows)


def _df_verification_rows(verification_records: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build rows from ``parallel_verify_signals`` items (``signal`` key) or cached JSONL records."""
    rows: List[Dict[str, Any]] = []
    for r in verification_records:
        sig_obj = r.get("signal")
        if isinstance(sig_obj, Signal):
            sid = sig_obj.signal_id
            event_subtype = sig_obj.event_subtype
        else:
            sid = r.get("signal_id")
            event_subtype = r.get("event_subtype")
        rows.append(
            {
                "signal_id": sid,
                "event_subtype": event_subtype,
                "verification_decision": r.get("verification_decision"),
                "original_confidence": r.get("original_confidence"),
                "adjusted_confidence": r.get("adjusted_confidence"),
            }
        )
    return pd.DataFrame(rows)


def _display_stored_contradiction_explanations(
    explanations: List[Dict[str, Any]],
    signals: List[Signal],
    max_items: int = 6,
) -> None:
    """Show Gemini contradiction explanations from ``conflict_summary`` (no extra API calls)."""
    by_id = {s.signal_id: s for s in signals}
    for entry in (explanations or [])[:max_items]:
        sid_a = str(entry.get("signal_id_a", ""))
        sid_b = str(entry.get("signal_id_b", ""))
        expl = str(entry.get("explanation", ""))
        sa = by_id.get(sid_a)
        sb = by_id.get(sid_b)
        src_a = sa.evidence[0].source_name if sa and sa.evidence else ""
        src_b = sb.evidence[0].source_name if sb and sb.evidence else ""
        st.write(f"**Contradiction:** {sid_a} ({src_a}) <-> {sid_b} ({src_b})")
        st.write(f"Gemini explanation: {expl}")
        if sa and sa.evidence:
            st.code(f"A evidence: {sa.evidence[0].snippet}")
        if sb and sb.evidence:
            st.code(f"B evidence: {sb.evidence[0].snippet}")


def _format_disputed_examples(
    disputed_signals: List[Signal],
    max_pairs: int = 12,
) -> List[Tuple[Signal, Signal]]:
    """Pair up disputed signals from different documents for display."""
    pairs: List[Tuple[Signal, Signal]] = []
    n = len(disputed_signals)
    for i in range(n):
        for j in range(i + 1, n):
            sa = disputed_signals[i]
            sb = disputed_signals[j]
            da = sa.evidence[0].document_id if sa.evidence else ""
            db = sb.evidence[0].document_id if sb.evidence else ""
            if not da or not db or da == db:
                continue
            pairs.append((sa, sb))
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def _gemini_pair_explain(sa: Signal, sb: Signal) -> Dict[str, Any]:
    """Re-judge a disputed pair with Gemini to surface explanation for the demo."""
    # Local imports so cached mode doesn't require google-genai unless used.
    from google import genai  # type: ignore

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set; cannot run Gemini pair explanation.")

    # Use the existing conflict prompt builder & parser.
    from orchestration.sis.nodes import conflict as conflict_mod

    client = genai.Client(api_key=api_key)
    prompt = conflict_mod._build_pair_prompt(sa, sb)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw = conflict_mod._response_text(response)
    rel, expl = conflict_mod._parse_llm_json(raw)
    return {"relationship": rel, "explanation": expl}


def main() -> None:
    st.set_page_config(page_title="SIS Pipeline Demo", layout="wide")

    st.title("SIS Pipeline Demo - Credit Risk Signal Intelligence")
    st.write(
        "SIS extracts credit-relevant signals from unstructured documents, validates and verifies them with "
        "structured schemas, resolves cross-source conflicts, and gates evidence for FRD."
    )

    with st.sidebar:
        st.header("Tech Stack (per step)")
        st.markdown("- **Extraction:** LangExtract + Gemini 2.5 Flash")
        st.markdown("- **Validation:** Pydantic schema + deterministic evidence checks")
        st.markdown("- **Verification:** Gemini grounding verification")
        st.markdown("- **Conflict Resolution:** NLI (DeBERTa-v3) + Gemini semantic confirmation")
        st.markdown("- **Evidence Gate:** deterministic routing + flags (no RS calls yet)")

    mode = st.radio("Mode", ["Cached Results", "Live Run"], horizontal=True)
    run_clicked = st.button("Run Pipeline", type="primary")

    docs = _load_docs()

    with st.expander("Input documents (Hyflux test data)", expanded=True):
        for d in docs:
            st.subheader(f"{d.document_id} - {d.source_name}")
            st.caption(f"source_type={d.source_type.value} | source_quality_score={d.source_quality_score}")
            st.code(d.full_text[:300] + ("..." if len(d.full_text) > 300 else ""), language="text")

        st.info(
            "These are real historical articles from Hyflux's credit deterioration period (2018-2019). "
            "We use them to validate that the pipeline would have flagged early warning signals before the eventual collapse."
        )

    if not run_clicked:
        st.stop()

    # --- Live mode execution ---
    if mode == "Live Run":
        if not os.getenv("GEMINI_API_KEY"):
            st.error("GEMINI_API_KEY is not set. Cached mode can still run without it.")
            st.stop()
        try:
            import langextract  # noqa: F401
        except ModuleNotFoundError:
            st.error("langextract is not installed. Install with `pip install langextract` to run Live Run.")
            st.stop()

        # Step 1: Extraction
        t0 = time.perf_counter()
        with st.spinner("Step 1/5: Extraction (LangExtract + Gemini) ..."):
            signals_extracted = parallel_extract_signals(docs)
        t_extract = time.perf_counter() - t0

        with st.expander("Step 1: Extraction", expanded=True):
            st.metric("Signals extracted", len(signals_extracted))
            st.caption(f"Time taken: {t_extract:.1f}s")

            df = _df_signals(signals_extracted)
            if df.empty or "severity" not in df.columns:
                st.warning("No signals were extracted; showing an empty table.")
                st.dataframe(df, use_container_width=True)
            else:
                df["severity_color"] = df["severity"].apply(_severity_color)
                st.dataframe(df, use_container_width=True)

        # Step 2: Validation
        with st.spinner("Step 2/5: Validation (Pydantic) ..."):
            validation_result = schema_validation_gate(signals=signals_extracted, documents=docs)
        valid_signals = validation_result["valid_signals"]
        passed_with_warnings = validation_result["passed_with_warnings"]
        retry_needed = validation_result["retry_needed"]
        validated_signals = valid_signals + passed_with_warnings

        with st.expander("Step 2: Validation", expanded=True):
            valid_n = len(valid_signals)
            warn_n = len(passed_with_warnings)
            retry_n = len(retry_needed)
            total = valid_n + warn_n
            st.metric("Passed (valid)", f"{valid_n}/{total}")
            st.metric("Warnings", warn_n)
            st.metric("Retries needed", retry_n)
            if retry_needed:
                st.warning(f"Retry-needed doc_ids: {retry_needed}")

        # Step 3: Verification
        t0 = time.perf_counter()
        with st.spinner("Step 3/5: Verification (Gemini grounding) ..."):
            verification_results = parallel_verify_signals(
                signals=validated_signals,
                documents=docs,
                max_workers=10,
            )
        t_verify = time.perf_counter() - t0

        yes_n = sum(1 for r in verification_results if r.get("verification_decision") == "yes")
        partial_n = sum(1 for r in verification_results if r.get("verification_decision") == "partial")
        no_n = sum(1 for r in verification_results if r.get("verification_decision") == "no")
        err_n = sum(1 for r in verification_results if r.get("verification_decision") == "error")

        with st.expander("Step 3: Verification", expanded=True):
            st.caption(f"Time taken: {t_verify:.1f}s")
            st.metric("yes", yes_n)
            st.metric("partial", partial_n)
            st.metric("no", no_n)
            st.metric("error", err_n)

            df = _df_verification_rows(verification_results)
            st.dataframe(df, use_container_width=True)

            # Partial reasons
            docs_by_id = {d.document_id: d for d in docs}
            partial_results = [r for r in verification_results if r.get("verification_decision") == "partial"]
            for r in partial_results[:8]:
                sig = r.get("signal")
                if not isinstance(sig, Signal) or not sig.evidence:
                    continue
                sid = sig.signal_id
                ev = sig.evidence[0]
                doc = docs_by_id.get(ev.document_id)
                if not doc:
                    continue
                context = _windowed_context(doc.full_text, ev.char_interval.start, ev.char_interval.end)
                with st.expander(f"Why partial? {sid}", expanded=False):
                    st.write("Reason (demo heuristic): Gemini returned `partial`, and adjusted_confidence was reduced.")
                    st.write("Evidence snippet:")
                    st.code(ev.snippet)
                    st.write("Windowed context (+/- 200 chars):")
                    st.code(context)

        # Step 4: Conflict resolution
        t0 = time.perf_counter()
        with st.spinner("Step 4/5: Conflict Resolution (NLI + Gemini) ..."):
            resolved_items, conflict_summary = conflict_resolution(
                verification_items=verification_results,
                documents=docs,
                max_workers=10,
            )
        t_conflict = time.perf_counter() - t0

        resolved_signals = [it["signal"] for it in resolved_items]

        with st.expander("Step 4: Conflict Resolution", expanded=True):
            nli_screened = int(conflict_summary.get("nli_pairs_screened", 0))
            nli_candidates = int(conflict_summary.get("nli_contradictions_detected", 0))
            gemini_confirmed = int(conflict_summary.get("gemini_confirmed", 0))
            disputed_count = int(conflict_summary.get("disputed", 0))

            st.caption(f"Time taken: {t_conflict:.1f}s")
            st.metric("NLI screened pairs", nli_screened)
            st.metric("NLI candidates", nli_candidates)
            st.metric("Gemini confirmed contradictions", gemini_confirmed)
            st.metric("Disputed signals", disputed_count)

            disputed = [
                s
                for s in resolved_signals
                if str(s.conflict_status) == "ConflictStatus.disputed" or s.conflict_status.value == "disputed"
            ]
            explanations_live = conflict_summary.get("contradiction_explanations") or []
            if explanations_live:
                _display_stored_contradiction_explanations(
                    explanations_live,
                    resolved_signals,
                    max_items=6,
                )
            elif disputed:
                st.write(
                    "Disputed signals are present but no Gemini contradiction explanations were stored "
                    "in conflict_summary (unexpected for a normal run)."
                )
            else:
                st.write("No disputed signals detected.")

        # Step 5: Evidence gate
        with st.spinner("Step 5/5: Evidence Gate (deterministic flags) ..."):
            sis_output, retrieval_requests = evidence_gate(resolved_signals, docs)

        with st.expander("Step 5: Evidence Gate", expanded=True):
            meta = sis_output.metadata
            st.metric("auto_verified", meta.signals_auto_verified)
            st.metric("ambiguous", meta.signals_ambiguous)
            st.metric("rejected", meta.signals_rejected)

            df = pd.DataFrame(
                [
                    {
                        "signal_id": s.signal_id,
                        "event_type": s.event_type.value,
                        "event_subtype": s.event_subtype,
                        "severity": s.severity.value,
                        "confidence": s.confidence,
                        "conflict_status": s.conflict_status.value,
                        "evidence_route": s.evidence_route,
                        "evidence_notes": ",".join(s.evidence_notes),
                        "source": s.evidence[0].source_name if s.evidence else "",
                    }
                    for s in sis_output.signals
                ]
            )
            st.dataframe(df, use_container_width=True)

            if retrieval_requests:
                st.warning(f"{len(retrieval_requests)} targeted retrieval requests were generated (RS placeholder).")
                for req in retrieval_requests[:5]:
                    st.write(
                        f"[RETRIEVAL_NEEDED] company={req.company_id}, keywords={req.keywords}, target_sources={req.target_source_types}"
                    )
                    st.write(req.signal_context)

        with st.expander("Final SIS Output (SISOutput JSON)", expanded=False):
            st.json(sis_output.model_dump(mode="json"))

        st.success(
            f"Pipeline processed {len(docs)} documents -> extracted {len(sis_output.signals)} signals -> "
            f"{meta.signals_auto_verified} auto_verified, {meta.signals_ambiguous} ambiguous, {meta.signals_rejected} rejected. "
            "Ready for FRD."
        )

    else:
        # --- Cached mode execution (no API calls) ---
        cache = load_cached_bundle()
        docs = cache["docs"]
        signals_extracted = cache["signals_extracted"]
        docs_by_id = cache["docs_by_id"]
        verification_records = cache["verification_records"]
        ver_by_sid = cache["ver_by_sid"]
        conflict_summary = cache["conflict_summary"]
        conflict_signals_raw = cache["conflict_signals"]
        sis_output: Optional[SISOutput] = cache["sis_output"]
        retrieval_requests: List[TargetedRetrievalRequest] = cache["retrieval_requests"]

        signals_by_id = {s.signal_id: s for s in signals_extracted}

        # Step 1
        with st.expander("Step 1: Extraction", expanded=True):
            st.metric("Signals extracted", len(signals_extracted))
            st.caption("Time taken: cached")
            df = _df_signals(signals_extracted)
            st.dataframe(df, use_container_width=True)

        # Step 2 validation
        valid_ids = cache["valid_ids"]
        warning_ids = cache["warning_ids"]
        retry_doc_ids = cache["retry_doc_ids"]
        total = len(valid_ids) + len(warning_ids)
        with st.expander("Step 2: Validation", expanded=True):
            st.metric("Passed (valid)", f"{len(valid_ids)}/{total}")
            st.metric("Warnings", len(warning_ids))
            st.metric("Retries needed", len(retry_doc_ids))

        # Step 3 verification
        yes_n = sum(1 for r in verification_records if r.get("verification_decision") == "yes")
        partial_n = sum(1 for r in verification_records if r.get("verification_decision") == "partial")
        no_n = sum(1 for r in verification_records if r.get("verification_decision") == "no")
        err_n = sum(1 for r in verification_records if r.get("verification_decision") == "error")

        with st.expander("Step 3: Verification", expanded=True):
            st.metric("yes", yes_n)
            st.metric("partial", partial_n)
            st.metric("no", no_n)
            st.metric("error", err_n)

            df = _df_verification_rows(verification_records)
            st.dataframe(df, use_container_width=True)

            partial_results = [r for r in verification_records if r.get("verification_decision") == "partial"]
            for r in partial_results[:6]:
                sid = r.get("signal_id")
                sig = signals_by_id.get(sid)
                if not sig or not sig.evidence:
                    continue
                ev = sig.evidence[0]
                doc = docs_by_id.get(ev.document_id)
                if not doc:
                    continue
                context = _windowed_context(doc.full_text, ev.char_interval.start, ev.char_interval.end)
                with st.expander(f"Why partial? {sid}", expanded=False):
                    st.write("Reason (demo heuristic): cached verification shows `partial`; adjusted_confidence was halved.")
                    st.write("Evidence snippet:")
                    st.code(ev.snippet)
                    st.write("Windowed context (+/- 200 chars):")
                    st.code(context)

        # Step 4 conflict
        with st.expander("Step 4: Conflict Resolution", expanded=True):
            nli_screened = int(conflict_summary.get("nli_pairs_screened", 0))
            nli_candidates = int(conflict_summary.get("nli_contradictions_detected", 0))
            gemini_confirmed = int(conflict_summary.get("gemini_confirmed", 0))
            disputed_count = int(conflict_summary.get("disputed", 0))

            st.metric("NLI screened pairs", nli_screened)
            st.metric("NLI candidates", nli_candidates)
            st.metric("Gemini confirmed contradictions", gemini_confirmed)
            st.metric("Disputed signals", disputed_count)

            conflict_signals: List[Signal] = []
            for it in conflict_signals_raw:
                sig = Signal.model_validate(it["signal"])
                conflict_signals.append(sig)
            disputed = [s for s in conflict_signals if s.conflict_status.value == "disputed"]

            explanations_cached = conflict_summary.get("contradiction_explanations") or []
            if explanations_cached:
                _display_stored_contradiction_explanations(
                    explanations_cached,
                    conflict_signals,
                    max_items=6,
                )
            elif disputed:
                pairs = _format_disputed_examples(disputed, max_pairs=8)
                for sa, sb in pairs[:6]:
                    src_a = sa.evidence[0].source_name if sa.evidence else ""
                    src_b = sb.evidence[0].source_name if sb.evidence else ""
                    st.write(
                        f"**Disputed evidence pair (cached):** {sa.signal_id} ({src_a}) <-> {sb.signal_id} ({src_b})"
                    )
                    try:
                        judgment = _gemini_pair_explain(sa, sb)
                    except Exception as e:
                        st.write(f"Gemini explanation fallback failed: {e!r}")
                        st.code(f"A evidence: {sa.evidence[0].snippet if sa.evidence else ''}")
                        st.code(f"B evidence: {sb.evidence[0].snippet if sb.evidence else ''}")
                        continue
                    st.write(f"Gemini explanation: {judgment.get('explanation', '')}")
                    st.code(f"A evidence: {sa.evidence[0].snippet if sa.evidence else ''}")
                    st.code(f"B evidence: {sb.evidence[0].snippet if sb.evidence else ''}")
            else:
                st.write("No disputed signals detected.")

        # Step 5 evidence gate + final output
        with st.expander("Step 5: Evidence Gate", expanded=True):
            if not sis_output:
                st.error("sis_output.jsonl not found or invalid.")
            else:
                meta = sis_output.metadata
                st.metric("auto_verified", meta.signals_auto_verified)
                st.metric("ambiguous", meta.signals_ambiguous)
                st.metric("rejected", meta.signals_rejected)

                df = pd.DataFrame(
                    [
                        {
                            "signal_id": s.signal_id,
                            "event_type": s.event_type.value,
                            "event_subtype": s.event_subtype,
                            "severity": s.severity.value,
                            "confidence": s.confidence,
                            "conflict_status": s.conflict_status.value,
                            "evidence_route": s.evidence_route,
                            "evidence_notes": ",".join(s.evidence_notes),
                            "source": s.evidence[0].source_name if s.evidence else "",
                        }
                        for s in sis_output.signals
                    ]
                )
                st.dataframe(df, use_container_width=True)

                if retrieval_requests:
                    st.warning(f"{len(retrieval_requests)} targeted retrieval requests were generated (RS placeholder).")
                    for req in retrieval_requests[:5]:
                        st.write(
                            f"[RETRIEVAL_NEEDED] company={req.company_id}, keywords={req.keywords}, target_sources={req.target_source_types}"
                        )
                        st.write(req.signal_context)

        with st.expander("Final SIS Output (SISOutput JSON)", expanded=False):
            if sis_output:
                st.json(sis_output.model_dump(mode="json"))

        if sis_output:
            meta = sis_output.metadata
            st.success(
                f"Pipeline processed {len(docs)} documents -> extracted {len(sis_output.signals)} signals -> "
                f"{meta.signals_auto_verified} auto_verified, {meta.signals_ambiguous} ambiguous, {meta.signals_rejected} rejected. "
                "Ready for FRD."
            )


if __name__ == "__main__":
    main()

