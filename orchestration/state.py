import operator
from typing import TypedDict, Annotated, Any

from shared.states.case_state import CaseState

def merge_case_state(existing: CaseState | None, new: CaseState | None) -> CaseState:
    """Reducer function to manage updating the global case state.
    For simplicity in FIS, we just replace the state entirely when a node returns it."""
    if new is None:
        return existing
    return new

class AgentWorkerState(TypedDict):
    """The root statestore for LangGraph."""
    # We maintain the global case state here. Nodes will return {'case': updated_case}
    case: Annotated[CaseState, merge_case_state]
    
    # Internal LangGraph reducer for parallel fan-out fetches (Map-Reduce)
    retrieved_items_buffer: Annotated[list[Any], operator.add]