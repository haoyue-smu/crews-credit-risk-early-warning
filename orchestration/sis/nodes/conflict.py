"""SIS conflict resolution node (Phase 3).

Stage 1: deterministic cross-document merge for identical event_subtype (no ML).
Stage 2: CrossEncoder NLI screens all cross-document snippet pairs (local, batched).
Stage 3: LLM confirms NLI candidates via ``_build_pair_prompt`` (OpenRouter/OpenAI SDK).
"""

from __future__ import annotations

import json
import re

import numpy as np
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from shared.llm import get_client, MODEL_SIS
from shared.schemas.documents import DocumentInput
from shared.schemas.signals import ConflictStatus, Evidence, Signal
from shared.taxonomy import EventCategory, Severity

NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"
# Logits order: contradiction (0), entailment (1), neutral (2) for this checkpoint.
NLI_CONTRADICTION_INDEX = 0

# Cap evidence items per signal to prevent O(n) growth during merging/resolution.
MAX_EVIDENCE_PER_SIGNAL: int = 5


def _load_cross_encoder():
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "sentence-transformers is not installed. Install with: pip install sentence-transformers"
        ) from exc
    return CrossEncoder(NLI_MODEL_NAME)


def _company_id_for_signal(signal: Signal, docs_by_id: Dict[str, DocumentInput]) -> Optional[str]:
    if not signal.evidence:
        return None
    doc = docs_by_id.get(signal.evidence[0].document_id)
    return doc.company_id if doc else None


def _primary_document_id(signal: Signal) -> Optional[str]:
    if not signal.evidence:
        return None
    return signal.evidence[0].document_id


def _primary_evidence_snippet(signal: Signal) -> str:
    if not signal.evidence:
        return ""
    return str(signal.evidence[0].snippet or "")


def _primary_source_quality(signal: Signal) -> float:
    if not signal.evidence:
        return 0.0
    return float(signal.evidence[0].source_quality)


def _merge_signal_group(signals: List[Signal]) -> Signal:
    """Merge multiple signals into one: combined evidence, max confidence, resolved."""
    if len(signals) == 1:
        out = signals[0].model_copy(deep=True)
        out.conflict_status = ConflictStatus.resolved
        out.ambiguous = False
        return out

    base = max(signals, key=lambda s: s.confidence)
    ev_map: Dict[Tuple[str, int, int], Evidence] = {}
    for s in signals:
        for e in s.evidence:
            key = (e.document_id, e.char_interval.start, e.char_interval.end)
            ev_map.setdefault(key, e)

    ids = sorted({s.signal_id for s in signals})
    new_id = "merged_" + "_".join(ids)[:180]
    merged = base.model_copy(deep=True)
    merged.signal_id = new_id
    merged.evidence = list(ev_map.values())[:MAX_EVIDENCE_PER_SIGNAL]
    merged.confidence = max(s.confidence for s in signals)
    merged.conflict_status = ConflictStatus.resolved
    merged.ambiguous = False
    return merged


def _merge_item_group(items: List[Dict[str, Any]], signals: List[Signal]) -> Dict[str, Any]:
    """Merge verification-item dicts for a group of signals (same structure as input)."""
    merged_sig = _merge_signal_group(signals)
    base_item = max(items, key=lambda it: float(it.get("adjusted_confidence", 0.0)))
    out = {
        "signal": merged_sig,
        "verification_decision": base_item.get("verification_decision", "skipped"),
        "adjusted_confidence": max(float(it.get("adjusted_confidence", 0.0)) for it in items),
        "original_confidence": max(float(it.get("original_confidence", 0.0)) for it in items),
    }
    return out


def _stage1_cross_doc_same_subtype(
    items: List[Dict[str, Any]],
    docs_by_id: Dict[str, DocumentInput],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Within each (company_id, event_type) group, merge signals that share event_subtype
    and span at least two distinct source documents.
    Returns (new_items, number of signals removed by merging).
    """
    groups: Dict[Tuple[Optional[str], str], List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        sig: Signal = it["signal"]
        company = _company_id_for_signal(sig, docs_by_id)
        key = (company, sig.event_type.value)
        groups[key].append(it)

    removed = 0
    new_items: List[Dict[str, Any]] = []

    for _gkey, group in groups.items():
        by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for it in group:
            by_subtype[it["signal"].event_subtype].append(it)

        for _subtype, sub_items in by_subtype.items():
            doc_ids = {_primary_document_id(it["signal"]) for it in sub_items}
            doc_ids.discard(None)
            if len(doc_ids) >= 2:
                sigs = [it["signal"] for it in sub_items]
                new_items.append(_merge_item_group(sub_items, sigs))
                removed += len(sub_items) - 1
            else:
                new_items.extend(sub_items)

    return new_items, removed


def _build_all_cross_document_pairs(
    items: List[Dict[str, Any]],
    docs_by_id: Dict[str, DocumentInput],
) -> List[Tuple[int, int]]:
    """Every pair of signals from different documents, same company; same-document pairs excluded."""
    pairs: List[Tuple[int, int]] = []
    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            sa: Signal = items[i]["signal"]
            sb: Signal = items[j]["signal"]
            ca = _company_id_for_signal(sa, docs_by_id)
            cb = _company_id_for_signal(sb, docs_by_id)
            if ca is None or cb is None or ca != cb:
                continue
            da = _primary_document_id(sa)
            db = _primary_document_id(sb)
            if not da or not db or da == db:
                continue
            pairs.append((i, j))
    return pairs


_tls = threading.local()


def _thread_openai_client() -> OpenAI:
    """One OpenAI client per worker thread (avoids shared-client issues)."""
    c = getattr(_tls, "client", None)
    if c is not None:
        return c
    _tls.client = get_client()
    return _tls.client


def _build_pair_prompt(sa: Signal, sb: Signal) -> str:
    ev_a = sa.evidence[0] if sa.evidence else None
    ev_b = sb.evidence[0] if sb.evidence else None
    sn_a = ev_a.snippet if ev_a else ""
    sn_b = ev_b.snippet if ev_b else ""
    src_a = ev_a.source_name if ev_a else "unknown"
    src_b = ev_b.source_name if ev_b else "unknown"

    return (
        "You are a senior credit-risk analyst. Two structured signals were extracted from "
        "different sources about the same obligor. Classify how they relate factually.\n\n"
        "Rules:\n"
        "- Base your judgment ONLY on the evidence_snippets and the structured fields below. "
        "Do not invent facts.\n"
        "- Signals may use different event_type labels (e.g., news vs company statement) but "
        "still refer to the same real-world proposition — compare the factual claims, not only "
        "the taxonomy labels.\n"
        "- **duplicate**: The two signals describe the same underlying factual event or claim "
        "for the same entity and time-relevant context; merging them would not lose distinct "
        "information. Minor wording differences are OK.\n"
        "- **contradiction**: The core factual assertions are mutually exclusive if both were "
        "taken as true (e.g., \"filed for court-supervised restructuring\" vs \"has not filed "
        "any formal application for court-supervised restructuring\"). Speculation vs flat "
        "denial of the same specific fact can be contradiction when both speak to the same "
        "yes/no proposition.\n"
        "- **related**: Same theme, sector, or narrative thread, but the claims are compatible "
        "or address different facets (e.g., asset-sale difficulty vs generic operational update) "
        "without mutual exclusion. Use when you cannot justify duplicate or contradiction.\n"
        "- **unrelated**: No substantive factual link between the two claims; different topics "
        "or no clear connection.\n\n"
        "Boundary conditions:\n"
        "- If one snippet is vague and the other is specific but they do not assert opposite "
        "facts, prefer **related** over **contradiction**.\n"
        "- If both could be true under different interpretations of timing or scope, prefer "
        "**related**, not **contradiction**.\n"
        "- **Contradiction** requires a clear logical clash on the same obligor and overlapping "
        "subject matter.\n\n"
        f"SIGNAL A:\n- event_type: {sa.event_type.value}\n- event_subtype: {sa.event_subtype}\n"
        f"- severity: {sa.severity.value}\n- source: {src_a}\n- evidence_snippet: {sn_a!r}\n\n"
        f"SIGNAL B:\n- event_type: {sb.event_type.value}\n- event_subtype: {sb.event_subtype}\n"
        f"- severity: {sb.severity.value}\n- source: {src_b}\n- evidence_snippet: {sn_b!r}\n\n"
        "Output: JSON only, one object, exactly these keys:\n"
        '- "relationship": one of "duplicate", "contradiction", "related", "unrelated"\n'
        '- "explanation": one concise sentence stating the decisive criterion you applied\n'
    )


def _parse_llm_json(text: str) -> Tuple[str, str]:
    if not text:
        return "unrelated", "empty_response"
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return "unrelated", "no_json"
    try:
        payload = json.loads(m.group())
        rel = str(payload.get("relationship", "unrelated")).strip().lower()
        if rel not in {"duplicate", "contradiction", "related", "unrelated"}:
            rel = "unrelated"
        expl = str(payload.get("explanation", ""))
        return rel, expl
    except Exception:
        return "unrelated", "parse_error"


def _call_llm_pair(sa: Signal, sb: Signal) -> Tuple[str, str]:
    client = _thread_openai_client()
    prompt = _build_pair_prompt(sa, sb)
    response = client.chat.completions.create(
        model=MODEL_SIS,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    return _parse_llm_json(raw)


def _apply_duplicate_and_contradiction_edges(
    working: List[Dict[str, Any]],
    duplicate_edges: List[Tuple[int, int]],
    contradiction_edges: List[Tuple[int, int]],
) -> Tuple[List[Dict[str, Any]], int]:
    """DSU-merge duplicates, then apply contradiction dispute/resolution. Indices refer to ``working``."""
    n = len(working)
    parent = list(range(n))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i: int, j: int) -> None:
        ri, rj = _find(i), _find(j)
        if ri != rj:
            parent[rj] = ri

    for ia, ib in duplicate_edges:
        _union(ia, ib)

    roots_seen: set[int] = set()
    rep_signal: Dict[int, Signal] = {}
    collapsed: List[Dict[str, Any]] = []
    duplicates_merged_delta = 0

    for i in range(n):
        r = _find(i)
        if r in roots_seen:
            continue
        roots_seen.add(r)
        members = [j for j in range(n) if _find(j) == r]
        if len(members) == 1:
            collapsed.append(working[members[0]])
            rep_signal[members[0]] = working[members[0]]["signal"]
        else:
            group_items = [working[j] for j in members]
            sigs = [it["signal"] for it in group_items]
            merged_item = _merge_item_group(group_items, sigs)
            collapsed.append(merged_item)
            merged_sig = merged_item["signal"]
            for j in members:
                rep_signal[j] = merged_sig
            duplicates_merged_delta += len(members) - 1

    working = collapsed

    for ia, ib in contradiction_edges:
        sa = rep_signal.get(ia)
        sb = rep_signal.get(ib)
        if sa is None or sb is None:
            continue
        if sa is sb:
            continue

        qa = _primary_source_quality(sa)
        qb = _primary_source_quality(sb)

        if qa >= 0.8 and qb >= 0.8:
            sa.conflict_status = ConflictStatus.disputed
            sa.ambiguous = True
            sb.conflict_status = ConflictStatus.disputed
            sb.ambiguous = True
        else:
            if qa > qb:
                winner, loser = sa, sb
            elif qb > qa:
                winner, loser = sb, sa
            else:
                winner = sa if sa.confidence >= sb.confidence else sb
                loser = sb if winner is sa else sa

            winner.conflict_status = ConflictStatus.resolved
            winner.ambiguous = False
            for e in loser.evidence:
                if len(winner.evidence) >= MAX_EVIDENCE_PER_SIGNAL:
                    break
                key = (e.document_id, e.char_interval.start, e.char_interval.end)
                if not any(
                    x.document_id == key[0]
                    and x.char_interval.start == key[1]
                    and x.char_interval.end == key[2]
                    for x in winner.evidence
                ):
                    winner.evidence.append(e)
            winner.confidence = max(winner.confidence, loser.confidence)

            loser_id = loser.signal_id
            working = [it for it in working if it["signal"].signal_id != loser_id]

    return working, duplicates_merged_delta


def _apply_positive_auto_ambiguous_post(
    working: List[Dict[str, Any]],
    docs_by_id: Dict[str, DocumentInput],
) -> int:
    """Mark non-disputed positive signals ambiguous when a cross-doc high-severity negative exists (same company)."""

    high_negatives: List[Signal] = []
    for it in working:
        s: Signal = it["signal"]
        if s.event_type != EventCategory.positive_signals and s.severity == Severity.high:
            high_negatives.append(s)

    marked = 0
    for it in working:
        s: Signal = it["signal"]
        if s.event_type != EventCategory.positive_signals:
            continue
        if s.conflict_status == ConflictStatus.disputed:
            continue
        pos_company = _company_id_for_signal(s, docs_by_id)
        pos_doc = _primary_document_id(s)
        if pos_company is None or not pos_doc:
            continue
        found_cross_doc = False
        for n in high_negatives:
            if _company_id_for_signal(n, docs_by_id) != pos_company:
                continue
            nd = _primary_document_id(n)
            if not nd or nd == pos_doc:
                continue
            found_cross_doc = True
            break
        if not found_cross_doc:
            continue
        if not s.ambiguous:
            it["signal"] = s.model_copy(deep=True, update={"ambiguous": True})
            marked += 1
    return marked


def conflict_resolution(
    verification_items: List[Dict[str, Any]],
    documents: List[DocumentInput],
    *,
    max_workers: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Resolve conflicts: Stage 1 dedup, NLI screen, LLM confirm contradictions/duplicates.

    Args:
        verification_items: Dicts with ``signal``, optional verification fields.
        documents: Source documents for company / document lookup.
        max_workers: Max concurrent LLM calls for Stage 3.

    Returns:
        (updated_items, summary) including nli_pairs_screened, nli_contradictions_detected,
        llm_confirmed, contradiction_explanations (LLM-confirmed contradiction edges),
        plus legacy numeric counters.
    """
    total_input = len(verification_items)

    docs_by_id = {d.document_id: d for d in documents}

    working: List[Dict[str, Any]] = []
    for it in verification_items:
        sig: Signal = it["signal"]
        sig_copy = sig.model_copy(deep=True)
        sig_copy.confidence = float(it.get("adjusted_confidence", sig_copy.confidence))
        working.append(
            {
                "signal": sig_copy,
                "verification_decision": it.get("verification_decision", "skipped"),
                "adjusted_confidence": float(it.get("adjusted_confidence", sig_copy.confidence)),
                "original_confidence": float(it.get("original_confidence", sig_copy.confidence)),
            }
        )

    duplicates_merged = 0
    working, s1_removed = _stage1_cross_doc_same_subtype(working, docs_by_id)
    duplicates_merged += s1_removed

    cross_pairs = _build_all_cross_document_pairs(working, docs_by_id)
    nli_pairs_screened = len(cross_pairs)
    nli_contradictions_detected = 0
    llm_confirmed = 0
    contradictions_found = 0
    contradiction_explanations: List[Dict[str, str]] = []

    nli_candidate_pairs: List[Tuple[int, int, float]] = []

    if cross_pairs:
        nli_model = _load_cross_encoder()
        sentence_pairs: List[Tuple[str, str]] = []
        for ia, ib in cross_pairs:
            sa = working[ia]["signal"]
            sb = working[ib]["signal"]
            sentence_pairs.append(
                (_primary_evidence_snippet(sa), _primary_evidence_snippet(sb)),
            )

        scores = nli_model.predict(
            sentence_pairs,
            batch_size=32,
            show_progress_bar=False,
        )

        arr = np.asarray(scores)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        for idx, (ia, ib) in enumerate(cross_pairs):
            row = arr[idx]
            am = int(np.argmax(row))
            c_score = float(row[NLI_CONTRADICTION_INDEX])
            if am == NLI_CONTRADICTION_INDEX:
                nli_contradictions_detected += 1
                nli_candidate_pairs.append((ia, ib, c_score))

        print(
            f"[NLI] Screened {nli_pairs_screened} pairs, "
            f"found {nli_contradictions_detected} potential contradictions"
        )
        for ia, ib, c_score in nli_candidate_pairs:
            sa = working[ia]["signal"]
            sb = working[ib]["signal"]
            print(
                f"[NLI] {sa.signal_id} vs {sb.signal_id}: "
                f"contradiction_score={c_score:.3f}"
            )
    elif nli_pairs_screened == 0:
        print("[NLI] Screened 0 pairs, found 0 potential contradictions")

    duplicate_edges: List[Tuple[int, int]] = []
    contradiction_edges: List[Tuple[int, int]] = []

    if nli_candidate_pairs:
        def _llm_task(
            ia: int,
            ib: int,
        ) -> Tuple[int, int, str, str]:
            sa = working[ia]["signal"]
            sb = working[ib]["signal"]
            rel, expl = _call_llm_pair(sa, sb)
            print(f"[LLM] {sa.signal_id} vs {sb.signal_id}: {rel} - {expl}")
            return (ia, ib, rel, expl)

        mw = max(1, min(max_workers, len(nli_candidate_pairs)))
        llm_results: List[Tuple[int, int, str, str]] = []
        with ThreadPoolExecutor(max_workers=mw) as ex:
            futs = [
                ex.submit(_llm_task, ia, ib)
                for ia, ib, _ in nli_candidate_pairs
            ]
            for fut in as_completed(futs):
                llm_results.append(fut.result())

        for ia, ib, rel, expl in llm_results:
            if rel == "duplicate":
                duplicate_edges.append((ia, ib))
            elif rel == "contradiction":
                contradiction_edges.append((ia, ib))
                llm_confirmed += 1
                contradictions_found += 1
                sa = working[ia]["signal"]
                sb = working[ib]["signal"]
                contradiction_explanations.append(
                    {
                        "signal_id_a": sa.signal_id,
                        "signal_id_b": sb.signal_id,
                        "explanation": expl,
                    }
                )
            # related / unrelated: NLI false positive — leave signals as-is (no_conflict)

    if duplicate_edges or contradiction_edges:
        working, dm = _apply_duplicate_and_contradiction_edges(
            working, duplicate_edges, contradiction_edges
        )
        duplicates_merged += dm

    positive_auto_ambiguous = _apply_positive_auto_ambiguous_post(working, docs_by_id)
    print(
        f"[POST] Marked {positive_auto_ambiguous} positive signals as ambiguous "
        "(high-severity negative signals exist)"
    )

    disputed_count = sum(
        1 for it in working if it["signal"].conflict_status == ConflictStatus.disputed
    )

    total_output = len(working)
    summary = {
        "total_input": total_input,
        "total_output": total_output,
        "duplicates_merged": duplicates_merged,
        "contradictions_found": contradictions_found,
        "disputed": disputed_count,
        "positive_auto_ambiguous": positive_auto_ambiguous,
        "nli_pairs_screened": nli_pairs_screened,
        "nli_contradictions_detected": nli_contradictions_detected,
        "llm_confirmed": llm_confirmed,
        "contradiction_explanations": contradiction_explanations,
    }
    return working, summary
