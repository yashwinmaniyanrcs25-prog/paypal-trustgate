"""Models for user purchasing instructions and AI product recommendations."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PurchasingStatus(str, Enum):
    """Lifecycle statuses for an agentic purchase flow."""
    RECEIVED = "RECEIVED"
    AI_ANALYZED = "AI_ANALYZED"
    POLICY_VERIFIED = "POLICY_VERIFIED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    READY_FOR_PAYPAL = "READY_FOR_PAYPAL"
    REJECTED = "REJECTED"


class PurchaseConstraints(BaseModel):
    """Parsed bounds extracted from user intent."""
    max_budget: float = Field(..., description="Maximum budget allowed in USD")
    allowed_categories: List[str] = Field(default_factory=list)
    allowed_merchants: List[str] = Field(default_factory=list)
    required_specs: List[str] = Field(default_factory=list)
    destination_country: str = Field(default="US")


class UserIntentRequest(BaseModel):
    """User natural-language purchasing instructions."""
    instruction: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural language instruction (e.g. 'Find a mechanical keyboard under $120 with brown switches')",
        examples=["Find me ergonomic noise-canceling headphones under $150 with US shipping."],
    )
    explicit_budget_cap: Optional[float] = Field(
        default=None,
        description="Optional explicit maximum budget override by user",
    )
    user_id: str = Field(default="user_demo_01", description="Identifier of the user")


class ProductProposal(BaseModel):
    """A product recommendation proposed by the Grok AI agent (Propose-only)."""
    id: str = Field(..., description="Proposal ID")
    title: str = Field(..., description="Product name")
    description: str = Field(..., description="Product summary")
    merchant: str = Field(..., description="Merchant name")
    merchant_trusted: bool = Field(default=True, description="Whether merchant is on approved list")
    price: float = Field(..., description="Unit price in USD")
    shipping_cost: float = Field(default=0.0, description="Estimated shipping")
    currency: str = Field(default="USD")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="AI confidence matching user instructions")
    specs_matched: List[str] = Field(default_factory=list)
    specs_unmatched: List[str] = Field(default_factory=list)
    product_url: Optional[str] = None


class AgentAnalysisResponse(BaseModel):
    """Result of Grok AI parsing and recommendation."""
    request_id: str
    original_instruction: str
    extracted_constraints: PurchaseConstraints
    reasoning_summary: str
    proposed_product: Optional[ProductProposal] = None
    ai_status: str = "PROPOSAL_ONLY"
    warning: str = "AI proposal is subject to deterministic policy verification and explicit human approval."

