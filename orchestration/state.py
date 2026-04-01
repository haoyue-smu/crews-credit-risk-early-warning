import operator
from typing import TypedDict, Annotated, Any

from shared.states.case_state import CaseState


def merge_case_state(existing: CaseState | None, new: CaseState | None) -> CaseState:
    """Reducer function to manage updating the global case state.
    For simplicity, we replace the state entirely when a node returns it."""
    if new is None:
        return existing
    return new


def merge_rs_coverage(existing: dict | None, new: dict | None) -> dict | None:
    """Reducer for RS coverage state. Latest wins."""
    if new is not None:
        return new
    return existing


class AgentWorkerState(TypedDict):
    """The root statestore for LangGraph.

    Used by both FIS and RS subgraphs.
    """
    # Global case state — nodes return {'case': updated_case}
    case: Annotated[CaseState, merge_case_state]

    # Internal LangGraph reducer for parallel fan-out fetches (Map-Reduce)
    retrieved_items_buffer: Annotated[list[Any], operator.add]

    # RS coverage tracking (passed between RS nodes)
    _rs_coverage: Annotated[dict | None, merge_rs_coverage]
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
