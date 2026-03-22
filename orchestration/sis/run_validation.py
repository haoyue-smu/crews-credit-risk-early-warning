"""Development script to run schema_validation_gate on local Hyflux data.

Run with:
    python -m orchestration.sis.run_validation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity
from orchestration.sis.nodes.validate import schema_validation_gate


def _load_documents(root: Path) -> Dict[str, DocumentInput]:
    docs: Dict[str, DocumentInput] = {}
    for path in sorted(root.glob("doc_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        doc = DocumentInput.model_validate(payload)
        docs[doc.document_id] = doc
    return docs


def _signals_from_extraction_results(
    results_path: Path,
    documents: List[DocumentInput],
) -> List[Signal]:
    signals: List[Signal] = []
    with results_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload: Dict[str, Any] = json.loads(line)
            text = payload.get("text", "")

            # extraction_results.jsonl uses synthetic document_ids; we match by full_text.
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

                signal = Signal(
                    signal_id=f"{doc.document_id}_{ex.get('extraction_index')}_{ex.get('group_index')}",
                    event_type=event_type,
                    event_subtype=event_subtype,
                    severity=severity,
                    confidence=1.0,
                    ambiguous=False,
                    evidence=[evidence],
                )
                signals.append(signal)

    return signals


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    hyflux_root = project_root / "data" / "local" / "hyflux"
    results_path = hyflux_root / "extraction_results.jsonl"
    validation_cache_path = hyflux_root / "validation_results.jsonl"

    args = sys.argv[1:]
    use_cache = "--use-cache" in args
    force_recompute = "--no-cache" in args

    docs_by_id = _load_documents(hyflux_root)
    docs_list = list(docs_by_id.values())

    signals = _signals_from_extraction_results(results_path, docs_list)

    print(f"Loaded {len(signals)} signals from extraction_results.jsonl")

    if use_cache and not force_recompute and validation_cache_path.exists():
        print(f"Using cached validation results from {validation_cache_path}")
        records: List[Dict[str, Any]] = []
        with validation_cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))

        valid_signals = [r for r in records if r.get("status") == "valid"]
        warnings = [r for r in records if r.get("status") == "warning"]
        retry_needed: List[str] = sorted(
            {str(r.get("document_id")) for r in records if r.get("status") == "retry"}
        )
    else:
        validation_result = schema_validation_gate(
            signals=signals,
            documents=docs_list,
        )

        valid_signals = validation_result["valid_signals"]
        retry_needed = validation_result["retry_needed"]
        passed_with_warnings = validation_result["passed_with_warnings"]

        # Save per-signal validation results to JSONL.
        with validation_cache_path.open("w", encoding="utf-8") as f:
            for sig in valid_signals:
                doc_id = sig.evidence[0].document_id if sig.evidence else None
                rec = {
                    "signal_id": sig.signal_id,
                    "document_id": doc_id,
                    "status": "valid",
                }
                f.write(json.dumps(rec) + "\n")
            for sig in passed_with_warnings:
                doc_id = sig.evidence[0].document_id if sig.evidence else None
                rec = {
                    "signal_id": sig.signal_id,
                    "document_id": doc_id,
                    "status": "warning",
                }
                f.write(json.dumps(rec) + "\n")
            for doc_id in retry_needed:
                rec = {
                    "signal_id": None,
                    "document_id": doc_id,
                    "status": "retry",
                }
                f.write(json.dumps(rec) + "\n")

        warnings = passed_with_warnings

    print(f"\nValidation summary:")
    print(f"- valid_signals: {len(valid_signals)}")
    print(f"- passed_with_warnings: {len(warnings)}")
    print(f"- retry_needed (document_ids): {retry_needed}")


if __name__ == "__main__":
    main()

