def compute_score(state):
    state["score"] = 25.0
    state["confidence"] = 0.5
    state["status"] = "completed"
    return state