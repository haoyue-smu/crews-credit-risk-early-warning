"""Top-level pipeline graph combining SIS and FRD subgraphs."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from orchestration.frd.graph import build_frd_graph
from orchestration.sis.graph import build_sis_graph
from orchestration.state import PipelineState


def build_pipeline() -> Any:
    """Build the full SIS → FRD pipeline.

    Future: RS, SQ, FIS subgraphs will populate ``documents`` / ``financial_profile``.
    """
    graph = StateGraph(PipelineState)
    sis_graph = build_sis_graph()
    frd_graph = build_frd_graph()

    graph.add_node("sis", sis_graph)
    graph.add_node("frd", frd_graph)

    graph.set_entry_point("sis")
    graph.add_edge("sis", "frd")
    graph.add_edge("frd", END)
    return graph.compile()
