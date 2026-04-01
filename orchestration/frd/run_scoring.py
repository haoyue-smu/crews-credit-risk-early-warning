"""
Dev runner for FRD score_risk.
Loads SIS output from cached jsonl, runs scoring, prints results.

Usage:
    python -m orchestration.frd.run_scoring
    python -m orchestration.frd.run_scoring --config '{"high_criteria_for_red": 2}'
    python -m orchestration.frd.run_scoring --no-financial
    python -m orchestration.frd.run_scoring --financial path/to/fp.json
    python -m orchestration.frd.run_scoring --no-report
    python -m orchestration.frd.run_scoring --model google/gemini-2.5-pro
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shared.llm import MODEL_FRD
from orchestration.frd.nodes.aggregate_inputs import aggregate_inputs
from orchestration.frd.nodes.score_risk import score_risk
from shared.schemas.frd import CriteriaWeight, FRDOutput, FinancialProfile, ScoringConfig, TrafficLight


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_first_json_object(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Empty file: {path}")
    for line in text.splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    raise ValueError(f"No JSON line in {path}")


def _weight_tag(w: CriteriaWeight) -> str:
    return {
        CriteriaWeight.high: "HIGH",
        CriteriaWeight.medium: "MED",
        CriteriaWeight.low: "LOW",
        CriteriaWeight.mitigating: "MIT",
    }[w]


def _traffic_label(tl: TrafficLight) -> str:
    return {
        TrafficLight.red: "🔴 RED",
        TrafficLight.amber: "🟠 AMBER",
        TrafficLight.green: "🟢 GREEN",
    }[tl]


def _print_scorecard(frd: FRDOutput) -> None:
    rs = frd.risk_score
    print(f"\n=== FRD Risk Score: {frd.company_id} ===")
    print(f"Traffic Light: {_traffic_label(rs.traffic_light)}\n")
    print("Criteria Scorecard:")
    printed_fin_sep = False
    for c in rs.criteria_results:
        if c.criteria_id.startswith("B") and not printed_fin_sep:
            print("─── Financial Criteria ───")
            printed_fin_sep = True
        tag = _weight_tag(c.weight)
        status = "✅ MET" if c.met else "❌ NOT MET"
        print(f"  [{tag:5}]  {c.criteria_id} {c.criteria_name:40} {status:12} ({c.detail})")

    n_h = sum(1 for c in rs.criteria_results if c.weight == CriteriaWeight.high and c.met)
    n_m = sum(1 for c in rs.criteria_results if c.weight == CriteriaWeight.medium and c.met)
    n_l = sum(1 for c in rs.criteria_results if c.weight == CriteriaWeight.low and c.met)
    n_i = sum(1 for c in rs.criteria_results if c.weight == CriteriaWeight.mitigating and c.met)
    print(f"\nSummary: {n_h} high, {n_m} medium, {n_l} low, {n_i} mitigating")

    if rs.mitigating_details:
        for md in rs.mitigating_details:
            print(f"Mitigating: {md}")
    elif rs.has_mitigating_factors:
        print("Mitigating: A8 met — no traffic-light change under current thresholds")

    print(f"Flags: {', '.join(rs.flags)}")

    fp = frd.financial_profile
    if fp is not None:
        lz = fp.latest_zscore
        peer_line = (
            f"{fp.peer_comparison.company_percentile_rank:g}th percentile"
            if fp.peer_comparison is not None
            else "n/a"
        )
        print(
            f"\nFinancial: Z-Score {lz.score} ({lz.zone.value}) | "
            f"Trend: {fp.zscore_trend.trend_direction} {fp.zscore_trend.consecutive_decline_years}yr | "
            f"Peer: {peer_line}"
        )
        print(
            f"Source: {fp.source_filing} | Staleness: {fp.data_staleness_days} days"
        )

    cfg = rs.scoring_config_used
    print(
        "\nConfig used: "
        f"high_for_red={cfg.high_criteria_for_red}, med_for_red={cfg.medium_criteria_for_red}, "
        f"med_for_amber={cfg.medium_criteria_for_amber}, low_for_amber={cfg.low_criteria_for_amber}, "
        f"mitigating_confidence={cfg.mitigating_confidence_threshold}, "
        f"mitigating_max_override_high={cfg.mitigating_max_override_high}"
    )


def _resolve_financial_payload(
    root: Path,
    no_financial: bool,
    financial_path: str | None,
) -> dict | None:
    if no_financial:
        return None
    if financial_path:
        p = Path(financial_path)
        if not p.is_file():
            print(f"Financial profile not found: {p}", file=sys.stderr)
            sys.exit(1)
        return json.loads(p.read_text(encoding="utf-8"))
    default_fp = root / "data" / "local" / "hyflux" / "financial_profile.json"
    if default_fp.is_file():
        return json.loads(default_fp.read_text(encoding="utf-8"))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FRD score_risk on cached Hyflux SIS output.")
    parser.add_argument(
        "--config",
        default=None,
        help='JSON object merged onto default ScoringConfig, e.g. \'{"high_criteria_for_red": 2}\'',
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to SIS jsonl (default: data/local/hyflux/sis_output.jsonl under project root)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write FRD JSON (default: data/local/hyflux/frd_score_result.json)",
    )
    parser.add_argument(
        "--no-financial",
        action="store_true",
        help="Do not load financial profile (skip default file if present)",
    )
    parser.add_argument(
        "--financial",
        default=None,
        metavar="PATH",
        help="Path to FinancialProfile JSON (overrides default auto-load)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip LLM report generation (scoring only)",
    )
    parser.add_argument(
        "--model",
        default="",
        metavar="MODEL_ID",
        help="OpenRouter model ID for report generation (default: OPENROUTER_MODEL_FRD env var, fallback OPENROUTER_MODEL_ID)",
    )
    args = parser.parse_args()

    root = _project_root()
    in_path = Path(args.input) if args.input else root / "data" / "local" / "hyflux" / "sis_output.jsonl"
    out_path = Path(args.output) if args.output else root / "data" / "local" / "hyflux" / "frd_score_result.json"

    if not in_path.is_file():
        print(f"Input not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    fp_raw = _resolve_financial_payload(root, args.no_financial, args.financial)

    bundle = _load_first_json_object(in_path)
    aggregated = aggregate_inputs(bundle, financial_profile=fp_raw)
    company_id = aggregated["company_id"]
    signals = aggregated["signals"]
    fp_model: FinancialProfile | None = aggregated["financial_profile"]

    base_cfg = ScoringConfig()
    if args.config:
        override = json.loads(args.config)
        cfg = ScoringConfig.model_validate({**base_cfg.model_dump(), **override})
    else:
        cfg = base_cfg

    fp_for_score = fp_model.model_dump(mode="json") if fp_model is not None else None
    risk = score_risk(signals, company_id, cfg, financial_profile=fp_for_score)

    report: dict | None = None
    if not args.no_report:
        from orchestration.frd.nodes.generate_report import generate_report

        risk_score_dict = risk.model_dump(mode="json")
        fp_report_dict = fp_model.model_dump(mode="json") if fp_model is not None else None
        report = generate_report(
            risk_score=risk_score_dict,
            signals=signals,
            financial_profile=fp_report_dict,
            documents_processed=int(aggregated["documents_processed"]),
            model_id=args.model or MODEL_FRD,
        )

    frd = FRDOutput(
        company_id=risk.company_id,
        traffic_light=risk.traffic_light,
        risk_score=risk,
        report_narrative=report["full_narrative"] if report else None,
        financial_profile=fp_model,
        metadata={
            "runner": "orchestration.frd.run_scoring",
            "documents_processed": aggregated["documents_processed"],
            "criteria_evaluated": len(risk.criteria_results),
            "criteria_met": sum(1 for c in risk.criteria_results if c.met),
            "financial_data_available": risk.financial_data_available,
            "report_generated": report is not None,
            "report_model": report["model_used"] if report else None,
            "report_sections": report["sections"] if report else None,
            "timestamp": report["generation_timestamp"] if report else None,
        },
    )

    _print_scorecard(frd)
    if report is not None:
        print("\n=== Credit Risk Report ===")
        print(report["full_narrative"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = frd.model_dump(mode="json")
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
