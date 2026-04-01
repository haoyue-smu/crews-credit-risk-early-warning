"""LangGraph state definitions for the UBS credit assessment pipeline.

Two separate state schemas exist because FIS/RS and SIS/FRD were built independently:

  AgentWorkerState  — used by FIS and RS subgraphs.
                      Wraps the central CaseState Pydantic model with LangGraph
                      reducer functions for parallel-safe merging.

  PipelineState     — used by SIS and FRD subgraphs.
                      A flat TypedDict (total=False) so each subgraph can be
                      invoked independently with only the fields it needs.

The two schemas are connected by the bridge functions in shared/states/frd_bridge.py,
which graph_runner.py uses to pass data between the FIS/RS and SIS/FRD halves.

Legacy:
  CreditGraphState  — used by orchestration/runner.py for smoke-testing only.
                      Not part of the production pipeline.
"""

import operator
from typing import Annotated, Any, Dict, List, TypedDict

from shared.states.case_state import CaseState


# ---------------------------------------------------------------------------
# AgentWorkerState — FIS and RS subgraphs
# ---------------------------------------------------------------------------

def merge_case_state(existing: CaseState | None, new: CaseState | None) -> CaseState:
    """LangGraph reducer for CaseState.

    Nodes return {'case': updated_case}. Because LangGraph merges state
    after every node, this reducer ensures the latest version always wins.
    Returning `existing` when `new` is None prevents accidental null-overwrites.
    """
    if new is None:
        return existing
    return new


def merge_rs_coverage(existing: dict | None, new: dict | None) -> dict | None:
    """LangGraph reducer for RS coverage tracking state. Latest value wins."""
    return new if new is not None else existing


class AgentWorkerState(TypedDict):
    """Root state for the FIS and RS LangGraph subgraphs.

    Fields
    ------
    case
        The central CaseState object. Every FIS/RS node reads from and writes
        back a modified copy via model_copy(deep=True). The merge_case_state
        reducer ensures safe replacement.

    retrieved_items_buffer
        Accumulates RawRetrievedItem objects from parallel Tavily search
        coroutines using operator.add (list concatenation reducer).

    _rs_coverage
        Serialized CoverageState dict passed between RS nodes to track
        which topics have been covered and how many retry attempts remain.
        The leading underscore signals that this is RS-internal state.
    """
    case: Annotated[CaseState, merge_case_state]
    retrieved_items_buffer: Annotated[list[Any], operator.add]
    _rs_coverage: Annotated[dict | None, merge_rs_coverage]


# ---------------------------------------------------------------------------
# PipelineState — SIS and FRD subgraphs
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    """State passed through the SIS and FRD LangGraph subgraphs.

    Uses total=False so each subgraph can be invoked standalone with only
    the fields it needs (no required keys).

    Data flow
    ---------
    graph_runner.py populates the initial keys:
      - RS output → documents (via frd_bridge.normalized_documents_to_pipeline_docs)
      - FIS output → financial_profile (via frd_bridge.financial_features_to_profile)

    SIS writes:  extraction_results → validation_results → verification_results
                 → conflict_results / conflict_summary → sis_output
    FRD reads:   sis_output + financial_profile
    FRD writes:  frd_aggregated → risk_score → report → frd_output
    """

    # --- Inputs (populated by graph_runner.py before SIS) ---
    company_id: str
    documents: List[Dict[str, Any]]           # RS-normalized documents for SIS

    # --- SIS intermediate state (written sequentially by SIS nodes) ---
    extraction_results: List[Dict[str, Any]]   # Raw signals from extract node
    validation_results: List[Dict[str, Any]]   # Schema-validated signals
    verification_results: List[Dict[str, Any]] # Grounding-verified signals
    conflict_results: List[Dict[str, Any]]     # Conflict-resolved signals
    conflict_summary: Dict[str, Any]           # Aggregate conflict stats

    # --- SIS output (written by evidence_gate, consumed by FRD) ---
    sis_output: Dict[str, Any]                 # Serialized SISOutput
    targeted_retrieval_requests: List[Dict[str, Any]]  # Optional RS feedback (future)

    # --- FIS output (populated by graph_runner.py before FRD) ---
    financial_profile: Dict[str, Any] | None  # Serialized FinancialProfile

    # --- FRD intermediate state ---
    frd_aggregated: Dict[str, Any]            # Merged signals + financial profile
    skip_report: bool                         # If True, skip narrative generation
    report_model_id: str                      # Gemini model to use for the report

    # --- FRD output ---
    risk_score: Dict[str, Any]               # Serialized RiskScore
    report: Dict[str, Any] | None            # Raw report dict from generate_report
    frd_output: Dict[str, Any]               # Serialized FRDOutput (final result)


# ---------------------------------------------------------------------------
# CreditGraphState — legacy smoke-test runner only
# ---------------------------------------------------------------------------

class CreditGraphState(TypedDict):
    """Minimal state used by orchestration/runner.py for graph compilation checks.

    Not part of the production pipeline.
    """
    entity_name: str
    entity_type: str
    location: str
    documents: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    score: float
    confidence: float
    status: str
