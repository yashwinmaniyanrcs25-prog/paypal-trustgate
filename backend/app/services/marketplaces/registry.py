"""Registry of available marketplace provider adapters."""

from typing import Dict, List, Optional
from app.models.marketplace import MarketplaceStatusResponse
from app.services.marketplaces.base import BaseMarketplaceAdapter
from app.services.marketplaces.channel3_adapter import channel3_adapter
from app.services.marketplaces.amazon_adapter import amazon_adapter
from app.services.marketplaces.demo_adapter import demo_adapter


class MarketplaceRegistry:
    """Registry coordinating available marketplace adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseMarketplaceAdapter] = {
            "channel3": channel3_adapter,
            "amazon": amazon_adapter,
            "demo": demo_adapter,
        }

    def get_adapter(self, marketplace_id: Optional[str] = None) -> BaseMarketplaceAdapter:
        """Lookup adapter by marketplace_id; falls back to demo adapter if unknown."""
        key = (marketplace_id or "demo").strip().lower()
        if key in ("channel3", "channel3_api", "live", "c3"):
            return self._adapters["channel3"]
        if key in ("amazon", "amazon_creators", "amazon.in", "amazon.com"):
            return self._adapters["amazon"]
        return self._adapters.get("demo", demo_adapter)

    def list_marketplaces(self, region: Optional[str] = None) -> List[MarketplaceStatusResponse]:
        """Return integration statuses for all registered marketplaces."""
        statuses: List[MarketplaceStatusResponse] = []
        # Return Channel3 (live multi-merchant API), Amazon Creators API, then Demo Fixtures
        for key in ("channel3", "amazon", "demo"):
            adapter = self._adapters.get(key)
            if adapter:
                statuses.append(adapter.get_integration_status(region))
        return statuses


marketplace_registry = MarketplaceRegistry()


