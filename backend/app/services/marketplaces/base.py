"""Abstract base class for marketplace provider adapters."""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.models.marketplace import (
    MarketplaceStatusResponse,
    MarketplaceRegion,
    MarketplaceIntegrationState,
)
from app.models.proposal import DiscoveredProduct


class MarketplaceAccessError(Exception):
    """Raised when marketplace API access is unavailable or unconfigured."""
    def __init__(self, state: MarketplaceIntegrationState, message: str, setup_guidance: Optional[str] = None):
        super().__init__(message)
        self.state = state
        self.message = message
        self.setup_guidance = setup_guidance


class BaseMarketplaceAdapter(ABC):
    """Common interface for marketplace adapters (Amazon Creators, Demo, etc.).

    Modular and strictly decoupled from the deterministic TrustGate policy engine.
    """

    @property
    @abstractmethod
    def marketplace_id(self) -> str:
        """Unique identifier for this marketplace adapter (e.g. 'amazon', 'demo')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable marketplace name (e.g. 'Amazon Marketplace')."""
        pass

    @property
    @abstractmethod
    def supported_regions(self) -> List[MarketplaceRegion]:
        """List of supported regional marketplaces and currencies."""
        pass

    @abstractmethod
    def get_integration_status(self, region: Optional[str] = None) -> MarketplaceStatusResponse:
        """Return integration state: Not Configured, Credentials Missing, Access Pending, Connected, Error."""
        pass

    @abstractmethod
    async def search_products(
        self, query: str, region: str, limit: int = 10
    ) -> List[DiscoveredProduct]:
        """Search products in this marketplace.

        Raises MarketplaceAccessError if credentials or approved API access are missing.
        Must NEVER scrape web pages or fabricate live marketplace results.
        """
        pass

    @abstractmethod
    async def get_product_details(
        self, product_id: str, region: str
    ) -> Optional[DiscoveredProduct]:
        """Fetch item details by marketplace product ID or ASIN."""
        pass

    @abstractmethod
    def normalize_product(self, raw_item: dict, region: str) -> DiscoveredProduct:
        """Normalize raw provider payload into TrustGate's DiscoveredProduct schema."""
        pass

