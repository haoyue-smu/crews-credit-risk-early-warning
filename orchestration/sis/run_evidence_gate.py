"""Final SIS → FRD handoff: run evidence_gate on conflict_results.jsonl.

Run with:
    python -m orchestration.sis.run_evidence_gate

Writes ``data/local/hyflux/sis_output.jsonl`` (single JSON record: SISOutput + retrieval).
``--use-cache`` replays the last saved bundle without re-running the gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shared.schemas.retrieval import TargetedRetrievalRequest
from shared.schemas.signals import SISOutput, Signal
from orchestration.sis.nodes.evidence_gate import evidence_gate
from orchestration.sis.run_conflict import load_conflict_cache, load_hyflux_documents


def _bundle_path(hyflux_root: Path) -> Path:
    return hyflux_root / "sis_output.jsonl"


def save_sis_bundle(
    path: Path,
    sis_output: SISOutput,
    retrieval: List[TargetedRetrievalRequest],
) -> None:
    record: Dict[str, Any] = {
        "_sis_bundle_v1": True,
        "sis_output": sis_output.model_dump(mode="json"),
        "targeted_retrieval_requests": [r.model_dump(mode="json") for r in retrieval],
    }
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


def load_sis_bundle(path: Path) -> Tuple[SISOutput, List[TargetedRetrievalRequest]] | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    data = json.loads(raw.splitlines()[0])
    if not data.get("_sis_bundle_v1"):
        return None
    out = SISOutput.model_validate(data["sis_output"])
    reqs = [
        TargetedRetrievalRequest.model_validate(r)
        for r in data.get("targeted_retrieval_requests", [])
    ]
    return out, reqs


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    hyflux_root = project_root / "data" / "local" / "hyflux"
    conflict_path = hyflux_root / "conflict_results.jsonl"
    out_path = _bundle_path(hyflux_root)

    args = sys.argv[1:]
    use_cache = "--use-cache" in args
    force_recompute = "--no-cache" in args

    if use_cache and not force_recompute:
        cached = load_sis_bundle(out_path)
        if cached is None:
            print(f"No usable SIS bundle at {out_path}; run without --use-cache first.")
            return
        sis_output, retrieval = cached
        print(f"Using cached SIS output from {out_path}\n")
    else:
        conflict_data = load_conflict_cache(conflict_path)
        if conflict_data is None:
            print(
                f"No usable conflict cache at {conflict_path}. "
                "Run: python -m orchestration.sis.run_conflict"
            )
            return
        _summary, items = conflict_data
        signals: List[Signal] = [it["signal"] for it in items]
        docs_by_id = load_hyflux_documents(hyflux_root)
        docs_list = list(docs_by_id.values())

        sis_output, retrieval = evidence_gate(signals, docs_list)
        save_sis_bundle(out_path, sis_output, retrieval)
        print(f"Wrote SIS bundle to {out_path}\n")

    print("=== SISOutput (JSON) ===")
    print(json.dumps(sis_output.model_dump(mode="json"), indent=2, ensure_ascii=False))

    if retrieval:
        print("\n=== TargetedRetrievalRequest (RS placeholder) ===")
        for req in retrieval:
            print(
                f"[RETRIEVAL_NEEDED] company={req.company_id}, keywords={req.keywords}, "
                f"target_sources={req.target_source_types}, context={req.signal_context}"
            )
    else:
        print("\n(No TargetedRetrievalRequest objects.)")


if __name__ == "__main__":
    main()
