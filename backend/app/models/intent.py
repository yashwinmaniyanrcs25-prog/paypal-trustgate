"""Models for natural language purchase intent interpretation."""

from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.policy import PurchaseMandate


class IntentInterpretationRequest(BaseModel):
    """User input prompt for natural language purchase intent."""
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural language shopping request",
        examples=[
            "I need a new laptop under ₹60,000. Only buy from a verified seller. No refurbished products and no accessories."
        ],
    )


class IntentInterpretationResponse(BaseModel):
    """Structured response from the Grok Intent Interpreter."""
    raw_prompt: str
    success: bool
    status: str = Field(
        description="Interpretation status: SUCCESS, NEEDS_CLARIFICATION, PROVIDER_UNCONFIGURED, PROVIDER_ERROR, VALIDATION_ERROR"
    )
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    mandate: Optional[PurchaseMandate] = None
    extracted_intent_summary: Optional[str] = None
    ai_explanation: Optional[str] = None
    is_confirmed: bool = False
    error_message: Optional[str] = None

