"""API endpoints for marketplace discovery, candidate evaluation, and safe selection."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.policy import PurchaseMandate, MandatePolicyEvaluationResponse
from app.models.marketplace import MarketplaceStatusResponse
from app.models.proposal import (
    ProposalSearchRequest,
    ProposalSearchResponse,
    DiscoveredProduct,
)
from app.services.product_discovery_service import product_discovery_service
from app.services.marketplaces.registry import marketplace_registry
from app.services.policy_engine import policy_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Marketplace Discovery & Selection"])


class StageProposalRequest(BaseModel):
    """Payload to stage an approved candidate proposal for human review."""
    mandate: PurchaseMandate
    candidate: DiscoveredProduct
    user_id: Optional[str] = "user_demo"


class StageProposalResponse(BaseModel):
    """Staged proposal receipt confirming proposal is ready for human sign-off."""
    staged_proposal_id: str
    product_name: str
    price: float
    currency: str
    merchant_name: str
    policy_approved: bool
    requires_human_approval: bool = True
    payment_executed: bool = False
    message: str
    demo_notice: str
    is_demo_data: bool = False


@router.get(
    "/marketplaces",
    response_model=List[MarketplaceStatusResponse],
    summary="List supported marketplaces, their regions, and authentic integration statuses",
)
async def list_marketplaces(
    region: Optional[str] = Query(default=None, description="Optional region filter (e.g. amazon.in)")
) -> List[MarketplaceStatusResponse]:
    """Returns available marketplace integrations (e.g. Amazon Creators API, Demo Fixtures)

    with their authentic integration states: Not Configured, Credentials Missing, Access Pending, Connected, or Error.
    """
    return marketplace_registry.list_marketplaces(region=region)


@router.get(
    "/marketplaces/{marketplace_id}/status",
    response_model=MarketplaceStatusResponse,
    summary="Get integration status for a specific marketplace adapter and region",
)
async def get_marketplace_status(
    marketplace_id: str,
    region: Optional[str] = Query(default=None, description="Target region (e.g. amazon.in, amazon.com)")
) -> MarketplaceStatusResponse:
    """Returns detailed integration status and configuration guidance for a marketplace adapter."""
    adapter = marketplace_registry.get_adapter(marketplace_id)
    return adapter.get_integration_status(region=region)


@router.post(
    "/search",
    response_model=ProposalSearchResponse,
    summary="Discover candidates and run deterministic policy evaluation on each",
)
async def search_proposals(payload: ProposalSearchRequest) -> ProposalSearchResponse:
    """Discover candidate products from selected marketplace or demo fixtures,

    and run each candidate through the deterministic TrustGate policy engine.
    """
    try:
        response = await product_discovery_service.search_candidates(
            mandate=payload.mandate,
            query=payload.query,
            catalog_mode=payload.catalog_mode,
            marketplace_id=payload.marketplace_id,
            region=payload.region,
        )
        return response
    except Exception as exc:
        logger.error(f"Error searching and evaluating proposals: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Proposal discovery failed: {str(exc)}",
        )


@router.post(
    "/stage",
    response_model=StageProposalResponse,
    summary="Stage an approved candidate proposal for human sign-off",
)
async def stage_proposal(payload: StageProposalRequest) -> StageProposalResponse:
    """Safely stages an approved candidate proposal.

    SECURITY INVARIANTS:
    1. Only policy-approved candidates can be staged.
    2. Zero autonomous payment execution. Selecting a proposal DOES NOT execute a payment.
    3. Demo candidates are barred from proceeding to any real payment processing.
    4. Human approval remains mandatory.
    """
    # Invariant: Price must be strictly positive
    if payload.candidate.price is None or payload.candidate.price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Candidate cannot be staged: Invalid non-positive price ({payload.candidate.price}). Verified price > 0 is required.",
        )

    # Build transaction for policy verification check
    from app.models.policy import ProposedTransaction

    tx = ProposedTransaction(
        product_name=payload.candidate.name,
        product_description=payload.candidate.description,
        product_price=payload.candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=payload.candidate.price,
        currency=payload.candidate.currency,
        merchant_name=payload.candidate.merchant_name,
        merchant_verified=payload.candidate.merchant_verified,
        product_condition=payload.candidate.condition,
        add_ons=[],
    )

    evaluation = policy_engine.evaluate_mandate(
        mandate=payload.mandate,
        transaction=tx,
        caller_role="human_user",
    )

    if not evaluation.approved:
        violations_str = "; ".join(v.message for v in evaluation.violations)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Candidate cannot be staged: Policy evaluation blocked this item. Violations: {violations_str}",
        )

    import uuid
    staged_id = f"stg_{uuid.uuid4().hex[:8]}"

    # Save to trusted server-side state for safe checkout derivation
    from app.services.proposal_store import proposal_store
    proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=payload.mandate,
        candidate=payload.candidate,
        policy_evaluation=evaluation,
        user_id=payload.user_id or "user_demo",
    )

    # Invariant: Demo candidates cannot trigger real financial transactions
    is_demo = payload.candidate.is_demo_data
    demo_msg = (
        "Demonstration candidate staged for invariant review only. Barred from real payment execution."
        if is_demo
        else "Authentic marketplace proposal staged. Explicit human approval in PayPal Sandbox required."
    )

    return StageProposalResponse(
        staged_proposal_id=staged_id,
        product_name=payload.candidate.name,
        price=payload.candidate.price,
        currency=payload.candidate.currency,
        merchant_name=payload.candidate.merchant_name,
        policy_approved=True,
        requires_human_approval=True,
        payment_executed=False,
        message=(
            f"Candidate proposal staged successfully. Policy engine approved item. "
            f"Payment remains held awaiting human authorization."
        ),
        demo_notice=demo_msg,
        is_demo_data=is_demo,
    )
