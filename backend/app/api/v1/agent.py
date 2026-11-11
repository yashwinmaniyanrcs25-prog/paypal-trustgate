"""Agentic purchasing intent endpoints powered by Grok."""

from fastapi import APIRouter, HTTPException, status
from app.models.purchase import UserIntentRequest, AgentAnalysisResponse
from app.services.grok_service import grok_service

router = APIRouter(prefix="/agent", tags=["AI Agent"])


@router.post(
    "/analyze",
    response_model=AgentAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse natural-language purchasing instruction via Grok",
)
async def analyze_instruction(request: UserIntentRequest):
    """Analyzes user instructions using Grok.

    Enforces that Grok acts solely in proposal mode and cannot authorize charges.
    """
    try:
        analysis = await grok_service.analyze_intent(request)
        return analysis
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent intent parsing failed: {str(e)}",
        )

