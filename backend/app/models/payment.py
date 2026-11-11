"""Models for PayPal Sandbox Checkout and Server-Side Payment Operations."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.models.policy import PurchaseMandate, MandatePolicyEvaluationResponse
from app.models.proposal import DiscoveredProduct


class PaymentConfigResponse(BaseModel):
    """Public configuration for PayPal Sandbox Checkout."""
    configured: bool = Field(..., description="True if Sandbox credentials are set")
    client_id: Optional[str] = Field(default=None, description="Public PayPal Sandbox client ID only. Never secret.")
    mode: str = Field(default="sandbox", description="Always 'sandbox'")
    currency: str = Field(default="USD", description="Default checkout currency")
    base_url: str = Field(default="https://api-m.sandbox.paypal.com")
    merchant_name: str = Field(default="PayPal TrustGate Sandbox")
    is_sandbox: bool = Field(default=True)
    notice: str = Field(
        default="Sandbox test environment only. No real financial charges occur.",
        description="Clear prototype disclosure",
    )


class CreateOrderRequest(BaseModel):
    """Payload to create a PayPal Sandbox order from a trusted staged proposal."""
    staged_proposal_id: str = Field(..., description="ID of the trusted server-side staged proposal")
    user_id: Optional[str] = Field(default="user_demo")


class CreateOrderResponse(BaseModel):
    """PayPal Sandbox order creation response."""
    order_id: str = Field(..., description="PayPal Sandbox order identifier")
    staged_proposal_id: str = Field(..., description="Linked internal proposal ID")
    status: str = Field(..., description="PayPal order status (e.g. CREATED)")
    amount: float = Field(..., description="Server-derived total amount")
    currency: str = Field(..., description="Currency code")
    is_sandbox: bool = True
    is_demo_data: bool = True
    message: str = "PayPal Sandbox order created. Awaiting explicit buyer approval in Sandbox."


class CaptureOrderRequest(BaseModel):
    """Payload to capture an approved PayPal Sandbox order."""
    order_id: str = Field(..., description="PayPal Sandbox order ID")
    user_id: Optional[str] = Field(default="user_demo")


class CaptureOrderResponse(BaseModel):
    """Receipt returned after verified server-side capture in PayPal Sandbox."""
    order_id: str
    capture_id: str
    staged_proposal_id: str
    status: str = "COMPLETED"
    amount: float
    currency: str
    product_name: str
    merchant_name: str
    captured_at: str
    policy_decision: str = "APPROVED"
    policy_signature: str
    is_sandbox: bool = True
    is_demo_data: bool = True
    receipt_notice: str = "PayPal Sandbox transaction captured successfully. Demonstration checkout only. No real funds transferred."


class PaymentStatusResponse(BaseModel):
    """Safe payment status response."""
    order_id: str
    staged_proposal_id: Optional[str] = None
    status: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    captured: bool = False
    capture_id: Optional[str] = None
    is_sandbox: bool = True
    is_demo_data: bool = True


class StagedProposalRecord(BaseModel):
    """Trusted server-side record of a staged proposal with explicit state tracking."""
    staged_proposal_id: str
    mandate: PurchaseMandate
    candidate: DiscoveredProduct
    policy_evaluation: MandatePolicyEvaluationResponse
    user_id: str
    status: str = "STAGED"  # STAGED | HUMAN_APPROVED | HUMAN_REJECTED | ORDER_CREATED | ORDER_CREATION_FAILED | CAPTURED | CAPTURE_FAILED | CANCELLED | EXPIRED
    created_at: str
    updated_at: Optional[str] = None
    paypal_order_id: Optional[str] = None
    captured: bool = False
    capture_id: Optional[str] = None
    capture_data: Optional[Dict[str, Any]] = None
    rejection_reason: Optional[str] = None
    cancellation_reason: Optional[str] = None
    expires_at: Optional[str] = None
