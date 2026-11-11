"""Deterministic demo catalog provider adapter for TrustGate.

Provides labeled test fixtures to test all 7 TrustGate policy invariants
offline and safely without network calls or marketplace API accounts.
Candidates are strictly isolated and never mixed with real marketplace results.
"""

from typing import List, Optional
from app.models.marketplace import (
    MarketplaceStatusResponse,
    MarketplaceRegion,
    MarketplaceIntegrationState,
)
from app.models.proposal import DiscoveredProduct
from app.services.marketplaces.base import BaseMarketplaceAdapter


class DemoCatalogAdapter(BaseMarketplaceAdapter):
    """Adapter for local simulation fixtures."""

    _SUPPORTED_REGIONS = [
        MarketplaceRegion(
            id="demo_us",
            name="Demo Fixtures (USD $)",
            currency="USD",
            host="local.trustgate.demo",
            is_default=True,
        ),
        MarketplaceRegion(
            id="demo_in",
            name="Demo Fixtures (INR ₹)",
            currency="INR",
            host="local.trustgate.demo",
            is_default=False,
        ),
    ]

    @property
    def marketplace_id(self) -> str:
        return "demo"

    @property
    def name(self) -> str:
        return "TrustGate Demo Fixtures"

    @property
    def supported_regions(self) -> List[MarketplaceRegion]:
        return self._SUPPORTED_REGIONS

    def get_integration_status(self, region: Optional[str] = None) -> MarketplaceStatusResponse:
        reg_id = (region or "demo_us").strip().lower()
        reg = self._SUPPORTED_REGIONS[0] if "in" not in reg_id else self._SUPPORTED_REGIONS[1]

        return MarketplaceStatusResponse(
            marketplace_id=self.marketplace_id,
            name=self.name,
            state=MarketplaceIntegrationState.CONNECTED,
            is_connected=True,
            configured=True,
            supported_regions=self.supported_regions,
            active_region=reg.id,
            currency=reg.currency,
            message="Demo catalog active. Deterministic fixtures available for testing 7 policy invariants.",
            setup_guidance=None,
            legal_disclaimer="Simulated catalog data for local demonstration only. Not for real payment execution.",
        )

    async def search_products(
        self, query: str, region: str = "demo_us", limit: int = 10
    ) -> List[DiscoveredProduct]:
        """Returns deterministic labeled demo candidates."""
        curr = "INR" if "in" in region.lower() else "USD"
        base_budget = 60000.0 if curr == "INR" else 150.0

        # We construct products similar to the previous generator
        q_label = query.title() if query else "Product"

        fixtures = [
            # Candidate 1: Compliant
            DiscoveredProduct(
                product_id="demo_compliant_001",
                name=f"{q_label} Pro Edition (TrustGate Certified)",
                description=f"Authentic {query} matching user mandate. Full warranty, direct fulfillment.",
                category="Verified Electronics",
                price=round(base_budget * 0.75, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Official Authorized Merchant",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated compliant candidate for prototype demonstration.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 2: Over Budget (TG-001)
            DiscoveredProduct(
                product_id="demo_overbudget_002",
                name=f"{q_label} Ultra Max (Excessive Price)",
                description=f"High-end premium configuration exceeding mandate spending limit.",
                category="Verified Electronics",
                price=round(base_budget * 1.35, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Official Authorized Merchant",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated over-budget candidate (Violates TG-001).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 3: Unverified Merchant (TG-004)
            DiscoveredProduct(
                product_id="demo_unverified_003",
                name=f"{q_label} Budget Seller Special",
                description=f"Low priced {query} sold by an unverified third-party marketplace seller.",
                category="Marketplace Deals",
                price=round(base_budget * 0.60, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Unknown Shady Wholesale",
                merchant_verified=False,
                verification_status="UNVERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated unverified merchant candidate (Violates TG-004).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 4: Non-compliant Condition (TG-003)
            DiscoveredProduct(
                product_id="demo_condition_004",
                name=f"{q_label} Grade-B Refurbished Lot",
                description=f"Open-box refurbished unit. Cosmetic wear on chassis, 90-day vendor warranty.",
                category="Refurbished Goods",
                price=round(base_budget * 0.50, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80",
                condition="refurbished",
                merchant_name="Official Authorized Merchant",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated non-compliant condition candidate (Violates TG-003).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 5: Add-ons & Extra Charges (TG-005)
            DiscoveredProduct(
                product_id="cand_addons_005",
                name=f"{q_label} Deluxe Bundle with Hidden Fees",
                description=f"Includes bundled accessory pack and hidden activation fee.",
                category="Verified Electronics",
                price=round(base_budget * 0.70, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Official Authorized Merchant",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated candidate with unexpected charges and add-ons (Violates TG-005).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 6: Currency Mismatch (TG-002)
            DiscoveredProduct(
                product_id="demo_currency_006",
                name=f"{q_label} European Import Unit",
                description=f"International SKU priced in mismatched currency without conversion.",
                category="International Imports",
                price=round(base_budget * 0.65, 2),
                currency="EUR" if curr == "USD" else "USD",
                image_url="https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Official Authorized Merchant",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated currency mismatch candidate (Violates TG-002).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
        ]
        return fixtures[:limit]

    async def get_product_details(
        self, product_id: str, region: str = "demo_us"
    ) -> Optional[DiscoveredProduct]:
        items = await self.search_products(query="Product", region=region, limit=10)
        for it in items:
            if it.product_id == product_id:
                return it
        return None

    def normalize_product(self, raw_item: dict, region: str) -> DiscoveredProduct:
        return DiscoveredProduct(**raw_item)


demo_adapter = DemoCatalogAdapter()

