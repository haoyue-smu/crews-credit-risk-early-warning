"""Shared pipeline state for LangGraph orchestration."""

from __future__ import annotations

from typing import Any, List, Dict, TypedDict


class PipelineState(TypedDict, total=False):
    """State passed between all subgraphs in the pipeline.

    Each subgraph reads what it needs and writes its outputs.
    Fields use total=False so subgraphs can be run independently.

    Flow: RS/SQ populate documents → SIS reads documents, writes signals →
          FIS populates financial_profile → FRD reads signals + financial_profile, writes risk output
    """

    # --- Input (populated by RS/SQ or dev loader) ---
    company_id: str
    documents: List[Dict[str, Any]]

    # --- SIS internal (written by SIS nodes, read by next SIS node) ---
    extraction_results: List[Dict[str, Any]]
    validation_results: List[Dict[str, Any]]
    verification_results: List[Dict[str, Any]]
    conflict_results: List[Dict[str, Any]]
    conflict_summary: Dict[str, Any]

    # --- SIS output (written by evidence_gate, read by FRD) ---
    sis_output: Dict[str, Any]
    targeted_retrieval_requests: List[Dict[str, Any]]

    # --- FIS output (populated by FIS or dev loader) ---
    financial_profile: Dict[str, Any] | None

    # --- FRD intermediate / control ---
    frd_aggregated: Dict[str, Any]
    skip_report: bool
    report_model_id: str

    # --- FRD output ---
    risk_score: Dict[str, Any]
    report: Dict[str, Any] | None
    frd_output: Dict[str, Any]


# --- Legacy graph state (orchestration/runner.py) ---


class CreditGraphState(TypedDict):
    entity_name: str
    entity_type: str
    location: str
    documents: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    score: float
    confidence: float
    status: str
