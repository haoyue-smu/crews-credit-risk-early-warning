from fastapi import APIRouter
from backend.schemas.assess import AssessRequest, AssessResponse

router = APIRouter()


@router.post("/assess", response_model=AssessResponse)
def assess_entity(payload: AssessRequest):
    return AssessResponse(
        entity_name=payload.entity_name,
        text_risk_score=0.0,
        confidence=0.0,
        status="stub"
    )