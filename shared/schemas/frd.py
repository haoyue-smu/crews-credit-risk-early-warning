"""FRD (Fusion & Risk Decisioning) output schemas — consumed by reporting and downstream systems."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TrafficLight(str, Enum):
    red = "red"
    amber = "amber"
    green = "green"


class CriteriaWeight(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    mitigating = "mitigating"


class CriteriaResult(BaseModel):
    """Result of evaluating a single binary criterion."""

    criteria_id: str  # e.g. "A1", "B2"
    criteria_name: str
    met: bool
    weight: CriteriaWeight
    detail: str  # e.g. "3 signals: debt_restructuring, payment_default, ..."
    contributing_signal_count: int = 0


class ScoringConfig(BaseModel):
    """Configurable thresholds — tuned via backtesting."""

    high_criteria_for_red: int = 2          # ≥N high-weight criteria met → Red (was 1)
    medium_criteria_for_red: int = 3        # ≥N medium-weight criteria met → Red
    medium_criteria_for_amber: int = 1      # ≥N medium-weight criteria met → Amber
    low_criteria_for_amber: int = 3         # ≥N low-weight criteria met → Amber
    mitigating_confidence_threshold: float = 0.65  # positive signals need ≥ this confidence (was 0.7)
    mitigating_max_override_high: int = 2   # can downgrade if ≤N high criteria met (was 1)
    min_signal_confidence: float = 0.5      # Category A signals below this confidence are ignored


class ZScoreZone(str, Enum):
    safe = "safe"  # Z > 2.99
    grey = "grey"  # 1.81 <= Z <= 2.99
    distress = "distress"  # Z < 1.81


class AltmanZScore(BaseModel):
    """Single-period Altman Z-Score computed by FIS."""

    score: float
    zone: ZScoreZone
    working_capital_to_total_assets: float
    retained_earnings_to_total_assets: float
    ebit_to_total_assets: float
    equity_market_value_to_total_liabilities: float
    sales_to_total_assets: float
    reporting_period: str
    statement_date: date


class ZScoreTrend(BaseModel):
    """Year-over-year Z-Score history for trend analysis."""

    periods: list[AltmanZScore]
    consecutive_decline_years: int
    trend_direction: str


class PeerComparison(BaseModel):
    """Industry peer Z-Score benchmarks."""

    industry: str
    peer_count: int
    peer_median_zscore: float
    peer_25th_percentile: float
    peer_75th_percentile: float
    company_percentile_rank: float


class KeyFinancialRatios(BaseModel):
    """Supplementary ratios for report context (not used in scoring)."""

    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    net_profit_margin: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    revenue_yoy_growth: Optional[float] = None


class FinancialProfile(BaseModel):
    """FIS output → FRD input. One per company per assessment."""

    company_id: str
    latest_zscore: AltmanZScore
    zscore_trend: ZScoreTrend
    peer_comparison: Optional[PeerComparison] = None
    key_ratios: Optional[KeyFinancialRatios] = None
    data_staleness_days: int
    source_filing: str


class RiskScore(BaseModel):
    """Output of the score_risk node."""

    company_id: str
    traffic_light: TrafficLight
    criteria_results: list[CriteriaResult]
    high_criteria_met: int
    medium_criteria_met: int
    low_criteria_met: int
    has_mitigating_factors: bool
    mitigating_details: list[str]
    flags: list[str]
    scoring_config_used: ScoringConfig
    financial_data_available: bool = False


class FRDOutput(BaseModel):
    """Complete FRD output — for now just RiskScore, report added in Phase 3."""

    company_id: str
    traffic_light: TrafficLight
    risk_score: RiskScore
    report_narrative: Optional[str] = None
    financial_profile: Optional[FinancialProfile] = None
    metadata: dict = Field(default_factory=dict)
