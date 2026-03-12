from typing import TypedDict, List, Dict, Any


class CreditGraphState(TypedDict):
    entity_name: str
    entity_type: str
    location: str
    documents: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    score: float
    confidence: float
    status: str