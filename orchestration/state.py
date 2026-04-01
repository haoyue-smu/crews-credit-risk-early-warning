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