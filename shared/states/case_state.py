from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

from shared.schemas.documents import DocumentInput


class CompanyProfile(BaseModel):
    company_id: str
    company_name: str
    company_type: Literal["public", "private"]
    jurisdiction: str | None = None
    ticker: str | None = None
    isin: str | None = None
    website: str | None = None


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


class FinancialFeatures(BaseModel):
    values: dict[str, float | None] = Field(default_factory=dict)
    ratios: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


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


class AuditEvent(BaseModel):
    timestamp: datetime
    node_name: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


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

    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_log: list[AuditEvent] = Field(default_factory=list)