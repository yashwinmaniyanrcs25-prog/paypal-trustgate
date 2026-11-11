"""FastAPI API endpoints for Channel3 Universal Product Graph integration."""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.marketplace import MarketplaceStatusResponse
from app.models.policy import PurchaseMandate
from app.models.proposal import (
    DiscoveredProduct,
    ProposalSearchRequest,
    ProposalSearchResponse,
)
from app.services.channel3_service import channel3_service
from app.services.product_discovery_service import product_discovery_service
from app.services.marketplaces.base import MarketplaceAccessError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Channel3 Universal Product Graph"])


class Channel3DirectSearchRequest(BaseModel):
    """Payload for searching Channel3 catalog directly."""
    query: str = Field(..., min_length=1, description="Natural language product query")
    limit: int = Field(default=10, ge=1, le=20, description="Maximum products to retrieve")
    currency: str = Field(default="USD", description="Currency preference (e.g. USD, EUR)")
    mandate: Optional[PurchaseMandate] = Field(
        default=None,
        description="Optional purchase mandate to evaluate items against deterministic policy engine",
    )


class Channel3TestResponse(BaseModel):
    """Sanitized test connection response."""
    success: bool
    configured: bool
    status: str
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    endpoint: str
    products_returned: Optional[int] = None
    sample_title: Optional[str] = None
    message: str


@router.get(
    "/status",
    response_model=MarketplaceStatusResponse,
    summary="Get Channel3 integration configuration status",
)
async def get_channel3_status() -> MarketplaceStatusResponse:
    """Returns authentic Channel3 connection status, supported regions, and legal disclaimer."""
    return channel3_service.get_integration_status()


@router.post(
    "/test-connection",
    response_model=Channel3TestResponse,
    summary="Test live connectivity to Channel3 API",
)
async def test_channel3_connection() -> Channel3TestResponse:
    """Tests authentication and latency against https://api.trychannel3.com/v1/search.

    Does not expose the API key.
    """
    result = await channel3_service.test_connection()
    return Channel3TestResponse(**result)


@router.post(
    "/search",
    summary="Search products via Channel3 and evaluate against mandate if provided",
)
async def search_channel3(payload: Channel3DirectSearchRequest):
    """Performs live product discovery through Channel3.

    If a mandate is provided, evaluates every candidate against TrustGate's
    TG-001 through TG-007 deterministic policy invariants.
    """
    try:
        if payload.mandate:
            # Full evaluation path through product discovery service
            return await product_discovery_service.search_candidates(
                mandate=payload.mandate,
                query=payload.query,
                marketplace_id="channel3",
                region="global",
            )
        else:
            # Direct normalized discovery
            products = await channel3_service.search_products(
                query=payload.query,
                limit=payload.limit,
                currency=payload.currency,
            )
            return {
                "products": products,
                "count": len(products),
                "data_source": "channel3_api",
                "is_demo_data": False,
                "query": payload.query,
            }
    except MarketplaceAccessError as acc_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "CHANNEL3_ACCESS_ERROR",
                "message": acc_err.message,
                "state": acc_err.state.value,
                "setup_guidance": acc_err.setup_guidance,
            },
        )
    except Exception as exc:
        logger.error(f"Channel3 search endpoint error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Channel3 search failed: {str(exc)}",
        )

