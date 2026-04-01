"""Deterministic financial ratio and Altman Z-Score computation.

All three Altman variants are implemented:
  - Original Z-Score (1968): public manufacturing companies — uses market cap
  - Z' Score (1983): private companies — uses book value of equity
  - Z'' Score (2000): service / non-manufacturing — 4-factor, no asset turnover

The correct formula is selected based on CompanyProfile.company_type,
CompanyProfile.is_manufacturing, and whether market_cap is present.

This module is purely deterministic — no LLM calls.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.states.case_state import (
        BalanceSheetMetrics,
        CashFlowMetrics,
        FinancialRatios,
        IncomeStatementMetrics,
        PeerComparison,
        ZScoreFormula,
        ZScoreResult,
        ZScoreZone,
    )


# ---------------------------------------------------------------------------
# Zone classification helpers
# ---------------------------------------------------------------------------

def _classify_zone(score: float, formula: "ZScoreFormula") -> "ZScoreZone":
    from shared.states.case_state import ZScoreFormula, ZScoreZone

    thresholds = _get_thresholds(formula)
    if score >= thresholds["safe"]:
        return ZScoreZone.safe
    elif score >= thresholds["distress"]:
        return ZScoreZone.grey
    else:
        return ZScoreZone.distress


def _get_thresholds(formula: "ZScoreFormula") -> dict[str, float]:
    from shared.states.case_state import ZScoreFormula

    if formula == ZScoreFormula.original_public:
        return {"safe": 2.99, "distress": 1.81}
    elif formula == ZScoreFormula.revised_private:
        return {"safe": 2.90, "distress": 1.23}
    else:  # non_manufacturing Z''
        return {"safe": 2.60, "distress": 1.10}


def _select_formula(
    company_type: str,
    is_manufacturing: bool,
    market_cap: float | None,
) -> "ZScoreFormula":
    """Select the most appropriate Altman formula for this company."""
    from shared.states.case_state import ZScoreFormula

    if not is_manufacturing:
        return ZScoreFormula.non_manufacturing
    if company_type == "public" and market_cap is not None and market_cap > 0:
        return ZScoreFormula.original_public
    return ZScoreFormula.revised_private


# ---------------------------------------------------------------------------
# Ratio computation
# ---------------------------------------------------------------------------

def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Division that returns None rather than raising on None/zero."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    result = numerator / denominator
    # Guard against inf/nan blowing up downstream
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def compute_derived_values(
    bs: "BalanceSheetMetrics",
    is_: "IncomeStatementMetrics",
) -> tuple[float | None, float | None]:
    """Compute working_capital and total_debt if not already set.

    Returns (working_capital, total_debt).
    """
    working_capital = bs.working_capital
    if working_capital is None and bs.current_assets is not None and bs.current_liabilities is not None:
        working_capital = bs.current_assets - bs.current_liabilities

    total_debt = bs.total_debt
    if total_debt is None:
        # Approximate: long_term_debt + current_liabilities as proxy
        ltd = bs.long_term_debt or 0.0
        cl = bs.current_liabilities or 0.0
        if bs.long_term_debt is not None or bs.current_liabilities is not None:
            total_debt = ltd + cl

    return working_capital, total_debt


def compute_ebitda(is_: "IncomeStatementMetrics") -> float | None:
    """Derive EBITDA if not explicitly provided."""
    if is_.ebitda is not None:
        return is_.ebitda
    if is_.operating_income is not None and is_.depreciation_amortization is not None:
        return is_.operating_income + is_.depreciation_amortization
    return None


def compute_ratios(
    bs: "BalanceSheetMetrics",
    is_: "IncomeStatementMetrics",
    cf: "CashFlowMetrics",
    working_capital: float | None,
    total_debt: float | None,
    ebitda: float | None,
) -> "FinancialRatios":
    """Compute all standard financial ratios deterministically."""
    from shared.states.case_state import FinancialRatios

    notes: list[str] = []
    r = FinancialRatios()

    net_debt = None
    if total_debt is not None and bs.cash_and_equivalents is not None:
        net_debt = total_debt - bs.cash_and_equivalents

    liquid_assets: float | None = None
    if bs.current_assets is not None:
        inv = bs.inventory or 0.0
        liquid_assets = bs.current_assets - inv

    # --- Liquidity ---
    r.current_ratio = safe_div(bs.current_assets, bs.current_liabilities)
    if r.current_ratio is None:
        notes.append("current_ratio: missing current_assets or current_liabilities")

    r.quick_ratio = safe_div(liquid_assets, bs.current_liabilities)
    r.cash_ratio = safe_div(bs.cash_and_equivalents, bs.current_liabilities)

    # --- Leverage ---
    r.debt_to_equity = safe_div(total_debt, bs.total_equity)
    if r.debt_to_equity is None:
        notes.append("debt_to_equity: missing total_debt or total_equity")

    r.debt_to_assets = safe_div(total_debt, bs.total_assets)
    r.net_debt_to_ebitda = safe_div(net_debt, ebitda)

    ebit = is_.operating_income
    r.interest_coverage = safe_div(ebit, is_.interest_expense)
    if r.interest_coverage is None and is_.interest_expense is not None:
        notes.append("interest_coverage: missing operating_income (EBIT)")

    # --- Profitability ---
    r.gross_margin = safe_div(is_.gross_profit, is_.revenue)
    r.operating_margin = safe_div(is_.operating_income, is_.revenue)
    r.net_margin = safe_div(is_.net_income, is_.revenue)
    r.ebitda_margin = safe_div(ebitda, is_.revenue)
    r.return_on_assets = safe_div(is_.net_income, bs.total_assets)
    r.return_on_equity = safe_div(is_.net_income, bs.total_equity)

    # --- Efficiency ---
    r.asset_turnover = safe_div(is_.revenue, bs.total_assets)

    r.computation_notes = notes
    return r


# ---------------------------------------------------------------------------
# Altman Z-Score
# ---------------------------------------------------------------------------

def compute_z_score(
    bs: "BalanceSheetMetrics",
    is_: "IncomeStatementMetrics",
    company_type: str,
    is_manufacturing: bool,
    market_cap: float | None,
    fiscal_year: int | None,
    period_label: str | None,
    working_capital: float | None,
    total_debt: float | None,
) -> "ZScoreResult":
    """Compute the appropriate Altman Z-Score variant.

    Returns a ZScoreResult with score, zone, formula used, and component values.
    If insufficient data, returns a result with score=None and zone=unknown.
    """
    from shared.states.case_state import ZScoreFormula, ZScoreResult, ZScoreZone

    formula = _select_formula(company_type, is_manufacturing, market_cap)
    thresholds = _get_thresholds(formula)
    notes: list[str] = []
    components: dict[str, float | None] = {}

    # Shared components across all formulas
    total_assets = bs.total_assets

    # X1: Working Capital / Total Assets
    x1 = safe_div(working_capital, total_assets)
    components["X1_working_capital_to_assets"] = x1
    if x1 is None:
        notes.append("X1 (working capital / total assets): missing data")

    # X2: Retained Earnings / Total Assets
    x2 = safe_div(bs.retained_earnings, total_assets)
    components["X2_retained_earnings_to_assets"] = x2
    if x2 is None:
        notes.append("X2 (retained earnings / total assets): missing retained_earnings or total_assets")

    # X3: EBIT / Total Assets
    ebit = is_.operating_income
    x3 = safe_div(ebit, total_assets)
    components["X3_ebit_to_assets"] = x3
    if x3 is None:
        notes.append("X3 (EBIT / total assets): missing operating_income or total_assets")

    score: float | None = None

    if formula == ZScoreFormula.original_public:
        # X4: Market Cap / Book Value of Total Liabilities
        x4 = safe_div(market_cap, bs.total_liabilities)
        components["X4_market_cap_to_liabilities"] = x4
        if x4 is None:
            notes.append("X4 (market cap / total liabilities): missing market_cap or total_liabilities")

        # X5: Revenue / Total Assets
        x5 = safe_div(is_.revenue, total_assets)
        components["X5_revenue_to_assets"] = x5
        if x5 is None:
            notes.append("X5 (revenue / total assets): missing revenue or total_assets")

        if all(v is not None for v in [x1, x2, x3, x4, x5]):
            score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        else:
            notes.append("Z-Score (Original) could not be fully computed due to missing components.")

    elif formula == ZScoreFormula.revised_private:
        # X4': Book Value of Equity / Book Value of Total Liabilities
        book_equity = bs.total_equity
        x4p = safe_div(book_equity, bs.total_liabilities)
        components["X4p_book_equity_to_liabilities"] = x4p
        if x4p is None:
            notes.append("X4' (book equity / total liabilities): missing total_equity or total_liabilities")

        # X5: Revenue / Total Assets
        x5 = safe_div(is_.revenue, total_assets)
        components["X5_revenue_to_assets"] = x5
        if x5 is None:
            notes.append("X5 (revenue / total assets): missing revenue or total_assets")

        if all(v is not None for v in [x1, x2, x3, x4p, x5]):
            score = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4p + 0.998 * x5
        else:
            notes.append("Z' Score could not be fully computed due to missing components.")

    else:  # non_manufacturing Z''
        # X4': Book Value of Equity / Book Value of Total Liabilities
        book_equity = bs.total_equity
        x4p = safe_div(book_equity, bs.total_liabilities)
        components["X4p_book_equity_to_liabilities"] = x4p
        if x4p is None:
            notes.append("X4' (book equity / total liabilities): missing total_equity or total_liabilities")

        if all(v is not None for v in [x1, x2, x3, x4p]):
            score = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4p
        else:
            notes.append("Z'' Score could not be fully computed due to missing components.")

    zone = ZScoreZone.unknown
    if score is not None:
        score = round(score, 4)
        zone = _classify_zone(score, formula)

    return ZScoreResult(
        fiscal_year=fiscal_year,
        period_label=period_label,
        score=score,
        zone=zone,
        formula_used=formula,
        components=components,
        zone_thresholds=thresholds,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------

def build_peer_comparison(
    industry_sector: str | None,
    formula_used: "ZScoreFormula",
) -> "PeerComparison":
    """Build a PeerComparison object from the static benchmark table."""
    from shared.states.case_state import PeerComparison, ZScoreFormula
    from shared.states.industry_benchmarks import get_benchmark

    bm = get_benchmark(industry_sector)
    notes: list[str] = [bm.get("note", "")]

    if bm.get("median_z") is None:
        notes.append(
            "Z-Score benchmark not applicable for this sector. "
            "Interpret credit risk using sector-specific metrics instead."
        )

    return PeerComparison(
        industry_sector=bm.get("display_name", industry_sector or "Unknown"),
        formula_used=formula_used,
        industry_median_z=bm.get("median_z"),
        industry_safe_zone_pct=bm.get("industry_safe_zone_pct"),
        industry_grey_zone_pct=bm.get("industry_grey_zone_pct"),
        industry_distress_zone_pct=bm.get("industry_distress_zone_pct"),
        benchmark_z_safe=bm.get("benchmark_z_safe"),
        benchmark_z_distress=bm.get("benchmark_z_distress"),
        data_source="static_benchmark_v1",
        notes=[n for n in notes if n],
    )
