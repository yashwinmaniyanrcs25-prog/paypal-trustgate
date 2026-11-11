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
from app.services.product_normalizer import product_normalizer


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
        self,
        query: str,
        region: str = "demo_us",
        limit: int = 10,
        page: int = 1,
        offset: int = 0,
        page_token: Optional[str] = None,
    ) -> List[DiscoveredProduct]:
        """Returns deterministic labeled demo candidates."""
        curr = "INR" if ("in" in region.lower() or "india" in region.lower()) else "USD"
        q_lower = (query or "").lower().strip()

        # Determine budget base and category based on query
        is_laptop = "laptop" in q_lower or "notebook" in q_lower
        is_mouse = "mouse" in q_lower or "mice" in q_lower
        is_keyboard = "keyboard" in q_lower or "keychron" in q_lower

        if is_laptop:
            base_budget = 60000.0 if curr == "INR" else 150.0
            category = "Laptops"
            c1_name = "Lenovo IdeaPad Slim 3 15.6-inch Laptop (Intel Core i5, 16GB RAM, 512GB SSD)" if curr == "INR" else "Lenovo IdeaPad 3 15.6-inch Laptop (Intel Core i5, 16GB RAM, 512GB SSD)"
            c1_desc = f"Brand new Lenovo IdeaPad laptop matching {curr} mandate. Full 1-year manufacturer warranty."
            c1_img = "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80"
            c1_merchant = "Official Lenovo Brand Store"

            c2_name = "Dell XPS 15 OLED Laptop (Intel Core i7, 32GB RAM, 1TB SSD)"
            c2_desc = "High-end premium configuration exceeding mandate spending limit."
            c2_img = "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=400&q=80"

            c3_name = "ASUS VivoBook Go 14 Laptop (AMD Ryzen 3)"
            c3_desc = "Budget laptop sold by an unverified third-party marketplace seller."
            c3_img = "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80"

            c4_name = "HP Pavilion 14 Refurbished Grade-A Laptop"
            c4_desc = "Open-box refurbished unit. Cosmetic wear on chassis, 90-day vendor warranty."
            c4_img = "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80"

            c5_name = "Acer Aspire 5 Laptop Deluxe Bundle with Mandatory Accessories"
            c5_desc = "Includes bundled laptop sleeve, mouse, and hidden activation fees."
            c5_img = "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80"

            c6_name = "MacBook Air M1 Laptop (European Import Model)"
            c6_desc = "International SKU priced in mismatched currency without conversion."
            c6_img = "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=400&q=80"
            c6_price = round((720.0 if curr == "INR" else 150.0) * 0.65, 2)
            c6_curr = "USD" if curr == "INR" else "EUR"

        elif is_mouse:
            base_budget = 4500.0 if curr == "INR" else 100.0
            category = "Computer Accessories / Mice"
            c1_name = "Logitech MX Master 3S Wireless Performance Mouse"
            c1_desc = "Ergonomic wireless mouse with 8K DPI sensor, quiet clicks, and multi-device pairing."
            c1_img = "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=400&q=80"
            c1_merchant = "Logitech Official Brand Store"

            c2_name = "Razer Viper Mini Signature Edition Wireless Gaming Mouse"
            c2_desc = "Ultra-premium magnesium alloy wireless gaming mouse exceeding spending limits."
            c2_img = "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?auto=format&fit=crop&w=400&q=80"

            c3_name = "Generic RGB Wireless Optical Mouse (Bulk Pack)"
            c3_desc = "Low priced unbranded mouse sold by an unverified third-party marketplace seller."
            c3_img = "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80"

            c4_name = "Logitech MX Anywhere 2S Refurbished Mouse"
            c4_desc = "Open-box refurbished unit. Cosmetic wear on casing, 90-day vendor warranty."
            c4_img = "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80"

            c5_name = "Wireless Mouse Deluxe Bundle with Extended Warranty and Mousepad"
            c5_desc = "Includes bundled oversized mousepad and mandatory warranty activation fee."
            c5_img = "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80"

            c6_name = "Apple Magic Mouse (European Import Model)"
            c6_desc = "International SKU priced in mismatched currency without conversion."
            c6_img = "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=400&q=80"
            c6_price = 79.00 if curr == "INR" else 65.00
            c6_curr = "USD" if curr == "INR" else "EUR"

        elif is_keyboard:
            base_budget = 12000.0 if curr == "INR" else 150.0
            category = "Keyboards & Input Devices"
            c1_name = "Keychron K2 Wireless Mechanical Keyboard (Version 2)"
            c1_desc = "Authentic mechanical keyboard matching user mandate. Full warranty, direct fulfillment."
            c1_img = "https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=400&q=80"
            c1_merchant = "Keychron Official Direct"

            c2_name = "Custom CNC Aluminum Mechanical Keyboard (Excessive Price)"
            c2_desc = "High-end custom keyboard exceeding mandate spending limit."
            c2_img = "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=400&q=80"

            c3_name = "Unbranded Mechanical Keyboard Kit"
            c3_desc = "Low priced keyboard sold by an unverified third-party marketplace seller."
            c3_img = "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80"

            c4_name = "Keychron K2 Refurbished Lot B"
            c4_desc = "Open-box refurbished unit. Cosmetic wear on chassis, 90-day vendor warranty."
            c4_img = "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80"

            c5_name = "Keychron K2 Deluxe Bundle with Hidden Fees"
            c5_desc = "Includes bundled aviator cable, keycap puller, and mandatory warranty fee."
            c5_img = "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80"

            c6_name = "Keychron K2 European Import Model"
            c6_desc = "International SKU priced in mismatched currency without conversion."
            c6_img = "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=400&q=80"
            c6_price = 119.00 if curr == "INR" else 110.00
            c6_curr = "USD" if curr == "INR" else "EUR"

        else:
            base_budget = 60000.0 if curr == "INR" else 150.0
            category = "Verified Electronics"
            q_label = query.title() if query else "Product"
            c1_name = f"{q_label} Pro Edition (TrustGate Certified)"
            c1_desc = f"Authentic {query} matching user mandate. Full warranty, direct fulfillment."
            c1_img = "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80"
            c1_merchant = "Official Authorized Merchant"

            c2_name = f"{q_label} Ultra Max (Excessive Price)"
            c2_desc = "High-end premium configuration exceeding mandate spending limit."
            c2_img = "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=400&q=80"

            c3_name = f"{q_label} Budget Seller Special"
            c3_desc = f"Low priced {query} sold by an unverified third-party marketplace seller."
            c3_img = "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80"

            c4_name = f"{q_label} Grade-B Refurbished Lot"
            c4_desc = "Open-box refurbished unit. Cosmetic wear on chassis, 90-day vendor warranty."
            c4_img = "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80"

            c5_name = f"{q_label} Deluxe Bundle with Hidden Fees"
            c5_desc = "Includes bundled accessory pack and hidden activation fee."
            c5_img = "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80"

            c6_name = f"{q_label} European Import Unit"
            c6_desc = "International SKU priced in mismatched currency without conversion."
            c6_img = "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=400&q=80"
            c6_price = round(base_budget * 0.65, 2)
            c6_curr = "EUR" if curr == "USD" else "USD"

        fixtures = [
            # Candidate 1: Compliant (Eligible)
            DiscoveredProduct(
                product_id="demo_compliant_001",
                name=c1_name,
                description=c1_desc,
                category=category,
                price=round(base_budget * 0.75, 2),
                currency=curr,
                image_url=c1_img,
                condition="new",
                merchant_name=c1_merchant,
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
                name=c2_name,
                description=c2_desc,
                category=category,
                price=round(base_budget * 1.35, 2),
                currency=curr,
                image_url=c2_img,
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
                name=c3_name,
                description=c3_desc,
                category=category,
                price=round(base_budget * 0.60, 2),
                currency=curr,
                image_url=c3_img,
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
                name=c4_name,
                description=c4_desc,
                category=category,
                price=round(base_budget * 0.50, 2),
                currency=curr,
                image_url=c4_img,
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
                name=c5_name,
                description=c5_desc,
                category=category,
                price=round(base_budget * 0.70, 2),
                currency=curr,
                image_url=c5_img,
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
                name=c6_name,
                description=c6_desc,
                category=category,
                price=c6_price,
                currency=c6_curr,
                image_url=c6_img,
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
            # Candidate 7: Additional Compliant (Eligible) Laptop
            DiscoveredProduct(
                product_id="demo_compliant_007",
                name="Acer Swift 3 14-inch Laptop (AMD Ryzen 5, 16GB RAM, 512GB SSD)",
                description=f"Authentic Acer Swift 3 ultraportable matching {curr} mandate. 16GB RAM, 512GB SSD, Ryzen 5 5500U.",
                category=category,
                price=round(base_budget * 0.78, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Acer Authorized Store",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated compliant candidate for breadth testing.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 8: Additional Compliant (Eligible) Laptop
            DiscoveredProduct(
                product_id="demo_compliant_008",
                name="ASUS VivoBook 15 Slim Laptop (Intel Core i5, 16GB RAM, 512GB SSD)",
                description=f"Brand new ASUS VivoBook laptop matching {curr} requirements. Core i5-1235U, 16GB RAM, 512GB SSD.",
                category=category,
                price=round(base_budget * 0.82, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="ASUS Store Direct",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated compliant candidate for breadth testing.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 9: Additional Compliant (Eligible) Laptop
            DiscoveredProduct(
                product_id="demo_compliant_009",
                name="HP 15-dy2027od Laptop (Intel Core i5, 16GB RAM, 512GB SSD)",
                description=f"Authentic HP 15 laptop with Intel Core i5 processor, 16GB RAM, and 512GB SSD storage.",
                category=category,
                price=round(base_budget * 0.72, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="HP Direct Official",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated compliant candidate for breadth testing.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 10: Needs Verification (Missing RAM and storage in listing text - enrichable via details)
            DiscoveredProduct(
                product_id="demo_unverified_010",
                name="Dell Inspiron 14 Portable Notebook (Intel Core i5)",
                description="Dell Inspiron 14 lightweight laptop featuring Intel Core i5 processor and Full HD display.",
                category=category,
                price=round(base_budget * 0.68, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Dell Store Official",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated candidate with missing specs in snippet (Enrichable via detail endpoint).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 11: Needs Verification (Missing RAM in listing, remains unverified even after lookup)
            DiscoveredProduct(
                product_id="demo_unverified_011",
                name="Samsung Galaxy Book Ultra-Slim Laptop",
                description="Ultra-thin portable laptop with AMOLED display and Intel Core i5. System memory not specified.",
                category=category,
                price=round(base_budget * 0.79, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Samsung Authorized Partner",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated candidate with unverified specifications (Cannot be approved without confirmation).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 12: Blocked: Out of Stock (TG-006)
            DiscoveredProduct(
                product_id="demo_outofstock_012",
                name="Lenovo ThinkPad E14 Laptop (Intel Core i5, 16GB RAM, 512GB SSD)",
                description="High reliability business laptop currently discontinued and out of stock across warehouses.",
                category=category,
                price=round(base_budget * 0.74, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Lenovo Brand Store",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated out of stock candidate (Violates TG-006 inventory availability).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
                availability="OutOfStock",
            ),
            # Candidate 13: Additional Compliant (Eligible) Laptop
            DiscoveredProduct(
                product_id="demo_compliant_013",
                name="HP Envy x360 2-in-1 Laptop (Intel Core i7, 16GB RAM, 512GB SSD)",
                description=f"Convertible touchscreen laptop with Intel Core i7, 16GB RAM, 512GB SSD matching mandate.",
                category=category,
                price=round(base_budget * 0.88, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="HP Direct Official",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated compliant candidate for breadth testing.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 14: Needs Verification (Missing storage capacity)
            DiscoveredProduct(
                product_id="demo_unverified_014",
                name="Framework Laptop 13 Modular Edition (Intel Core i5, 16GB RAM)",
                description="Modular repairable laptop with Intel Core i5 processor and 16GB RAM. Storage capacity unlisted.",
                category=category,
                price=round(base_budget * 0.85, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Framework Computer Store",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated candidate with missing storage capacity specification.",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
            # Candidate 15: Over Budget (TG-001)
            DiscoveredProduct(
                product_id="demo_overbudget_015",
                name="Apple MacBook Pro 16 Laptop (Apple M3 Max, 36GB RAM, 1TB SSD)",
                description="Pro workstation laptop with M3 Max processor exceeding budget threshold.",
                category=category,
                price=round(base_budget * 2.10, 2),
                currency=curr,
                image_url="https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=400&q=80",
                condition="new",
                merchant_name="Apple Store Official",
                merchant_verified=True,
                verification_status="VERIFIED",
                data_source="local_demo_fixture",
                is_demo_data=True,
                demo_notice="Simulated over-budget candidate (Violates TG-001).",
                marketplace_id="demo",
                region=region,
                data_freshness="Simulated",
            ),
        ]

        # Normalize specifications across all fixtures
        for f in fixtures:
            specs = product_normalizer.normalize_specifications(
                title=f.name,
                description=f.description,
                category=f.category,
                raw_metadata={
                    "brand": f.merchant_name,
                    "availability": f.availability,
                    "retailer": f.merchant_name,
                },
            )
            for k, v in specs.items():
                if getattr(f, k, None) is None:
                    setattr(f, k, v)

        # Pagination slicing
        if offset > 0:
            start_idx = offset
            end_idx = start_idx + limit
            return fixtures[start_idx:end_idx]
        elif page > 1:
            start_idx = 6
            end_idx = start_idx + limit
            return fixtures[start_idx:end_idx]
        elif limit in (6, 10):
            # Page 1 returns standard 6 primary fixtures preserving deterministic verification baseline
            return fixtures[:6]
        else:
            return fixtures[:limit]

    async def get_product_details(
        self, product_id: str, region: str = "demo_us"
    ) -> Optional[DiscoveredProduct]:
        # Fetch all fixtures across pages
        items = await self.search_products(query="Product", region=region, limit=100, page=1)
        for it in items:
            if it.product_id == product_id:
                # If demo_unverified_010, simulate successful detail enrichment
                if product_id == "demo_unverified_010":
                    enriched = it.model_copy()
                    enriched.name = f"{it.name} (Intel Core i5, 16GB RAM, 512GB SSD)"
                    enriched.description = f"{it.description} Verified Specifications: 16GB DDR4 RAM, 512GB NVMe SSD, Intel Core i5."
                    enriched.ram_gb = 16
                    enriched.storage_gb = 512
                    enriched.storage_type = "NVMe SSD"
                    enriched.processor = "Intel Core i5"
                    enriched.spec_verification_status = "VERIFIED"
                    enriched.enrichment_status = "ENRICHED"
                    return enriched
                return it
        return None

    def normalize_product(self, raw_item: dict, region: str) -> DiscoveredProduct:
        return DiscoveredProduct(**raw_item)


demo_adapter = DemoCatalogAdapter()

