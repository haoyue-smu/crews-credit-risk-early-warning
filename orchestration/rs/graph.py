"""Retrieval Subgraph (RS) — LangGraph definition.

Async graph with conditional retry loop:

  plan_retrieval → execute_searches → normalize_and_dedup → relevance_filter
  → coverage_gate → (sufficient)  → source_quality_assessment → END
                  → (retry)       → retrieval_retry → execute_searches (loop)
                  → (exhausted)   → source_quality_assessment → END
"""

from langgraph.graph import StateGraph, END
from orchestration.state import AgentWorkerState
from orchestration.rs.nodes import (
    plan_retrieval,
    execute_searches,
    normalize_and_dedup,
    relevance_filter,
    coverage_gate,
    retrieval_retry,
    source_quality_assessment,
)


def _route_coverage(state: AgentWorkerState) -> str:
    """Routing function for the coverage gate decision."""
    case = state["case"]
    status = case.status

    if status == "rs_coverage_sufficient":
        return "source_quality_assessment"
    elif status == "rs_coverage_retry":
        return "retrieval_retry"
    else:  # exhausted
        return "source_quality_assessment"


def build_rs_graph():
    """Builds and compiles the Retrieval Subgraph (RS).

    All nodes are async. The coverage gate creates a conditional retry loop.
    """
    graph = StateGraph(AgentWorkerState)

    # Add nodes
    graph.add_node("plan_retrieval", plan_retrieval)
    graph.add_node("execute_searches", execute_searches)
    graph.add_node("normalize_and_dedup", normalize_and_dedup)
    graph.add_node("relevance_filter", relevance_filter)
    graph.add_node("coverage_gate", coverage_gate)
    graph.add_node("retrieval_retry", retrieval_retry)
    graph.add_node("source_quality_assessment", source_quality_assessment)

    # Entry
    graph.set_entry_point("plan_retrieval")

    # Main flow
    graph.add_edge("plan_retrieval", "execute_searches")
    graph.add_edge("execute_searches", "normalize_and_dedup")
    graph.add_edge("normalize_and_dedup", "relevance_filter")
    graph.add_edge("relevance_filter", "coverage_gate")

    # Coverage gate conditional routing
    graph.add_conditional_edges(
        "coverage_gate",
        _route_coverage,
        {
            "source_quality_assessment": "source_quality_assessment",
            "retrieval_retry": "retrieval_retry",
        },
    )

    # Retry loop: retry → re-execute → re-normalize → re-filter → re-gate
    graph.add_edge("retrieval_retry", "execute_searches")

    # Terminal
    graph.add_edge("source_quality_assessment", END)

    return graph.compile()
