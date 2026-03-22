"""Development script to run conflict_resolution and evidence_gate locally.

Run with:
    python -m orchestration.sis.run_conflict_and_gate
"""

from __future__ import annotations

from pathlib import Path

from orchestration.sis.nodes.conflict import conflict_resolution
from orchestration.sis.nodes.evidence_gate import evidence_gate
from orchestration.sis.run_conflict import (
    build_verification_items,
    load_hyflux_documents,
    load_verification_index,
    signals_from_extraction_results,
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    hyflux_root = project_root / "data" / "local" / "hyflux"
    extraction_path = hyflux_root / "extraction_results.jsonl"
    verification_path = hyflux_root / "verification_results.jsonl"

    docs_by_id = load_hyflux_documents(hyflux_root)
    docs_list = list(docs_by_id.values())

    signals = signals_from_extraction_results(extraction_path, docs_list)
    print(f"Loaded {len(signals)} raw signals from extraction_results.jsonl")

    verification_index = load_verification_index(verification_path)
    print(f"Loaded {len(verification_index)} verification records from verification_results.jsonl")

    items = build_verification_items(signals, verification_index)
    resolved_items, summary = conflict_resolution(items, docs_list, max_workers=10)
    resolved = [it["signal"] for it in resolved_items]
    print(f"After conflict_resolution: {len(resolved)} signals")
    print("Conflict summary:", summary)

    sis_output, retrieval_reqs = evidence_gate(resolved, docs_list)
    m = sis_output.metadata
    print("\nEvidence gate (SISOutput) summary:")
    print(f"- signals_extracted: {m.signals_extracted}")
    print(f"- signals_auto_verified: {m.signals_auto_verified}")
    print(f"- signals_ambiguous: {m.signals_ambiguous}")
    print(f"- targeted_retrieval_requests: {len(retrieval_reqs)}")


if __name__ == "__main__":
    main()
