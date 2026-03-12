from langgraph.graph import StateGraph, END
from orchestration.state import CreditGraphState
from orchestration.nodes.collect import collect_documents
from orchestration.nodes.extract import extract_signals
from orchestration.nodes.verify import verify_signals
from orchestration.nodes.score import compute_score


def build_graph():
    graph = StateGraph(CreditGraphState)

    graph.add_node("collect", collect_documents)
    graph.add_node("extract", extract_signals)
    graph.add_node("verify", verify_signals)
    graph.add_node("score", compute_score)

    graph.set_entry_point("collect")
    graph.add_edge("collect", "extract")
    graph.add_edge("extract", "verify")
    graph.add_edge("verify", "score")
    graph.add_edge("score", END)

    return graph.compile()