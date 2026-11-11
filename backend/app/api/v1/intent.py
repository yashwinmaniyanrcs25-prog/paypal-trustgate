"""Natural language purchase intent interpretation endpoints."""

from fastapi import APIRouter, HTTPException, status
from app.models.intent import IntentInterpretationRequest, IntentInterpretationResponse
from app.services.intent_interpreter_service import intent_interpreter_service

router = APIRouter(tags=["Intent Interpreter"])


@router.post(
    "/interpret",
    response_model=IntentInterpretationResponse,
    status_code=status.HTTP_200_OK,
    summary="Translate natural-language shopping instruction into a Purchase Mandate via Grok",
)
async def interpret_purchase_intent(request: IntentInterpretationRequest):
    """Interprets natural language into structured purchase mandate bounds.

    Uses the xAI Grok API with structured JSON output mode.
    Enforces that AI only extracts constraints and has zero payment execution rights.
    """
    try:
        response = await intent_interpreter_service.interpret_intent(request.prompt)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Intent interpretation service error: {str(e)}",
        )

