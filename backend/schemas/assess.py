from pydantic import BaseModel


class AssessRequest(BaseModel):
    entity_name: str
    entity_type: str
    location: str | None = None


class AssessResponse(BaseModel):
    entity_name: str
    text_risk_score: float
    confidence: float
    status: str