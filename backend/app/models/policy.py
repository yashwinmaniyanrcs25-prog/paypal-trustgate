"""Models for the deterministic TrustGate policy engine."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class ProductCondition(str, Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"


class RuleSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class PolicyViolation(BaseModel):
    """Details of a detected policy rule violation."""
    rule_id: str
    rule_name: str
    message: str
    severity: RuleSeverity = RuleSeverity.CRITICAL
    expected: Any = None
    actual: Any = None


class PolicyCheckSummary(BaseModel):
    """Status of an individual deterministic policy check."""
    rule_id: str
    rule_name: str
    description: str
    passed: bool
    details: str


class PurchaseMandate(BaseModel):
    """User-defined purchase mandate and constraints."""
    max_amount: float = Field(
        ...,
        gt=0,
        description="Maximum allowed checkout amount in declared currency",
        examples=[150.00],
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Allowed currency ISO code (e.g. USD, EUR, GBP)",
        examples=["USD"],
    )
    allowed_conditions: List[str] = Field(
        default_factory=lambda: ["new"],
        description="Allowed product conditions (e.g. ['new'], ['new', 'refurbished'])",
    )
    require_merchant_verification: bool = Field(
        default=True,
        description="Whether the selling merchant must be verified",
    )
    allow_add_ons: bool = Field(
        default=False,
        description="Whether additional items, accessory add-ons, or warranties are allowed",
    )
    user_restrictions: Optional[List[str]] = Field(
        default_factory=list,
        description="Optional user-defined restrictions (e.g. 'US shipping only')",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().upper()
            return clean if clean else "USD"
        return "USD"

    @field_validator("allowed_conditions", mode="before")
    @classmethod
    def normalize_conditions(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [c.strip().lower() for c in v.split(",") if c.strip()]
        if isinstance(v, list):
            return [str(c).strip().lower() for c in v if str(c).strip()]
        return ["new"]


class ProposedTransaction(BaseModel):
    """Proposed transaction details from merchant or agent proposal."""
    product_name: str = Field(..., min_length=1, description="Product title or description")
    product_description: Optional[str] = Field(default="", description="Detailed product description")
    product_price: float = Field(..., ge=0, description="Base product price")
    shipping_cost: float = Field(default=0.0, ge=0, description="Shipping cost")
    tax: float = Field(default=0.0, ge=0, description="Applicable tax")
    additional_charges: float = Field(default=0.0, ge=0, description="Additional charges or hidden fees")
    final_total: float = Field(..., gt=0, description="Final checkout total declared")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="Currency ISO code")
    merchant_name: str = Field(..., min_length=1, description="Merchant or vendor name")
    merchant_verified: bool = Field(default=False, description="Whether merchant is verified")
    product_condition: str = Field(default="new", description="Product condition (new, used, refurbished)")
    add_ons: List[str] = Field(default_factory=list, description="Additional items or add-ons included")

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().upper()
            return clean if clean else "USD"
        return "USD"

    @field_validator("product_condition", mode="before")
    @classmethod
    def normalize_condition(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            return clean if clean else "new"
        return "new"


class MandatePolicyEvaluationRequest(BaseModel):
    """Input payload to evaluate a proposed transaction against a purchase mandate."""
    mandate: PurchaseMandate
    transaction: ProposedTransaction
    caller_role: str = Field(
        default="human_user",
        description="Must be 'human_user' to proceed to checkout readiness.",
    )


class MandatePolicyEvaluationResponse(BaseModel):
    """Output from the deterministic policy engine for a mandate evaluation."""
    evaluation_id: str
    approved: bool
    status: str  # "APPROVED" | "BLOCKED"
    violations: List[PolicyViolation]
    explanation: str
    checks: List[PolicyCheckSummary]
    mandate_summary: Dict[str, Any]
    transaction_summary: Dict[str, Any]
    requires_human_approval: bool = True
    can_proceed_to_paypal: bool
    policy_signature: str
    evaluated_at: str


# Legacy compatibility models
class PolicyEvaluationRequest(BaseModel):
    """Legacy input payload to evaluate a proposed purchase against user constraints."""
    user_id: str = "user_demo"
    original_instruction: str = ""
    budget_limit: float
    proposed_price: float
    shipping_cost: float = 0.0
    merchant_name: str
    caller_role: str = Field(
        default="human_user",
        description="Must be 'human_user' to proceed to checkout readiness.",
    )


class PolicyEvaluationResponse(BaseModel):
    """Legacy output from the deterministic policy engine."""
    evaluation_id: str
    passed: bool
    status: str
    checks: List[PolicyCheckSummary]
    violations: List[PolicyViolation]
    total_evaluated_cost: float
    budget_limit: float
    requires_human_approval: bool = True
    can_proceed_to_paypal: bool
    policy_signature: str
