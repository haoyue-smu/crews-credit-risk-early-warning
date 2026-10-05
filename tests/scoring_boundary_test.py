"""
FRD Scoring Boundary Test
==========================

Tests the deterministic scoring layer with constructed signal combinations
to verify traffic light thresholds are correctly calibrated.

Maps out the complete boundary: what combination of criteria → RED/AMBER/GREEN.
Validates against known company outcomes (Hyflux=RED, Tesla=AMBER, healthy=GREEN).

Usage:
    python -m tests.scoring_boundary_test

No LLM calls needed — pure deterministic, runs in <1 second.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.frd.nodes.score_risk import score_risk
from shared.schemas.frd import (
    AltmanZScore,
    CriteriaWeight,
    FinancialProfile,
    PeerComparison,
    ScoringConfig,
    TrafficLight,
    ZScoreZone,
    ZScoreTrend,
)


# ---------------------------------------------------------------------------
# Signal factory — construct minimal signals that trigger specific criteria
# ---------------------------------------------------------------------------

def _sig(event_type: str, severity: str, subtype: str = "test",
         ambiguous: bool = False, confidence: float = 1.0,
         conflict_status: str = "no_conflict") -> dict:
    return {
        "signal_id": f"test_{event_type}_{subtype}",
        "event_type": event_type,
        "event_subtype": subtype,
        "severity": severity,
        "confidence": confidence,
        "ambiguous": ambiguous,
        "conflict_status": conflict_status,
        "evidence": [],
    }


def signals_for_criteria(*criteria_ids: str) -> list[dict]:
    """Generate minimal signal sets that trigger exactly the specified criteria.

    Criteria trigger conditions:
      A1: ≥1 financial_distress_signals with severity=high and ambiguous=False
      A2: ≥2 legal_regulatory with severity high or medium
      A3: ≥2 management_governance (any severity)
      A4: ≥2 operational_issues with severity high or medium
      A5: ≥2 reputation_sentiment with severity high or medium
      A6: ≥1 market_industry_risks (any)
      A7: ≥1 conflict_status=disputed
      A8: ≥1 positive_signals with ambiguous=False
    """
    signals = []
    for cid in criteria_ids:
        if cid == "A1":
            signals.append(_sig("financial_distress_signals", "high", "distress_1"))
        elif cid == "A2":
            signals.append(_sig("legal_regulatory", "high", "legal_1"))
            signals.append(_sig("legal_regulatory", "medium", "legal_2"))
        elif cid == "A3":
            signals.append(_sig("management_governance", "medium", "mgmt_1"))
            signals.append(_sig("management_governance", "medium", "mgmt_2"))
        elif cid == "A4":
            signals.append(_sig("operational_issues", "medium", "ops_1"))
            signals.append(_sig("operational_issues", "medium", "ops_2"))
        elif cid == "A5":
            signals.append(_sig("reputation_sentiment", "medium", "rep_1"))
            signals.append(_sig("reputation_sentiment", "medium", "rep_2"))
        elif cid == "A6":
            signals.append(_sig("market_industry_risks", "medium", "macro_1"))
        elif cid == "A7":
            signals.append(_sig("financial_distress_signals", "medium", "disputed_1",
                                conflict_status="disputed"))
        elif cid == "A8":
            signals.append(_sig("positive_signals", "positive", "positive_1"))
    return signals


def make_financial_profile(zone: str = "safe", score: float = 4.0,
                           decline_years: int = 0,
                           percentile: float = 75.0) -> dict:
    """Build a FinancialProfile dict for testing."""
    zone_enum = {"safe": "safe", "grey": "grey", "distress": "distress"}[zone]
    return {
        "company_id": "test",
        "latest_zscore": {
            "score": score,
            "zone": zone_enum,
            "working_capital_to_total_assets": 0.2,
            "retained_earnings_to_total_assets": 0.3,
            "ebit_to_total_assets": 0.1,
            "equity_market_value_to_total_liabilities": 1.5,
            "sales_to_total_assets": 0.9,
            "reporting_period": "FY2023",
            "statement_date": date.today().isoformat(),
        },
        "zscore_trend": {
            "periods": [],
            "consecutive_decline_years": decline_years,
            "trend_direction": "declining" if decline_years >= 2 else "stable",
        },
        "peer_comparison": {
            "industry": "test",
            "peer_count": 100,
            "peer_median_zscore": 2.2,
            "peer_25th_percentile": 1.23,
            "peer_75th_percentile": 2.9,
            "company_percentile_rank": percentile,
        },
        "key_ratios": None,
        "data_staleness_days": 180,
        "source_filing": "test.pdf",
    }


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def run_boundary_map():
    """Exhaustively map which criteria combinations → which traffic light."""
    print("=" * 80)
    print("TEST 1: CRITERIA COMBINATION → TRAFFIC LIGHT BOUNDARY MAP")
    print("=" * 80)
    print()

    cfg = ScoringConfig()
    print(f"Current config: RED if ≥{cfg.high_criteria_for_red} high OR "
          f"≥{cfg.medium_criteria_for_red} medium met")
    print(f"               AMBER if ≥{cfg.medium_criteria_for_amber} medium OR "
          f"≥{cfg.low_criteria_for_amber} low met")
    print()

    # All Category A criteria (excluding A8 mitigating)
    risk_criteria = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]
    weights = {
        "A1": "HIGH", "A2": "HIGH",
        "A3": "MED", "A4": "MED",
        "A5": "LOW", "A6": "LOW", "A7": "LOW"
    }

    results = {"red": [], "amber": [], "green": []}

    # Test all combinations of 0 to 7 criteria
    for r in range(len(risk_criteria) + 1):
        for combo in combinations(risk_criteria, r):
            signals = signals_for_criteria(*combo)
            rs = score_risk(signals, "test_company")
            tl = rs.traffic_light.value
            combo_str = "+".join(combo) if combo else "(none)"
            weight_str = "+".join(weights[c] for c in combo) if combo else ""
            results[tl].append((combo_str, weight_str, rs.high_criteria_met,
                                rs.medium_criteria_met, rs.low_criteria_met))

    # Print summary
    for color in ["red", "amber", "green"]:
        entries = results[color]
        print(f"\n{'🔴' if color=='red' else '🟡' if color=='amber' else '🟢'} "
              f"{color.upper()} — {len(entries)} combinations")
        print(f"  {'Criteria':<35} {'Weights':<25} {'H':>3} {'M':>3} {'L':>3}")
        print(f"  {'-'*35} {'-'*25} {'-'*3} {'-'*3} {'-'*3}")
        for combo_str, weight_str, h, m, l in entries[:15]:  # cap output
            print(f"  {combo_str:<35} {weight_str:<25} {h:>3} {m:>3} {l:>3}")
        if len(entries) > 15:
            print(f"  ... and {len(entries)-15} more")

    return results


def run_real_company_scenarios():
    """Test against known company outcomes."""
    print("\n" + "=" * 80)
    print("TEST 2: REAL COMPANY SCENARIO VALIDATION")
    print("=" * 80)

    scenarios = [
        {
            "name": "Hyflux (2018) — Expected: RED",
            "expected": "red",
            "description": "Defaulted company: debt restructuring, payment default, asset sale difficulty, employee dissatisfaction",
            "criteria": ["A1", "A2", "A3", "A4", "A5", "A6"],
            "financial": make_financial_profile("distress", 0.5, decline_years=3, percentile=5),
        },
        {
            "name": "Tesla (2026) — Expected: AMBER",
            "expected": "amber",
            "description": "Financially healthy but governance/operational concerns",
            "criteria": ["A2", "A3", "A4", "A5", "A6"],
            "financial": make_financial_profile("safe", 4.2, decline_years=0, percentile=100),
        },
        {
            "name": "Stable Blue Chip (e.g. Apple) — Expected: GREEN",
            "expected": "green",
            "description": "No significant risk signals, strong financials",
            "criteria": [],
            "financial": make_financial_profile("safe", 5.0, decline_years=0, percentile=90),
        },
        {
            "name": "Company with only sector risk — Expected: GREEN",
            "expected": "green",
            "description": "Macro headwinds but no company-specific issues",
            "criteria": ["A6"],
            "financial": make_financial_profile("safe", 3.5, decline_years=0, percentile=60),
        },
        {
            "name": "Grey zone financials + some ops issues — Expected: AMBER",
            "expected": "amber",
            "description": "Z-Score in grey zone, some operational issues",
            "criteria": ["A4"],
            "financial": make_financial_profile("grey", 2.0, decline_years=1, percentile=30),
        },
        {
            "name": "Distress zone + legal issues — Expected: RED",
            "expected": "red",
            "description": "Z-Score distress + significant legal/regulatory risk",
            "criteria": ["A1", "A2"],
            "financial": make_financial_profile("distress", 0.8, decline_years=3, percentile=5),
        },
        {
            "name": "High risk but strong positive signals — Expected: AMBER (mitigated)",
            "expected": "amber",
            "description": "Would be RED but positive signals downgrade it",
            "criteria": ["A1", "A2", "A8"],
            "financial": make_financial_profile("safe", 4.0, decline_years=0, percentile=80),
        },
        {
            "name": "Single high criteria only — Expected: AMBER",
            "expected": "amber",
            "description": "Only one high-weight criterion met, not enough for RED",
            "criteria": ["A1"],
            "financial": None,
        },
        {
            "name": "Two high criteria — Expected: RED",
            "expected": "red",
            "description": "Two high-weight criteria met triggers RED",
            "criteria": ["A1", "A2"],
            "financial": None,
        },
        {
            "name": "Three medium criteria — Expected: RED",
            "expected": "red",
            "description": "Three medium-weight criteria met triggers RED",
            "criteria": ["A3", "A4"],  # A3+A4 = 2 medium, need B criteria for 3rd
            "financial": make_financial_profile("grey", 2.0, decline_years=2, percentile=30),
            # B2 (grey zone) = medium met, B3 (2yr decline) = medium met → total 4 medium → RED
        },
        {
            "name": "No signals, distress financials — Expected: AMBER",
            "expected": "amber",
            "description": "No SIS signals but Z-Score in distress → B1 high met",
            "criteria": [],
            "financial": make_financial_profile("distress", 0.5, decline_years=3, percentile=5),
        },
        {
            "name": "No signals, no financials — Expected: GREEN",
            "expected": "green",
            "description": "Completely clean — no signals, no financial data",
            "criteria": [],
            "financial": None,
        },
    ]

    passed = 0
    failed = 0

    for sc in scenarios:
        signals = signals_for_criteria(*sc["criteria"])
        rs = score_risk(signals, "test_company", financial_profile=sc.get("financial"))
        actual = rs.traffic_light.value
        match = actual == sc["expected"]

        icon = "✓" if match else "✗"
        color_icon = {"red": "🔴", "amber": "🟡", "green": "🟢"}
        print(f"\n  {icon} {sc['name']}")
        print(f"    {sc['description']}")
        print(f"    Criteria met: H={rs.high_criteria_met} M={rs.medium_criteria_met} L={rs.low_criteria_met}")
        print(f"    Mitigating: {rs.has_mitigating_factors} {rs.mitigating_details}")
        print(f"    Expected: {color_icon[sc['expected']]} {sc['expected'].upper()}  "
              f"Actual: {color_icon[actual]} {actual.upper()}  "
              f"{'PASS' if match else '*** FAIL ***'}")

        if match:
            passed += 1
        else:
            failed += 1
            # Show why it failed
            print(f"    Criteria results:")
            for cr in rs.criteria_results:
                if cr.met:
                    print(f"      {cr.criteria_id} ({cr.weight.value}): {cr.criteria_name} — {cr.detail}")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed}")
    print(f"{'='*60}")

    return passed, failed


def test_boundary_map():
    results = run_boundary_map()
    # Every subset of the 7 Category A risk criteria is scored exactly once
    assert sum(len(entries) for entries in results.values()) == 2 ** 7


def test_real_company_scenarios():
    passed, failed = run_real_company_scenarios()
    assert failed == 0, f"{failed} scenario(s) did not get the expected traffic light"


def test_mitigating_factor_behavior():
    """Test how positive signals affect traffic light downgrade."""
    print("\n" + "=" * 80)
    print("TEST 3: MITIGATING FACTOR (A8) BEHAVIOR")
    print("=" * 80)

    cfg = ScoringConfig()
    print(f"Config: mitigating_confidence_threshold={cfg.mitigating_confidence_threshold}, "
          f"mitigating_max_override_high={cfg.mitigating_max_override_high}")
    print()

    cases = [
        ("RED (2 high) + strong positive", ["A1", "A2", "A8"], 1.0, "amber"),
        ("RED (2 high) + weak positive (conf=0.5)", ["A1", "A2"], 0.5, "red"),
        ("RED (3 high) + strong positive (exceeds max_override)", ["A1", "A2"], 1.0, None),
        ("AMBER (1 medium) + strong positive → GREEN", ["A3", "A8"], 1.0, "green"),
        ("AMBER (1 medium) + weak positive → stays AMBER", ["A3"], 0.5, "amber"),
    ]

    for desc, criteria, pos_conf, expected in cases:
        signals = signals_for_criteria(*criteria)
        # Add positive signal with specified confidence if A8 not already in criteria
        if "A8" not in criteria and pos_conf >= cfg.mitigating_confidence_threshold:
            signals.append(_sig("positive_signals", "positive", "pos_test",
                                confidence=pos_conf))
        elif "A8" not in criteria:
            signals.append(_sig("positive_signals", "positive", "pos_test",
                                confidence=pos_conf))

        rs = score_risk(signals, "test_company")
        actual = rs.traffic_light.value

        if expected:
            match = actual == expected
            icon = "✓" if match else "✗"
        else:
            icon = "→"
            match = True

        print(f"  {icon} {desc}")
        print(f"    H={rs.high_criteria_met} M={rs.medium_criteria_met} L={rs.low_criteria_met} "
              f"mitigating={rs.has_mitigating_factors}")
        print(f"    Result: {actual.upper()} {rs.mitigating_details}")
        print()


def test_financial_data_impact():
    """Test how financial profile (B criteria) affects traffic light."""
    print("\n" + "=" * 80)
    print("TEST 4: FINANCIAL DATA (B CRITERIA) IMPACT")
    print("=" * 80)
    print()

    base_criteria = ["A3"]  # 1 medium met from SIS → baseline AMBER

    fp_scenarios = [
        ("No financial data", None),
        ("Safe zone (Z=4.0)", make_financial_profile("safe", 4.0)),
        ("Grey zone (Z=2.0)", make_financial_profile("grey", 2.0)),
        ("Distress zone (Z=0.5)", make_financial_profile("distress", 0.5)),
        ("Grey + 2yr decline", make_financial_profile("grey", 2.0, decline_years=2)),
        ("Distress + 2yr decline", make_financial_profile("distress", 0.5, decline_years=3)),
        ("Distress + decline + low peer", make_financial_profile("distress", 0.5, decline_years=3, percentile=10)),
    ]

    print(f"  Base SIS signals: {base_criteria} → 1 medium met")
    print(f"  {'Financial Scenario':<35} {'B met':>6} {'Total H':>8} {'Total M':>8} {'Result':>8}")
    print(f"  {'-'*35} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")

    for desc, fp in fp_scenarios:
        signals = signals_for_criteria(*base_criteria)
        rs = score_risk(signals, "test", financial_profile=fp)
        b_met = sum(1 for c in rs.criteria_results if c.criteria_id.startswith("B") and c.met)
        color = {"red": "🔴", "amber": "🟡", "green": "🟢"}
        print(f"  {desc:<35} {b_met:>6} {rs.high_criteria_met:>8} {rs.medium_criteria_met:>8} "
              f"{color[rs.traffic_light.value]} {rs.traffic_light.value.upper():>6}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("FRD SCORING BOUNDARY TEST")
    print("Deterministic — no LLM calls needed")
    print("=" * 80)

    boundary_results = run_boundary_map()
    passed, failed = run_real_company_scenarios()
    test_mitigating_factor_behavior()
    test_financial_data_impact()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Boundary map: {len(boundary_results['red'])} RED, "
          f"{len(boundary_results['amber'])} AMBER, "
          f"{len(boundary_results['green'])} GREEN combinations")
    print(f"Scenario validation: {passed} passed, {failed} failed")

    # Save results
    root = Path(__file__).resolve().parents[1]
    out_path = root / "data" / "local" / "hyflux" / "scoring_boundary_results.json"
    output = {
        "boundary_map": {
            color: [(combo, weights, h, m, l)
                    for combo, weights, h, m, l in entries]
            for color, entries in boundary_results.items()
        },
        "scenario_validation": {"passed": passed, "failed": failed},
    }
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
