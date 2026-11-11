"""Models for the deterministic TrustGate policy engine."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


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

    # Extended structured purchasing requirements
    category: Optional[str] = Field(
        default=None,
        description="Mandated product category (e.g. 'laptop')",
    )
    search_query: Optional[str] = Field(
        default=None,
        description="Inferred product search query (e.g. 'laptop')",
    )
    min_ram_gb: Optional[int] = Field(
        default=None,
        description="Minimum RAM capacity in gigabytes (e.g. 16)",
    )
    min_storage_gb: Optional[int] = Field(
        default=None,
        description="Minimum storage capacity in gigabytes (e.g. 512)",
    )
    storage_type: Optional[str] = Field(
        default=None,
        description="Mandated storage type (e.g. 'SSD', 'NVMe')",
    )
    processor_requirement: Optional[str] = Field(
        default=None,
        description="Processor requirement (e.g. 'Intel Core i5 or AMD Ryzen 5 or better')",
    )
    gpu_requirement: Optional[str] = Field(
        default=None,
        description="GPU requirement",
    )
    display_size: Optional[str] = Field(
        default=None,
        description="Display size requirement",
    )
    brand_preference: Optional[str] = Field(
        default=None,
        description="Brand preference",
    )
    model_preference: Optional[str] = Field(
        default=None,
        description="Model preference",
    )
    marketplace: Optional[str] = Field(
        default=None,
        description="Mandated marketplace (e.g. 'amazon.in', 'amazon.com')",
    )
    in_stock_required: bool = Field(
        default=True,
        description="Whether product must be in stock / available for purchase",
    )

    @property
    def condition(self) -> str:
        return self.allowed_conditions[0] if self.allowed_conditions else "new"

    @property
    def verified_seller_required(self) -> bool:
        return self.require_merchant_verification

    @property
    def allow_accessories(self) -> bool:
        return self.allow_add_ons

    @model_validator(mode="before")
    @classmethod
    def remap_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # remap max_budget -> max_amount if max_amount not present
            if "max_budget" in data and "max_amount" not in data:
                data["max_amount"] = data["max_budget"]
            # remap verified_seller_required -> require_merchant_verification
            if "verified_seller_required" in data and "require_merchant_verification" not in data:
                data["require_merchant_verification"] = data["verified_seller_required"]
            # remap allow_accessories -> allow_add_ons
            if "allow_accessories" in data and "allow_add_ons" not in data:
                data["allow_add_ons"] = data["allow_accessories"]
            # remap condition -> allowed_conditions
            if "condition" in data and "allowed_conditions" not in data:
                data["allowed_conditions"] = [data["condition"]]
            # remap query -> search_query if search_query not present
            if "query" in data and "search_query" not in data:
                data["search_query"] = data["query"]
        return data

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
    category: Optional[str] = Field(default="General", description="Product category")
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

    # Normalized hardware and marketplace specifications
    brand: Optional[str] = Field(default=None, description="Product brand name")
    model: Optional[str] = Field(default=None, description="Product model identifier")
    ram_gb: Optional[int] = Field(default=None, description="RAM size in GB")
    storage_gb: Optional[int] = Field(default=None, description="Storage capacity in GB")
    storage_type: Optional[str] = Field(default=None, description="Storage type (SSD, NVMe, eMMC, HDD)")
    processor: Optional[str] = Field(default=None, description="Processor name/tier")
    gpu: Optional[str] = Field(default=None, description="Graphics card or integrated GPU")
    screen_size: Optional[str] = Field(default=None, description="Screen size in inches")
    availability: Optional[str] = Field(default="InStock", description="Availability status (InStock, OutOfStock, etc.)")
    marketplace: Optional[str] = Field(default=None, description="Listing marketplace (e.g. amazon.in, amazon.com)")
    retailer: Optional[str] = Field(default=None, description="Listing retailer domain (e.g. officedepot.com)")
    original_price: Optional[float] = Field(default=None, description="Original listing price before conversion")
    original_currency: Optional[str] = Field(default=None, description="Original listing currency ISO code")
    spec_verification_status: Optional[str] = Field(default="UNKNOWN", description="VERIFIED, UNVERIFIED, or UNKNOWN")

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
