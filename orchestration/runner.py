"""Top-level runner for testing subgraph compilation and execution."""

from orchestration.fis.graph import build_fis_graph
from orchestration.rs.graph import build_rs_graph


def run():
    fis_graph = build_fis_graph()
    print("FIS graph compiled successfully!")

    rs_graph = build_rs_graph()
    print("RS graph compiled successfully!")

    return fis_graph, rs_graph


if __name__ == "__main__":
    run()