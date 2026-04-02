"""Central case state model for the credit analysis pipeline.

This is the single-source-of-truth schema that flows through every subgraph.
Nodes read from and write back to fields on CaseState, which is held inside
the LangGraph AgentWorkerState TypedDict.

Key additions over the original version:
  - Structured financial metrics (IS, BS, CF) instead of opaque dicts
  - FinancialRatios with named fields
  - Altman Z-Score results (current + historical) with zone classification
  - Peer comparison against industry benchmarks
  - FinancialPeriod metadata (fiscal year, quarter, currency)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.schemas.documents import DocumentInput


# ---------------------------------------------------------------------------
# Company Profile
# ---------------------------------------------------------------------------

class CompanyProfile(BaseModel):
    company_id: str
    company_name: str
    company_type: Literal["public", "private"]
    jurisdiction: str | None = None
    ticker: str | None = None
    isin: str | None = None
    website: str | None = None
    industry_sector: str | None = None
    is_manufacturing: bool = False
    market_cap: float | None = None   # USD, needed for original Z-Score


# ---------------------------------------------------------------------------
# Uploaded / Parsed financial documents
# ---------------------------------------------------------------------------

class UploadedFinancialDocument(BaseModel):
    document_id: str
    filename: str
    file_type: Literal["xml", "xbrl", "pdf"]
    local_path: str
    uploaded_at: datetime
    document_role: Literal["annual_report", "quarterly_report"] | None = None


class ParsedFinancialDocument(BaseModel):
    document_id: str
    parser_name: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    currency: str | None = None
    raw_statements: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Structured Financial Metrics  (LLM extracts → Pydantic validated)
# ---------------------------------------------------------------------------

class IncomeStatementMetrics(BaseModel):
    """Key income statement line items."""
    revenue: float | None = None
    cost_of_goods_sold: float | None = None
    gross_profit: float | None = None
    operating_expenses: float | None = None
    operating_income: float | None = None          # EBIT
    interest_expense: float | None = None
    depreciation_amortization: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    eps: float | None = None


class BalanceSheetMetrics(BaseModel):
    """Key balance sheet line items."""
    total_assets: float | None = None
    current_assets: float | None = None
    cash_and_equivalents: float | None = None
    inventory: float | None = None
    accounts_receivable: float | None = None
    total_liabilities: float | None = None
    current_liabilities: float | None = None
    long_term_debt: float | None = None
    total_debt: float | None = None
    total_equity: float | None = None
    retained_earnings: float | None = None
    working_capital: float | None = None


class CashFlowMetrics(BaseModel):
    """Key cash flow statement line items."""
    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None
    financing_cash_flow: float | None = None
    capital_expenditures: float | None = None
    free_cash_flow: float | None = None


class FinancialPeriod(BaseModel):
    """Metadata about the reporting period."""
    fiscal_year: int | None = None
    fiscal_period: str | None = None   # "FY", "Q1", "Q2", etc.
    period_start: datetime | None = None
    period_end: datetime | None = None
    currency: str | None = None
    is_audited: bool | None = None


# ---------------------------------------------------------------------------
# Financial Ratios (deterministically computed from metrics)
# ---------------------------------------------------------------------------

class FinancialRatios(BaseModel):
    """Standard financial ratios computed deterministically from extracted metrics."""
    # Liquidity
    current_ratio: float | None = None
    quick_ratio: float | None = None
    cash_ratio: float | None = None

    # Leverage
    debt_to_equity: float | None = None
    debt_to_assets: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None

    # Profitability
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    ebitda_margin: float | None = None
    return_on_assets: float | None = None
    return_on_equity: float | None = None

    # Efficiency
    asset_turnover: float | None = None

    computation_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Altman Z-Score
# ---------------------------------------------------------------------------

class ZScoreFormula(str, Enum):
    original_public = "original_public"         # 1968: public manufacturing
    revised_private = "revised_private"         # Z': private companies
    non_manufacturing = "non_manufacturing"     # Z'': services / non-mfg


class ZScoreZone(str, Enum):
    safe = "safe"
    grey = "grey"
    distress = "distress"
    unknown = "unknown"


class ZScoreResult(BaseModel):
    """A single Z-Score computation for one reporting period."""
    fiscal_year: int | None = None
    period_label: str | None = None            # e.g. "FY2023", "Q3 2024"
    score: float | None = None
    zone: ZScoreZone = ZScoreZone.unknown
    formula_used: ZScoreFormula = ZScoreFormula.revised_private
    components: dict[str, float | None] = Field(default_factory=dict)
    zone_thresholds: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class PeerComparison(BaseModel):
    """Industry-level Z-Score benchmark for peer context."""
    industry_sector: str
    formula_used: ZScoreFormula
    industry_median_z: float | None = None
    industry_safe_zone_pct: float | None = None
    industry_grey_zone_pct: float | None = None
    industry_distress_zone_pct: float | None = None
    benchmark_z_safe: float | None = None
    benchmark_z_distress: float | None = None
    data_source: str = "static_benchmark_v1"
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Consolidated FinancialFeatures (FIS output)
# ---------------------------------------------------------------------------

class FinancialFeatures(BaseModel):
    """The complete output of the FIS subgraph.

    Combines LLM-extracted metrics with deterministically computed ratios,
    Z-Score results, and peer benchmarks.
    """
    period: FinancialPeriod = Field(default_factory=FinancialPeriod)

    income_statement: IncomeStatementMetrics = Field(default_factory=IncomeStatementMetrics)
    balance_sheet: BalanceSheetMetrics = Field(default_factory=BalanceSheetMetrics)
    cash_flow: CashFlowMetrics = Field(default_factory=CashFlowMetrics)

    ratios: FinancialRatios = Field(default_factory=FinancialRatios)

    current_z_score: ZScoreResult | None = None
    historical_z_scores: list[ZScoreResult] = Field(default_factory=list)
    peer_comparison: PeerComparison | None = None

    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Retrieval state models
# ---------------------------------------------------------------------------

class RetrievalQuery(BaseModel):
    source: Literal["news", "web", "financial_filings", "forums", "social"]
    query: str
    rationale: str
    priority: int = 1


class RawRetrievedItem(BaseModel):
    source: str
    query: str
    title: str | None = None
    url: str
    snippet: str | None = None
    published_date: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CoverageStatus(BaseModel):
    status: Literal["not_started", "partial", "sufficient", "insufficient"] = "not_started"
    topics_covered: list[str] = Field(default_factory=list)
    topics_missing: list[str] = Field(default_factory=list)
    attempts: int = 0


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    timestamp: datetime
    node_name: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Root case state
# ---------------------------------------------------------------------------

class CaseState(BaseModel):
    case_id: str
    created_at: datetime
    updated_at: datetime

    status: str = "created"
    company: CompanyProfile

    uploaded_financial_documents: list[UploadedFinancialDocument] = Field(default_factory=list)
    parsed_financial_documents: list[ParsedFinancialDocument] = Field(default_factory=list)
    financial_features: FinancialFeatures | None = None

    retrieval_plan: list[RetrievalQuery] = Field(default_factory=list)
    raw_retrieval_results: list[RawRetrievedItem] = Field(default_factory=list)

    # SIS-ready handoff
    normalized_documents: list[DocumentInput] = Field(default_factory=list)

    coverage: CoverageStatus = Field(default_factory=CoverageStatus)

    # SIS output (signal extraction + verification + conflict resolution)
    sis_output: dict[str, Any] | None = None

    # FRD output (traffic light scoring + analyst report)
    frd_output: dict[str, Any] | None = None
    frd_traffic_light: str | None = None  # "red" | "amber" | "green"

    # Analyst guidance — free-text context saved on the Run Analysis page,
    # injected into the FRD report generation prompt.
    analyst_guidance: str | None = None

    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_log: list[AuditEvent] = Field(default_factory=list)