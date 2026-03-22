from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from shared.schemas.documents import DocumentInput
from shared.schemas.signals import CharInterval, Evidence, Signal
from shared.taxonomy import EventCategory, Severity


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
    cache_path = hyflux_root / "verification_results.jsonl"

    docs_by_id = _load_documents(hyflux_root)
    docs_list = list(docs_by_id.values())
    signals = _signals_from_extraction_results(results_path, docs_list)

    # Expected 24 signals.
    decisions = [
        ("yes", 1.0),
        ("yes", 1.0),
        ("partial", 0.5),
        ("yes", 1.0),
        ("yes", 1.0),
        ("partial", 0.5),
        ("yes", 1.0),
        ("partial", 0.5),
    ]

    with cache_path.open("w", encoding="utf-8") as f:
        for idx, sig in enumerate(signals):
            if idx < len(decisions):
                decision, adj_conf = decisions[idx]
            else:
                decision, adj_conf = "skipped", 1.0

            record = {
                "signal_id": sig.signal_id,
                "verification_decision": decision,
                "adjusted_confidence": adj_conf,
                "original_confidence": 1.0,
                "event_type": sig.event_type.value,
                "event_subtype": sig.event_subtype,
            }
            f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()

