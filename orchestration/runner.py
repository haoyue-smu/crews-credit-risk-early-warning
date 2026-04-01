"""Smoke-test runner — verifies all four subgraphs compile without error.

Run from the project root:
  python -m orchestration.runner

This does NOT invoke any LLM or external API — it only checks that the
LangGraph StateGraph definitions are valid and all node imports succeed.
Useful as a quick sanity check after changing graph topology or state schemas.
"""

from orchestration.fis.graph import build_fis_graph
from orchestration.rs.graph import build_rs_graph
from orchestration.sis.graph import build_sis_graph
from orchestration.frd.graph import build_frd_graph


def run() -> None:
    print("Compiling FIS graph...", end=" ")
    build_fis_graph()
    print("OK")

    print("Compiling RS graph... ", end=" ")
    build_rs_graph()
    print("OK")

    print("Compiling SIS graph...", end=" ")
    build_sis_graph()
    print("OK")

    print("Compiling FRD graph...", end=" ")
    build_frd_graph()
    print("OK")

    print("\nAll four subgraphs compiled successfully.")


if __name__ == "__main__":
    run()
