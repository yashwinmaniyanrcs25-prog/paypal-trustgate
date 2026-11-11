"""Models for product discovery, candidate evaluation, and safe proposal selection."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.models.policy import PurchaseMandate, MandatePolicyEvaluationResponse


class DiscoveredProduct(BaseModel):
    """Normalized schema for candidate products from discovery catalogs."""
    product_id: str = Field(..., description="Unique product identifier (e.g. ASIN or catalog ID)")
    name: str = Field(..., description="Product name or title")
    description: str = Field(default="", description="Product description")
    category: str = Field(default="General", description="Product category")
    price: float = Field(..., ge=0, description="Product price in specified currency")
    currency: str = Field(default="USD", description="Currency ISO code (e.g. USD, INR, EUR)")
    image_url: Optional[str] = Field(default=None, description="Image thumbnail URL")
    condition: str = Field(
        default="unknown",
        description="Product condition: new, used, refurbished, or unknown",
    )
    merchant_name: str = Field(default="Unknown Seller", description="Selling merchant name")
    merchant_verified: bool = Field(default=False, description="Whether merchant verification is confirmed")
    verification_status: str = Field(
        default="UNKNOWN",
        description="Verification state: VERIFIED, UNVERIFIED, or UNKNOWN",
    )
    data_source: str = Field(
        default="local_demo_fixture",
        description="Origin catalog: amazon_creators_api, local_demo_fixture, dummyjson_api",
    )
    is_demo_data: bool = Field(
        default=True,
        description="Always True for demo fixtures. False ONLY for genuine live API data.",
    )
    demo_notice: str = Field(
        default="Fictional demonstration data. Not real-world merchant or pricing information.",
        description="Clear disclosure for prototype testing",
    )
    marketplace_id: str = Field(default="demo", description="Marketplace identifier (e.g. amazon, demo, channel3)")
    region: str = Field(default="US", description="Marketplace region (e.g. amazon.in, amazon.com, global)")
    data_freshness: str = Field(default="Simulated", description="Data timestamp or freshness indicator")
    purchase_url: Optional[str] = Field(default=None, description="Direct merchant or product buy URL")
    availability: Optional[str] = Field(default=None, description="Product inventory or stock status (e.g. InStock)")
    retailer: Optional[str] = Field(default=None, description="Retailer or domain hosting the listing")

    # Normalized hardware and specification attributes
    brand: Optional[str] = Field(default=None, description="Product brand name")
    model: Optional[str] = Field(default=None, description="Product model identifier")
    ram_gb: Optional[int] = Field(default=None, description="RAM size in GB")
    storage_gb: Optional[int] = Field(default=None, description="Storage capacity in GB")
    storage_type: Optional[str] = Field(default=None, description="Storage type (SSD, NVMe, eMMC, HDD)")
    processor: Optional[str] = Field(default=None, description="Processor name/tier")
    gpu: Optional[str] = Field(default=None, description="Graphics card or integrated GPU")
    screen_size: Optional[str] = Field(default=None, description="Screen size in inches")
    original_price: Optional[float] = Field(default=None, description="Original listing price before conversion")
    original_currency: Optional[str] = Field(default=None, description="Original listing currency ISO code")
    spec_verification_status: Optional[str] = Field(default="UNKNOWN", description="VERIFIED, UNVERIFIED, or UNKNOWN")
    enrichment_status: Optional[str] = Field(default=None, description="ENRICHED, PARTIAL, or COMPLETE")


class CandidateEvaluation(BaseModel):
    """Candidate product paired with its deterministic policy evaluation."""
    product: DiscoveredProduct
    policy_result: MandatePolicyEvaluationResponse
    approved: bool = Field(..., description="Whether the candidate passes all mandate rules")
    status: str = Field(..., description="APPROVED, NEEDS_VERIFICATION, or BLOCKED")
    budget_remaining: float = Field(..., description="Mandate max_amount minus candidate total")
    currency: str = Field(..., description="Candidate currency")
    can_select: bool = Field(..., description="True only if approved by policy engine")
    selection_blocked_reason: Optional[str] = Field(
        default=None,
        description="Explanation if candidate is unselectable due to policy violation",
    )
    unverified_reasons: Optional[List[str]] = Field(
        default=None,
        description="List of specific specs that could not be verified",
    )
    enrichment_status: Optional[str] = Field(
        default=None,
        description="Metadata enrichment status (ENRICHED, PARTIAL, NOT_NEEDED)",
    )


class ProposalSearchRequest(BaseModel):
    """Request payload for discovering and evaluating candidate proposals."""
    mandate: PurchaseMandate = Field(..., description="Confirmed purchase mandate")
    query: Optional[str] = Field(default="", description="Search query keywords")
    catalog_mode: str = Field(
        default="demo",
        description="Catalog source mode: 'demo' (deterministic fixtures) or 'external' (DummyJSON API)",
    )
    marketplace_id: str = Field(
        default="demo",
        description="Selected marketplace: 'amazon' or 'demo'",
    )
    region: Optional[str] = Field(
        default=None,
        description="Selected region (e.g. amazon.in, amazon.com, demo_us, demo_in)",
    )
    page: int = Field(default=1, ge=1, description="Page number for pagination")
    limit: int = Field(default=10, ge=1, le=50, description="Results per page limit")
    offset: int = Field(default=0, ge=0, description="Result offset")
    page_token: Optional[str] = Field(default=None, description="Continuation token for provider pagination")


class ProposalSearchResponse(BaseModel):
    """Response containing evaluated candidate proposals and catalog telemetry."""
    query: str = Field(default="", description="The executed search query")
    candidates: List[CandidateEvaluation] = Field(default_factory=list)
    discovered_count: int = Field(default=0, description="Total candidate items discovered from provider")
    enriched_count: int = Field(default=0, description="Number of items enriched via metadata/detail queries")
    eligible_count: int = Field(default=0, description="Number of fully eligible / approved candidates")
    unverified_count: int = Field(default=0, description="Number of relevant candidates needing spec verification")
    compliant_count: int = Field(default=0, description="Number of policy-approved candidates (alias to eligible_count)")
    blocked_count: int = Field(default=0, description="Number of policy-blocked candidates")
    total_count: int = Field(default=0, description="Total candidates in this response")
    has_more: bool = Field(default=False, description="Whether more results exist on the provider")
    page: int = Field(default=1, description="Current page number")
    total_pages: int = Field(default=1, description="Total estimated pages available")
    next_page_token: Optional[str] = Field(default=None, description="Continuation token for next page")
    catalog_mode: str = Field(default="demo", description="demo or external")
    data_source: str = Field(default="local_demo_fixture")
    is_demo_data: bool = Field(default=True)
    demo_notice: str = Field(
        default="All candidate products are demonstration fixtures or external demo catalog items. Never used for real payment execution."
    )
    marketplace_id: str = Field(default="demo", description="Selected marketplace identifier")
    marketplace_name: str = Field(default="TrustGate Demo Catalog", description="Selected marketplace title")
    region: str = Field(default="US", description="Active marketplace region")
    integration_state: str = Field(
        default="Connected",
        description="Integration state: Not Configured, Credentials Missing, Access Pending, Connected, Error",
    )
    setup_guidance: Optional[str] = Field(default=None, description="Steps needed if access is unconfigured")
    legal_notice: str = Field(
        default="",
        description="Mandatory compliance note for the chosen marketplace API",
    )
    data_freshness: str = Field(default="Simulated / Instant", description="Data timestamp or freshness indicator")
