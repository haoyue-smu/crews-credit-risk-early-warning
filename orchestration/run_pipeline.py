"""
End-to-end pipeline runner: SIS → FRD (LangGraph).

Usage:
    python -m orchestration.run_pipeline
    python -m orchestration.run_pipeline --company hyflux
    python -m orchestration.run_pipeline --company hyflux --no-report
    python -m orchestration.run_pipeline --company hyflux --financial data/local/hyflux/financial_profile.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from orchestration.graph import build_pipeline
from orchestration.state import PipelineState
from shared.schemas.frd import FRDOutput


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_documents(company: str) -> list[dict]:
    """Load all ``doc_*.json`` files for a company from ``data/local/{company}/``."""
    doc_dir = _project_root() / "data" / "local" / company
    if not doc_dir.is_dir():
        raise FileNotFoundError(f"Document directory not found: {doc_dir}")
    docs: list[dict] = []
    for fpath in sorted(doc_dir.glob("doc_*.json")):
        docs.append(json.loads(fpath.read_text(encoding="utf-8")))
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SIS → FRD LangGraph pipeline.")
    parser.add_argument("--company", default="hyflux", help="Company folder under data/local/")
    parser.add_argument(
        "--financial",
        default=None,
        help="Path to FinancialProfile JSON (default: data/local/{company}/financial_profile.json if present)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip LLM report generation (sets skip_report on pipeline state)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model id for FRD report (default: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    root = _project_root()
    documents = load_documents(args.company)
    print(f"Loaded {len(documents)} documents for {args.company!r}")

    financial_profile: dict | None = None
    fp_path = Path(args.financial) if args.financial else root / "data" / "local" / args.company / "financial_profile.json"
    if fp_path.is_file():
        financial_profile = json.loads(fp_path.read_text(encoding="utf-8"))
        print(f"Loaded financial profile from {fp_path}")
    else:
        print(f"No financial profile at {fp_path} (FRD will flag financial_data_unavailable)")

    initial_state: PipelineState = {
        "company_id": args.company,
        "documents": documents,
        "financial_profile": financial_profile,
        "skip_report": args.no_report,
        "report_model_id": args.model,
    }

    print("\n=== Running SIS → FRD Pipeline ===\n")
    pipeline = build_pipeline()
    final_state = pipeline.invoke(initial_state)

    frd_raw = final_state.get("frd_output")
    if not frd_raw:
        print("Pipeline finished but frd_output is missing.", file=sys.stderr)
        sys.exit(1)

    frd = FRDOutput.model_validate(frd_raw)

    from orchestration.frd.run_scoring import _print_scorecard

    _print_scorecard(frd)

    rep = final_state.get("report")
    if rep and isinstance(rep, dict) and rep.get("full_narrative"):
        print("\n=== Credit Risk Report ===")
        print(rep["full_narrative"])

    out_path = root / "data" / "local" / args.company / "pipeline_output.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(frd_raw, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print("\n=== Pipeline Complete ===")


if __name__ == "__main__":
    main()
