"""FRD score_risk node — deterministic Category A (SIS) + Category B (FIS) criteria."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from shared.schemas.frd import (
    CriteriaResult,
    CriteriaWeight,
    FinancialProfile,
    RiskScore,
    ScoringConfig,
    TrafficLight,
    ZScoreZone,
)

SignalDict = Dict[str, object]

# --- Category A: signal matchers ---


def _match_a1_financial_distress_high_clear(signals: Sequence[SignalDict]) -> List[SignalDict]:
    return [
        s
        for s in signals
        if str(s.get("event_type", "")) == "financial_distress_signals"
        and str(s.get("severity", "")) == "high"
        and s.get("ambiguous") is False
    ]


def _match_a2_legal_regulatory(signals: Sequence[SignalDict]) -> List[SignalDict]:
    matched = [
        s
        for s in signals
        if str(s.get("event_type", "")) == "legal_regulatory"
        and str(s.get("severity", "")) in ("high", "medium")
    ]
    return matched if len(matched) >= 2 else []


def _match_a3_management_instability(signals: Sequence[SignalDict]) -> List[SignalDict]:
    m = [s for s in signals if str(s.get("event_type", "")) == "management_governance"]
    return m if len(m) >= 2 else []


def _match_a4_operational(signals: Sequence[SignalDict]) -> List[SignalDict]:
    matched = [
        s
        for s in signals
        if str(s.get("event_type", "")) == "operational_issues"
        and str(s.get("severity", "")) in ("high", "medium")
    ]
    return matched if len(matched) >= 2 else []


def _match_a5_reputation_negative_trend(signals: Sequence[SignalDict]) -> List[SignalDict]:
    m = [
        s
        for s in signals
        if str(s.get("event_type", "")) == "reputation_sentiment"
        and str(s.get("severity", "")) in ("high", "medium")
    ]
    return m if len(m) >= 2 else []


def _match_a6_sector_macro(signals: Sequence[SignalDict]) -> List[SignalDict]:
    return [s for s in signals if str(s.get("event_type", "")) == "market_industry_risks"]


def _match_a7_disputed(signals: Sequence[SignalDict]) -> List[SignalDict]:
    return [s for s in signals if str(s.get("conflict_status", "")) == "disputed"]


def _match_a8_positive_clear(signals: Sequence[SignalDict]) -> List[SignalDict]:
    return [
        s
        for s in signals
        if str(s.get("event_type", "")) == "positive_signals" and s.get("ambiguous") is False
    ]


@dataclass(frozen=True)
class CategoryACriterionDef:
    """Data-driven Category A criterion."""

    criteria_id: str
    criteria_name: str
    weight: CriteriaWeight
    matcher: Callable[[Sequence[SignalDict]], List[SignalDict]]


CATEGORY_A_CRITERIA: tuple[CategoryACriterionDef, ...] = (
    CategoryACriterionDef("A1", "Financial distress signal detected", CriteriaWeight.high, _match_a1_financial_distress_high_clear),
    CategoryACriterionDef("A2", "Legal/regulatory risk detected", CriteriaWeight.high, _match_a2_legal_regulatory),
    CategoryACriterionDef("A3", "Management instability detected", CriteriaWeight.medium, _match_a3_management_instability),
    CategoryACriterionDef("A4", "Operational issues detected", CriteriaWeight.medium, _match_a4_operational),
    CategoryACriterionDef("A5", "Negative reputation trend", CriteriaWeight.low, _match_a5_reputation_negative_trend),
    CategoryACriterionDef("A6", "Sector/macro risk detected", CriteriaWeight.low, _match_a6_sector_macro),
    CategoryACriterionDef("A7", "Disputed signals present", CriteriaWeight.low, _match_a7_disputed),
    CategoryACriterionDef("A8", "Positive signals present", CriteriaWeight.mitigating, _match_a8_positive_clear),
)

# --- Category B: static metadata + ordered evaluators (B2 depends on B1) ---

B_CRITERIA_SPECS: tuple[tuple[str, str, CriteriaWeight], ...] = (
    ("B1", "Financial distress zone", CriteriaWeight.high),
    ("B2", "Financial grey zone", CriteriaWeight.medium),
    ("B3", "Deteriorating financial health", CriteriaWeight.medium),
    ("B4", "Peer comparison anomaly", CriteriaWeight.medium),
)


def _eval_b1(fp: FinancialProfile, state: Dict[str, Any]) -> CriteriaResult:
    lz = fp.latest_zscore
    met = lz.zone == ZScoreZone.distress
    state["b1_met"] = met
    detail = f"Z-Score: {lz.score:.2f}, zone: {lz.zone.value}"
    if met:
        detail = f"Z-Score: {lz.score:.2f}, zone: distress"
    return CriteriaResult(
        criteria_id="B1",
        criteria_name="Financial distress zone",
        met=met,
        weight=CriteriaWeight.high,
        detail=detail,
        contributing_signal_count=1 if met else 0,
    )


def _eval_b2(fp: FinancialProfile, state: Dict[str, Any]) -> CriteriaResult:
    lz = fp.latest_zscore
    b1_met = bool(state.get("b1_met"))
    if b1_met:
        return CriteriaResult(
            criteria_id="B2",
            criteria_name="Financial grey zone",
            met=False,
            weight=CriteriaWeight.medium,
            detail="in distress, not grey",
            contributing_signal_count=0,
        )
    met = lz.zone == ZScoreZone.grey
    if met:
        detail = f"Z-Score: {lz.score:.2f}, zone: grey"
    else:
        detail = f"Z-Score: {lz.score:.2f}, zone: {lz.zone.value}"
    return CriteriaResult(
        criteria_id="B2",
        criteria_name="Financial grey zone",
        met=met,
        weight=CriteriaWeight.medium,
        detail=detail,
        contributing_signal_count=1 if met else 0,
    )


def _eval_b3(fp: FinancialProfile, state: Dict[str, Any]) -> CriteriaResult:
    y = fp.zscore_trend.consecutive_decline_years
    met = y >= 2
    detail = f"{y} consecutive years declining" if met else f"{y} consecutive years (below threshold)"
    return CriteriaResult(
        criteria_id="B3",
        criteria_name="Deteriorating financial health",
        met=met,
        weight=CriteriaWeight.medium,
        detail=detail,
        contributing_signal_count=1 if met else 0,
    )


def _eval_b4(fp: FinancialProfile, state: Dict[str, Any]) -> CriteriaResult:
    pc = fp.peer_comparison
    if pc is None:
        return CriteriaResult(
            criteria_id="B4",
            criteria_name="Peer comparison anomaly",
            met=False,
            weight=CriteriaWeight.medium,
            detail="peer comparison not available",
            contributing_signal_count=0,
        )
    met = pc.company_percentile_rank < 25
    pr = pc.company_percentile_rank
    detail = f"percentile rank: {pr}, bottom quartile" if met else f"percentile rank: {pr}"
    return CriteriaResult(
        criteria_id="B4",
        criteria_name="Peer comparison anomaly",
        met=met,
        weight=CriteriaWeight.medium,
        detail=detail,
        contributing_signal_count=1 if met else 0,
    )


B_EVALUATORS: tuple[Callable[[FinancialProfile, Dict[str, Any]], CriteriaResult], ...] = (
    _eval_b1,
    _eval_b2,
    _eval_b3,
    _eval_b4,
)


def _evaluate_category_b(fp: Optional[FinancialProfile]) -> List[CriteriaResult]:
    if fp is None:
        return [
            CriteriaResult(
                criteria_id=sid,
                criteria_name=name,
                met=False,
                weight=w,
                detail="no financial profile",
                contributing_signal_count=0,
            )
            for sid, name, w in B_CRITERIA_SPECS
        ]
    state: Dict[str, Any] = {}
    return [ev(fp, state) for ev in B_EVALUATORS]


def _format_criteria_detail(matched: List[SignalDict]) -> str:
    if not matched:
        return "0 signals"
    n = len(matched)
    subtypes: List[str] = []
    seen: set[str] = set()
    for s in matched:
        st = str(s.get("event_subtype", "") or "").strip()
        if st and st not in seen:
            seen.add(st)
            subtypes.append(st)
    if not subtypes:
        return f"{n} signals"
    return f"{n} signals: {', '.join(subtypes)}"


def _evaluate_category_a(signals: List[SignalDict], cfg: ScoringConfig) -> List[CriteriaResult]:
    # Drop low-confidence signals before any criterion is evaluated
    confident_signals = [
        s for s in signals
        if float(s.get("confidence", 0.0) or 0.0) >= cfg.min_signal_confidence
    ]
    results: List[CriteriaResult] = []
    for spec in CATEGORY_A_CRITERIA:
        matched = spec.matcher(confident_signals)
        met = len(matched) > 0
        results.append(
            CriteriaResult(
                criteria_id=spec.criteria_id,
                criteria_name=spec.criteria_name,
                met=met,
                weight=spec.weight,
                detail=_format_criteria_detail(matched),
                contributing_signal_count=len(matched),
            )
        )
    return results


def _count_met_by_weight(criteria_results: Sequence[CriteriaResult]) -> tuple[int, int, int]:
    high = sum(1 for c in criteria_results if c.weight == CriteriaWeight.high and c.met)
    medium = sum(1 for c in criteria_results if c.weight == CriteriaWeight.medium and c.met)
    low = sum(1 for c in criteria_results if c.weight == CriteriaWeight.low and c.met)
    return high, medium, low


def _base_traffic_light(
    high_met: int,
    medium_met: int,
    low_met: int,
    config: ScoringConfig,
) -> TrafficLight:
    if high_met >= config.high_criteria_for_red or medium_met >= config.medium_criteria_for_red:
        return TrafficLight.red
    if medium_met >= config.medium_criteria_for_amber or low_met >= config.low_criteria_for_amber:
        return TrafficLight.amber
    return TrafficLight.green


def _criteria_by_id(results: Sequence[CriteriaResult]) -> Dict[str, CriteriaResult]:
    return {c.criteria_id: c for c in results}


def _positive_non_ambiguous_signals(signals: Sequence[SignalDict]) -> List[SignalDict]:
    return [
        s
        for s in signals
        if str(s.get("event_type", "")) == "positive_signals" and s.get("ambiguous") is False
    ]


def _apply_mitigating(
    base: TrafficLight,
    signals: Sequence[SignalDict],
    criteria_results: List[CriteriaResult],
    high_met: int,
    config: ScoringConfig,
) -> tuple[TrafficLight, List[str]]:
    by_id = _criteria_by_id(criteria_results)
    a8 = by_id.get("A8")
    details: List[str] = []
    if not a8 or not a8.met:
        return base, details

    positives = _positive_non_ambiguous_signals(signals)
    if not positives:
        return base, details

    confs = [float(s.get("confidence", 0.0) or 0.0) for s in positives]
    avg_conf = sum(confs) / len(confs)

    if avg_conf < config.mitigating_confidence_threshold:
        return base, details

    if base == TrafficLight.red:
        if high_met <= config.mitigating_max_override_high:
            details.append(
                f"{len(positives)} positive signals with avg confidence {avg_conf:.2f} — downgraded Red → Amber"
            )
            return TrafficLight.amber, details
        details.append(
            f"positive signals present but cannot override ({high_met} high criteria met; max override {config.mitigating_max_override_high})"
        )
        return base, details

    if base == TrafficLight.amber:
        details.append(
            f"{len(positives)} positive signals with avg confidence {avg_conf:.2f} — downgraded Amber → Green"
        )
        return TrafficLight.green, details

    return base, details


def _build_flags(
    criteria_results: Sequence[CriteriaResult],
    a6_met: bool,
    financial_profile: FinancialProfile | None,
) -> List[str]:
    flags: List[str] = []
    if financial_profile is None:
        flags.append("financial_data_unavailable")
    else:
        if financial_profile.peer_comparison is None:
            flags.append("peer_data_unavailable")
        if financial_profile.data_staleness_days > 365:
            flags.append("financial_data_stale")

    by_id = _criteria_by_id(criteria_results)
    other_risk_met = any(
        by_id[cid].met
        for cid in ("A1", "A2", "A3", "A4", "A5", "A7")
        if cid in by_id
    )
    if a6_met and other_risk_met:
        flags.append("sector_macro_overlap")
    if by_id.get("A7") and by_id["A7"].met:
        flags.append("disputed_signals_require_attention")
    return flags


def _parse_financial_profile(financial_profile: dict | None) -> FinancialProfile | None:
    if financial_profile is None:
        return None
    return FinancialProfile.model_validate(financial_profile)


def score_risk(
    signals: List[dict],
    company_id: str,
    config: ScoringConfig | None = None,
    financial_profile: dict | None = None,
) -> RiskScore:
    """
    Deterministic Category A + B risk scoring.

    Args:
        signals: SIS signal dicts.
        company_id: Obligor identifier.
        config: Thresholds; defaults if omitted.
        financial_profile: FIS ``FinancialProfile`` as a dict (e.g. JSON); if None, B1–B4 are not met
            and ``financial_data_unavailable`` is flagged.
    """
    cfg = config or ScoringConfig()
    signal_rows: List[SignalDict] = [dict(s) for s in signals]
    fp = _parse_financial_profile(financial_profile)

    results_a = _evaluate_category_a(signal_rows, cfg)
    results_b = _evaluate_category_b(fp)
    criteria_results = results_a + results_b

    high_met, medium_met, low_met = _count_met_by_weight(criteria_results)

    base = _base_traffic_light(high_met, medium_met, low_met, cfg)
    final_light, mitigating_details = _apply_mitigating(
        base, signal_rows, criteria_results, high_met, cfg
    )

    by_id = _criteria_by_id(criteria_results)
    a6_met = bool(by_id.get("A6") and by_id["A6"].met)
    flags = _build_flags(criteria_results, a6_met, fp)

    a8_met = bool(by_id.get("A8") and by_id["A8"].met)

    return RiskScore(
        company_id=company_id,
        traffic_light=final_light,
        criteria_results=criteria_results,
        high_criteria_met=high_met,
        medium_criteria_met=medium_met,
        low_criteria_met=low_met,
        has_mitigating_factors=a8_met,
        mitigating_details=mitigating_details,
        flags=flags,
        scoring_config_used=cfg,
        financial_data_available=fp is not None,
    )
