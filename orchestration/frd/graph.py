"""LangGraph FRD subgraph: aggregate_inputs → score_risk → generate_report."""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from orchestration.state import PipelineState
from shared.schemas.frd import FRDOutput, FinancialProfile, RiskScore


def frd_aggregate_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.frd.nodes.aggregate_inputs import aggregate_inputs

    sis = state.get("sis_output")
    if not sis:
        raise ValueError("frd_aggregate_node: state['sis_output'] is missing")
    fp_raw = state.get("financial_profile")
    aggregated = aggregate_inputs(sis, financial_profile=fp_raw)
    fp = aggregated["financial_profile"]
    frd_aggregated = {
        "company_id": aggregated["company_id"],
        "signals": aggregated["signals"],
        "sector_signals": aggregated["sector_signals"],
        "documents_processed": aggregated["documents_processed"],
        "financial_profile": fp.model_dump(mode="json") if fp is not None else None,
    }
    return {"frd_aggregated": frd_aggregated}


def frd_score_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.frd.nodes.score_risk import score_risk

    agg = state.get("frd_aggregated") or {}
    signals = agg.get("signals") or []
    company_id = str(agg.get("company_id", ""))
    fp = agg.get("financial_profile")
    risk = score_risk(signals, company_id, financial_profile=fp)
    return {"risk_score": risk.model_dump(mode="json")}


def frd_report_node(state: PipelineState) -> Dict[str, Any]:
    from orchestration.frd.nodes.generate_report import generate_report

    agg = state.get("frd_aggregated") or {}
    risk = RiskScore.model_validate(state["risk_score"])
    skip = bool(state.get("skip_report"))
    from shared.llm import MODEL_FRD
    model_id = str(state.get("report_model_id") or MODEL_FRD)

    report_dict: Dict[str, Any] | None
    if skip:
        report_dict = None
    else:
        report_dict = generate_report(
            risk_score=state["risk_score"],
            signals=list(agg.get("signals") or []),
            financial_profile=agg.get("financial_profile"),
            documents_processed=int(agg.get("documents_processed", 0)),
            model_id=model_id,
            analyst_guidance=str(state.get("analyst_guidance") or ""),
        )

    fp_model = (
        FinancialProfile.model_validate(agg["financial_profile"])
        if agg.get("financial_profile")
        else None
    )

    metadata = {
        "pipeline": "orchestration.graph",
        "documents_processed": agg.get("documents_processed", 0),
        "criteria_evaluated": len(risk.criteria_results),
        "criteria_met": sum(1 for c in risk.criteria_results if c.met),
        "financial_data_available": risk.financial_data_available,
        "report_generated": report_dict is not None,
        "report_model": report_dict["model_used"] if report_dict else None,
        "report_sections": report_dict["sections"] if report_dict else None,
        "timestamp": report_dict["generation_timestamp"] if report_dict else None,
    }

    frd = FRDOutput(
        company_id=risk.company_id,
        traffic_light=risk.traffic_light,
        risk_score=risk,
        report_narrative=report_dict["full_narrative"] if report_dict else None,
        financial_profile=fp_model,
        metadata=metadata,
    )

    return {
        "report": report_dict,
        "frd_output": frd.model_dump(mode="json"),
    }


def build_frd_graph() -> Any:
    """Build and compile the FRD LangGraph subgraph."""
    graph = StateGraph(PipelineState)
    graph.add_node("aggregate", frd_aggregate_node)
    graph.add_node("score", frd_score_node)
    graph.add_node("report", frd_report_node)

    graph.set_entry_point("aggregate")
    graph.add_edge("aggregate", "score")
    graph.add_edge("score", "report")
    graph.add_edge("report", END)
    return graph.compile()
