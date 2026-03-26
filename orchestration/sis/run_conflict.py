"""Development script to run conflict_resolution on Hyflux extraction + verification data.

Run with:
    python -m orchestration.sis.run_conflict

Uses ``verification_results.jsonl`` when present to attach decisions/confidence;
otherwise falls back to extraction-only signals with default verification fields.

``--use-cache`` skips conflict_resolution and replays ``conflict_results.jsonl``.
``--no-cache`` forces a fresh conflict pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity
from orchestration.sis.nodes.conflict import conflict_resolution


def load_hyflux_documents(root: Path) -> Dict[str, DocumentInput]:
    docs: Dict[str, DocumentInput] = {}
    for path in sorted(root.glob("doc_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        doc = DocumentInput.model_validate(payload)
        docs[doc.document_id] = doc
    return docs


def signals_from_extraction_results(
    results_path: Path,
    documents: List[DocumentInput],
) -> List[Signal]:
    signals: List[Signal] = []
    if not results_path.exists():
        return signals
    with results_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload: Dict[str, Any] = json.loads(line)
            text = payload.get("text", "")
            doc = next((d for d in documents if d.full_text == text), None)
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


def load_verification_index(path: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return index
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            sid = str(rec.get("signal_id", ""))
            if sid:
                index[sid] = rec
    return index


def build_verification_items(
    signals: List[Signal],
    verification_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge raw signals with optional verification cache rows (by ``signal_id``)."""
    items: List[Dict[str, Any]] = []
    for sig in signals:
        rec = verification_index.get(sig.signal_id, {})
        adj = float(rec.get("adjusted_confidence", sig.confidence))
        orig = float(rec.get("original_confidence", sig.confidence))
        items.append(
            {
                "signal": sig,
                "verification_decision": str(rec.get("verification_decision", "skipped")),
                "adjusted_confidence": adj,
                "original_confidence": orig,
            }
        )
    return items


def _item_to_record(item: Dict[str, Any]) -> Dict[str, Any]:
    sig: Signal = item["signal"]
    return {
        "signal": sig.model_dump(mode="json"),
        "verification_decision": item.get("verification_decision"),
        "adjusted_confidence": item.get("adjusted_confidence"),
        "original_confidence": item.get("original_confidence"),
    }


def _item_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "signal": Signal.model_validate(rec["signal"]),
        "verification_decision": rec.get("verification_decision", "skipped"),
        "adjusted_confidence": float(rec.get("adjusted_confidence", 0.0)),
        "original_confidence": float(rec.get("original_confidence", 0.0)),
    }


def save_conflict_results(output_path: Path, items: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    payload = {"_conflict_summary": True, **summary}
    with output_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
        for it in items:
            f.write(json.dumps(_item_to_record(it)) + "\n")


def load_conflict_cache(output_path: Path) -> tuple[Dict[str, Any], List[Dict[str, Any]]] | None:
    if not output_path.exists():
        return None
    lines = [ln for ln in output_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    first = json.loads(lines[0])
    if not first.get("_conflict_summary"):
        return None
    summary = {k: v for k, v in first.items() if k != "_conflict_summary"}
    items = [_item_from_record(json.loads(ln)) for ln in lines[1:]]
    return summary, items


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    hyflux_root = project_root / "data" / "local" / "hyflux"
    extraction_path = hyflux_root / "extraction_results.jsonl"
    verification_path = hyflux_root / "verification_results.jsonl"
    conflict_path = hyflux_root / "conflict_results.jsonl"

    args = sys.argv[1:]
    use_cache = "--use-cache" in args
    force_recompute = "--no-cache" in args

    if use_cache and not force_recompute:
        cached = load_conflict_cache(conflict_path)
        if cached is None:
            print(f"No usable cache at {conflict_path}; run without --use-cache first.")
            return
        summary, items = cached
        print(f"Using cached conflict results from {conflict_path}")
        print("\nConflict summary (cached):")
        for k, v in summary.items():
            print(f"- {k}: {v}")
        for it in items:
            sig: Signal = it["signal"]
            print(
                f"- {sig.signal_id} | {sig.event_type.value}/{sig.event_subtype} | "
                f"conflict={sig.conflict_status.value} ambiguous={sig.ambiguous}"
            )
        return

    docs_by_id = load_hyflux_documents(hyflux_root)
    docs_list = list(docs_by_id.values())
    signals = signals_from_extraction_results(extraction_path, docs_list)
    if not signals:
        print(f"No signals loaded from {extraction_path} (check extraction JSONL and doc JSONs).")
        return

    verification_index = load_verification_index(verification_path)
    if verification_index:
        print(f"Merged {len(verification_index)} verification rows from {verification_path}")
    else:
        print(f"No verification cache at {verification_path}; using default verification fields on signals.")

    items = build_verification_items(signals, verification_index)
    print(f"Running conflict_resolution on {len(items)} signals (max_workers=10 for Gemini)...")

    resolved_items, summary = conflict_resolution(items, docs_list, max_workers=10)

    print("\nConflict summary:")
    for k, v in summary.items():
        print(f"- {k}: {v}")

    for it in resolved_items:
        sig: Signal = it["signal"]
        print(
            f"- {sig.signal_id} | {sig.event_type.value}/{sig.event_subtype} | "
            f"conflict={sig.conflict_status.value} ambiguous={sig.ambiguous} "
            f"confidence={sig.confidence:.2f}"
        )

    save_conflict_results(conflict_path, resolved_items, summary)
    print(f"\nSaved conflict results to: {conflict_path}")


if __name__ == "__main__":
    main()
