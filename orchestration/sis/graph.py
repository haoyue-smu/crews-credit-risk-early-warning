"""LangGraph SIS subgraph: extract → validate → verify → conflict → evidence_gate."""

from __future__ import annotations

from typing import Any, Dict, List

from langgraph.graph import END, StateGraph

from orchestration.state import PipelineState
from shared.schemas.documents import DocumentInput
from shared.schemas.signals import Signal


def _documents_from_state(state: PipelineState) -> List[DocumentInput]:
    raw = state.get("documents") or []
    return [DocumentInput.model_validate(d) for d in raw]


def _verification_item_to_dict(item: Dict[str, Any]) -> Dict[str, Any]:
    sig = item["signal"]
    return {
        "signal": sig.model_dump(mode="json") if isinstance(sig, Signal) else sig,
        "verification_decision": item.get("verification_decision", "skipped"),
        "adjusted_confidence": float(item.get("adjusted_confidence", 0.0)),
        "original_confidence": float(item.get("original_confidence", 0.0)),
    }


def _verification_item_from_dict(rec: Dict[str, Any]) -> Dict[str, Any]:
    sig_raw = rec["signal"]
    sig = Signal.model_validate(sig_raw) if isinstance(sig_raw, dict) else sig_raw
    return {
        "signal": sig,
        "verification_decision": str(rec.get("verification_decision", "skipped")),
        "adjusted_confidence": float(rec.get("adjusted_confidence", 0.0)),
        "original_confidence": float(rec.get("original_confidence", 0.0)),
    }


def sis_extract_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.sis.nodes.extract import parallel_extract_signals

    docs = _documents_from_state(state)
    if not docs:
        raise ValueError("sis_extract_node: state['documents'] is missing or empty")
    signals = parallel_extract_signals(docs)
    return {"extraction_results": [s.model_dump(mode="json") for s in signals]}


def sis_validate_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.sis.nodes.validate import schema_validation_gate

    docs = _documents_from_state(state)
    raw = state.get("extraction_results") or []
    signals = [Signal.model_validate(s) for s in raw]
    result = schema_validation_gate(signals=signals, documents=docs)
    retry_needed = result.get("retry_needed") or []
    if retry_needed:
        print(f"[sis_validate_node] validation retry_needed document_ids: {retry_needed}")
    combined = list(result["valid_signals"]) + list(result["passed_with_warnings"])
    return {
        "validation_results": [s.model_dump(mode="json") for s in combined],
    }


def sis_verify_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.sis.nodes.verify import parallel_verify_signals

    docs = _documents_from_state(state)
    raw = state.get("validation_results") or []
    signals = [Signal.model_validate(s) for s in raw]
    items = parallel_verify_signals(signals=signals, documents=docs, max_workers=10)
    return {"verification_results": [_verification_item_to_dict(it) for it in items]}


def sis_conflict_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.sis.nodes.conflict import conflict_resolution

    docs = _documents_from_state(state)
    vraw = state.get("verification_results") or []
    items = [_verification_item_from_dict(rec) for rec in vraw]
    working, summary = conflict_resolution(items, docs, max_workers=10)
    return {
        "conflict_results": [_verification_item_to_dict(it) for it in working],
        "conflict_summary": summary,
    }


def sis_evidence_gate_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.sis.nodes.evidence_gate import evidence_gate

    docs = _documents_from_state(state)
    craw = state.get("conflict_results") or []
    items = [_verification_item_from_dict(rec) for rec in craw]
    signals = [it["signal"] for it in items]
    sis_output, retrieval = evidence_gate(signals, docs)
    return {
        "sis_output": sis_output.model_dump(mode="json"),
        "targeted_retrieval_requests": [r.model_dump(mode="json") for r in retrieval],
    }


def build_sis_graph() -> Any:
    """Build and compile the SIS LangGraph subgraph."""
    graph = StateGraph(PipelineState)
    graph.add_node("extract", sis_extract_node)
    graph.add_node("validate", sis_validate_node)
    graph.add_node("verify", sis_verify_node)
    graph.add_node("conflict", sis_conflict_node)
    graph.add_node("evidence_gate", sis_evidence_gate_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", "verify")
    graph.add_edge("verify", "conflict")
    graph.add_edge("conflict", "evidence_gate")
    graph.add_edge("evidence_gate", END)
    return graph.compile()
