"""Channel3 marketplace provider adapter for PayPal TrustGate.

Implements BaseMarketplaceAdapter to integrate Channel3's multi-merchant product graph
into TrustGate's marketplace provider registry.
"""

import logging
from typing import List, Optional
from app.models.marketplace import (
    MarketplaceStatusResponse,
    MarketplaceRegion,
    MarketplaceIntegrationState,
)
from app.models.proposal import DiscoveredProduct
from app.services.marketplaces.base import BaseMarketplaceAdapter, MarketplaceAccessError
from app.services.channel3_service import channel3_service, SUPPORTED_CHANNEL3_REGIONS

logger = logging.getLogger(__name__)


class Channel3Adapter(BaseMarketplaceAdapter):
    """Adapter connecting Channel3 Universal Product Graph to TrustGate."""

    @property
    def marketplace_id(self) -> str:
        return "channel3"

    @property
    def name(self) -> str:
        return "Channel3 Universal Product Graph"

    @property
    def supported_regions(self) -> List[MarketplaceRegion]:
        return SUPPORTED_CHANNEL3_REGIONS

    def get_integration_status(self, region: Optional[str] = None) -> MarketplaceStatusResponse:
        """Inspects backend configuration and returns authentic integration status."""
        return channel3_service.get_integration_status()

    async def search_products(
        self, query: str, region: str = "global", limit: int = 10
    ) -> List[DiscoveredProduct]:
        """Queries Channel3 API for candidate products.

        Raises MarketplaceAccessError if API key is unconfigured or request fails.
        """
        currency = "USD"
        return await channel3_service.search_products(
            query=query,
            limit=limit,
            currency=currency,
            region=region,
        )

    async def get_product_details(
        self, product_id: str, region: str = "global"
    ) -> Optional[DiscoveredProduct]:
        """Fetch item details by Channel3 product ID.

        Raises MarketplaceAccessError if credentials or approved API access are missing.
        """
        return await channel3_service.get_product_details(product_id=product_id, region=region)

    def normalize_product(self, raw_item: dict, region: str = "global") -> DiscoveredProduct:
        """Normalize raw provider payload into TrustGate's DiscoveredProduct schema.

        CRITICAL SECURITY & INTEGRITY INVARIANTS:
        1. Condition is never assumed to be new if unknown.
        2. Merchant verification is never assumed without confirmed domain matching.
        3. Real data tagging: is_demo_data is FALSE (genuine Channel3 graph data).
        4. Freshness: Stamped with Live Channel3 Universal Graph.
        5. Price Validation: Must have a strictly positive price (> 0.00). Never defaults to 0.00.
        """
        normalized = channel3_service._normalize_product(raw_item, fallback_currency="USD")
        if normalized:
            if region and region != "global":
                normalized.region = region
            return normalized

        # Invariant 5 & Requirement 7: If candidate has no valid positive price, reject it explicitly.
        # Never invent a price, silently substitute a default (0.0), or fabricate provider data.
        raw_id = str(raw_item.get("id") or "unknown")
        raise ValueError(
            f"Cannot normalize Channel3 candidate '{raw_id}': No valid positive price found in provider payload. "
            "TrustGate strictly requires a verified positive price (> 0.00)."
        )


channel3_adapter = Channel3Adapter()

