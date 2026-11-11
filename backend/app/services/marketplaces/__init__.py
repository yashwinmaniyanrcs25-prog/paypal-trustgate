"""Marketplace provider adapters package."""

from app.services.marketplaces.base import BaseMarketplaceAdapter, MarketplaceAccessError
from app.services.marketplaces.amazon_adapter import amazon_adapter, AmazonCreatorsAdapter
from app.services.marketplaces.demo_adapter import demo_adapter, DemoCatalogAdapter
from app.services.marketplaces.registry import marketplace_registry, MarketplaceRegistry

__all__ = [
    "BaseMarketplaceAdapter",
    "MarketplaceAccessError",
    "amazon_adapter",
    "AmazonCreatorsAdapter",
    "demo_adapter",
    "DemoCatalogAdapter",
    "marketplace_registry",
    "MarketplaceRegistry",
]

