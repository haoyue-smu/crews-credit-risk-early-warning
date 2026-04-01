from langgraph.graph import StateGraph, END
from orchestration.state import AgentWorkerState
from orchestration.fis.nodes import (
    ingest_client_financials,
    parse_financial_documents,
    extract_financial_features
)


def build_fis_graph():
    """Builds and compiles the Financial Ingestion Subgraph (FIS).

    Sequential deterministic flow:
      ingest_client_financials → parse_financial_documents → extract_financial_features → END
    """
    graph = StateGraph(AgentWorkerState)

    graph.add_node("ingest_client_financials", ingest_client_financials)
    graph.add_node("parse_financial_documents", parse_financial_documents)
    graph.add_node("extract_financial_features", extract_financial_features)

    graph.set_entry_point("ingest_client_financials")
    graph.add_edge("ingest_client_financials", "parse_financial_documents")
    graph.add_edge("parse_financial_documents", "extract_financial_features")
    graph.add_edge("extract_financial_features", END)

    return graph.compile()
