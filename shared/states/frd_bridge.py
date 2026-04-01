"""Bridge functions for converting between FIS/RS CaseState and SIS/FRD PipelineState.

FIS and RS operate on AgentWorkerState (containing CaseState).
SIS and FRD operate on PipelineState (dict-based).

This module converts between the two schemas so all four subgraphs
can be chained through a single backend pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.states.case_state import CaseState


# ---------------------------------------------------------------------------
# RS → SIS: normalized documents bridge
# ---------------------------------------------------------------------------

def normalized_documents_to_pipeline_docs(case: "CaseState") -> list[dict[str, Any]]:
    """Convert CaseState.normalized_documents to PipelineState['documents'] format.

    RS produces DocumentInput objects in case.normalized_documents.
    SIS expects these serialized as plain dicts in state['documents'].
    """
    return [doc.model_dump(mode="json") for doc in case.normalized_documents]


# ---------------------------------------------------------------------------
# FIS → FRD: FinancialFeatures → FinancialProfile bridge
# ---------------------------------------------------------------------------

def financial_features_to_profile(case: "CaseState") -> dict[str, Any] | None:
    """Convert CaseState.financial_features (FIS output) to a FinancialProfile dict
    compatible with FRD's PipelineState['financial_profile'].

    Returns None if financial_features is absent or the Z-Score was not computed
    (FRD's FinancialProfile requires a valid Z-Score score value).
    """
    ff = case.financial_features
    if ff is None:
        return None

    z = ff.current_z_score
    if z is None or z.score is None:
        return None

    # --- Build AltmanZScore dict ---
    comps = z.components or {}

    # X4 key varies by formula: original uses market_cap, private/non-mfg use book_equity
    x4_value = (
        comps.get("X4_market_cap_to_liabilities")
        or comps.get("X4p_book_equity_to_liabilities")
        or 0.0
    )

    latest_zscore = {
        "score": z.score,
        "zone": z.zone.value,
        "working_capital_to_total_assets": comps.get("X1_working_capital_to_assets") or 0.0,
        "retained_earnings_to_total_assets": comps.get("X2_retained_earnings_to_assets") or 0.0,
        "ebit_to_total_assets": comps.get("X3_ebit_to_assets") or 0.0,
        "equity_market_value_to_total_liabilities": x4_value,
        "sales_to_total_assets": comps.get("X5_revenue_to_assets") or 0.0,
        "reporting_period": z.period_label or f"FY{z.fiscal_year or 'unknown'}",
        "statement_date": date.today().isoformat(),
    }

    # --- Build ZScoreTrend dict ---
    historical = ff.historical_z_scores or []
    trend_periods = []
    for hz in historical:
        if hz.score is None:
            continue
        hcomps = hz.components or {}
        hx4 = (
            hcomps.get("X4_market_cap_to_liabilities")
            or hcomps.get("X4p_book_equity_to_liabilities")
            or 0.0
        )
        trend_periods.append({
            "score": hz.score,
            "zone": hz.zone.value,
            "working_capital_to_total_assets": hcomps.get("X1_working_capital_to_assets") or 0.0,
            "retained_earnings_to_total_assets": hcomps.get("X2_retained_earnings_to_assets") or 0.0,
            "ebit_to_total_assets": hcomps.get("X3_ebit_to_assets") or 0.0,
            "equity_market_value_to_total_liabilities": hx4,
            "sales_to_total_assets": hcomps.get("X5_revenue_to_assets") or 0.0,
            "reporting_period": hz.period_label or f"FY{hz.fiscal_year or 'unknown'}",
            "statement_date": date.today().isoformat(),
        })

    # Compute consecutive decline years from historical scores (most recent first)
    all_scores = [z.score] + [p["score"] for p in trend_periods]
    consecutive_decline = 0
    for i in range(len(all_scores) - 1):
        if all_scores[i] < all_scores[i + 1]:
            consecutive_decline += 1
        else:
            break

    trend_direction = "stable"
    if len(all_scores) >= 2:
        if all_scores[0] < all_scores[-1]:
            trend_direction = "declining"
        elif all_scores[0] > all_scores[-1]:
            trend_direction = "improving"

    zscore_trend = {
        "periods": trend_periods,
        "consecutive_decline_years": consecutive_decline,
        "trend_direction": trend_direction,
    }

    # --- Build PeerComparison dict (optional) ---
    peer_dict = None
    pc = ff.peer_comparison
    if pc is not None and pc.industry_median_z is not None:
        # Approximate percentile rank: where does the company's Z sit
        # between the distress threshold (≈0th pct) and safe threshold (≈100th pct)?
        safe_t = pc.benchmark_z_safe or 2.9
        dist_t = pc.benchmark_z_distress or 1.23
        span = safe_t - dist_t
        if span > 0:
            raw_rank = (z.score - dist_t) / span * 100
            pct_rank = max(0.0, min(100.0, round(raw_rank, 1)))
        else:
            pct_rank = 50.0

        peer_dict = {
            "industry": pc.industry_sector,
            "peer_count": 100,  # static benchmark approximation
            "peer_median_zscore": pc.industry_median_z,
            "peer_25th_percentile": dist_t,
            "peer_75th_percentile": safe_t,
            "company_percentile_rank": pct_rank,
        }

    # --- Build KeyFinancialRatios dict (optional) ---
    ratios_dict = None
    r = ff.ratios
    if r is not None:
        ratios_dict = {
            "debt_to_equity": r.debt_to_equity,
            "current_ratio": r.current_ratio,
            "interest_coverage": r.interest_coverage,
            "net_profit_margin": r.net_margin,
            "operating_cash_flow": ff.cash_flow.operating_cash_flow if ff.cash_flow else None,
            "revenue_yoy_growth": None,  # not tracked in FIS currently
        }

    # --- Estimate data staleness ---
    staleness_days = 180  # default if fiscal year unknown
    fiscal_year = ff.period.fiscal_year if ff.period else None
    if fiscal_year:
        current_year = datetime.now().year
        staleness_days = max(0, (current_year - fiscal_year) * 365)

    # --- Source filing reference ---
    source_filing = "annual_report"
    if case.uploaded_financial_documents:
        source_filing = case.uploaded_financial_documents[0].filename

    return {
        "company_id": case.company.company_id,
        "latest_zscore": latest_zscore,
        "zscore_trend": zscore_trend,
        "peer_comparison": peer_dict,
        "key_ratios": ratios_dict,
        "data_staleness_days": staleness_days,
        "source_filing": source_filing,
    }
