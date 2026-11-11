"""Domain models for marketplace integrations and provider adapters."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class MarketplaceIntegrationState(str, Enum):
    """Lifecycle and configuration state of a marketplace provider adapter."""
    NOT_CONFIGURED = "Not Configured"
    CREDENTIALS_MISSING = "Credentials Missing"
    ACCESS_PENDING = "Access Pending"
    CONNECTED = "Connected"
    ERROR = "Error"


class MarketplaceRegion(BaseModel):
    """Regional marketplace endpoint and currency specifications."""
    id: str = Field(..., description="Region identifier (e.g. amazon.in, amazon.com)")
    name: str = Field(..., description="User-friendly region title")
    currency: str = Field(..., description="Local currency code (INR, USD, EUR, etc.)")
    host: str = Field(..., description="Marketplace API hostname or endpoint")
    is_default: bool = Field(default=False)


class MarketplaceStatusResponse(BaseModel):
    """Status, supported regions, and integration readiness of a marketplace."""
    marketplace_id: str = Field(..., description="Unique marketplace identifier (e.g. amazon, demo)")
    name: str = Field(..., description="Marketplace name")
    state: MarketplaceIntegrationState = Field(..., description="Current connection state")
    is_connected: bool = Field(default=False, description="True only if live verified API access is active")
    configured: bool = Field(default=False, description="True if credentials are set")
    supported_regions: List[MarketplaceRegion] = Field(default_factory=list)
    active_region: str = Field(..., description="Currently queried or default region")
    currency: str = Field(default="USD")
    message: str = Field(..., description="Clear explanation of the current integration state")
    setup_guidance: Optional[str] = Field(
        default=None,
        description="Actionable steps or environment variables required to activate live access",
    )
    legal_disclaimer: str = Field(
        default="",
        description="Mandatory compliance and licensing disclosure for marketplace data",
    )

