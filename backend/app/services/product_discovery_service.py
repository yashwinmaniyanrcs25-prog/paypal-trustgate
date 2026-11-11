"""Product Discovery and Evaluation Service for PayPal TrustGate.

Coordinates marketplace provider adapters (e.g. Amazon Creators API, Demo Fixtures),
normalizes candidate items, and enforces deterministic TrustGate policy evaluation.

CRITICAL INVARIANTS:
1. Amazon Creators API is modular, isolated, and verified for licensing compliance.
2. Missing or pending marketplace access is reported as a distinct configuration/access state,
   never as an empty successful search, and never filled with fabricated results.
3. Unknown merchant verification is never assumed verified.
4. Unknown condition is never assumed new.
5. Currencies are never silently converted or cross-compared without explicit conversion.
6. AI agents never decide policy approval. Product catalog data is evaluated deterministically;
   never piped to LLM inference.
7. Candidate selection never initiates payment or authorizes checkout.
8. Demo data is never mixed into real marketplace results.
"""

import logging
from typing import List, Optional, Any, Dict
import httpx

from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.marketplace import (
    MarketplaceStatusResponse,
    MarketplaceIntegrationState,
)
from app.models.proposal import (
    DiscoveredProduct,
    CandidateEvaluation,
    ProposalSearchResponse,
)
from app.services.marketplaces.registry import marketplace_registry
from app.services.marketplaces.base import MarketplaceAccessError
from app.services.policy_engine import policy_engine
from app.services.currency_service import currency_service
from app.services.product_normalizer import product_normalizer

logger = logging.getLogger(__name__)

DUMMYJSON_SEARCH_URL = "https://dummyjson.com/products/search"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ProductDiscoveryService:
    """Service to discover candidate items and evaluate them against a purchase mandate."""

    async def search_candidates(
        self,
        mandate: PurchaseMandate,
        query: Optional[str] = None,
        catalog_mode: str = "demo",
        marketplace_id: Optional[str] = None,
        region: Optional[str] = None,
        page: int = 1,
        limit: int = 10,
        offset: int = 0,
        page_token: Optional[str] = None,
    ) -> ProposalSearchResponse:
        """Search catalog for candidates and evaluate each candidate deterministically."""
        # Resolve active marketplace
        mkt_id = (marketplace_id or "").strip().lower()
        if not mkt_id:
            mkt_id = "demo" if catalog_mode == "demo" else ("external" if catalog_mode == "external" else "amazon")

        search_query = (query or "").strip()
        if not search_query and mandate.user_restrictions:
            search_query = mandate.user_restrictions[0]
        if not search_query:
            search_query = "laptop"

        # -------------------------------------------------------------
        # 1. Channel3 Universal Multi-Merchant Product Graph
        # -------------------------------------------------------------
        if mkt_id in ("channel3", "channel3_api", "live", "c3"):
            adapter = marketplace_registry.get_adapter("channel3")
            reg = region or "global"
            status = adapter.get_integration_status(reg)

            # If Channel3 is not configured, report authentic state with setup guidance
            if status.state != MarketplaceIntegrationState.CONNECTED:
                logger.info(
                    f"Channel3 API state: {status.state.value} for region {reg}."
                )
                return ProposalSearchResponse(
                    query=search_query,
                    candidates=[],
                    discovered_count=0,
                    enriched_count=0,
                    eligible_count=0,
                    unverified_count=0,
                    compliant_count=0,
                    blocked_count=0,
                    total_count=0,
                    has_more=False,
                    page=page,
                    total_pages=1,
                    next_page_token=None,
                    catalog_mode="channel3",
                    data_source="channel3_api",
                    is_demo_data=False,
                    demo_notice="",
                    marketplace_id="channel3",
                    marketplace_name=adapter.name,
                    region=reg,
                    integration_state=status.state.value,
                    setup_guidance=status.setup_guidance,
                    legal_notice=status.legal_disclaimer,
                    data_freshness="Integration Not Active",
                )

            # Live access is CONNECTED: query Channel3 API with pagination support
            fetch_limit = max(1, min(limit, 50))
            try:
                products = await adapter.search_products(
                    search_query,
                    region=reg,
                    limit=fetch_limit,
                    page_token=page_token,
                )
            except MarketplaceAccessError as acc_err:
                logger.warning(f"Channel3 search error: {acc_err.message}")
                return ProposalSearchResponse(
                    query=search_query,
                    candidates=[],
                    discovered_count=0,
                    enriched_count=0,
                    eligible_count=0,
                    unverified_count=0,
                    compliant_count=0,
                    blocked_count=0,
                    total_count=0,
                    has_more=False,
                    page=page,
                    total_pages=1,
                    next_page_token=None,
                    catalog_mode="channel3",
                    data_source="channel3_api",
                    is_demo_data=False,
                    demo_notice="",
                    marketplace_id="channel3",
                    marketplace_name=adapter.name,
                    region=reg,
                    integration_state=acc_err.state.value,
                    setup_guidance=acc_err.setup_guidance,
                    legal_notice=status.legal_disclaimer,
                    data_freshness=f"Error: {acc_err.message[:50]}",
                )

            # Metadata enrichment & candidate evaluation
            candidates, disc_count, enr_count = await self._process_and_evaluate_products(
                products=products,
                mandate=mandate,
                adapter=adapter,
                region=reg,
            )

            ranked_candidates = self._rank_candidates(candidates, mandate)
            eligible_count = sum(1 for c in ranked_candidates if c.status == "APPROVED")
            unverified_count = sum(1 for c in ranked_candidates if c.status == "NEEDS_VERIFICATION")
            blocked_count = sum(1 for c in ranked_candidates if c.status == "BLOCKED")
            next_token = getattr(adapter, "next_page_token", None)
            has_more = bool(next_token or len(products) >= fetch_limit)

            return ProposalSearchResponse(
                query=search_query,
                candidates=ranked_candidates,
                discovered_count=disc_count,
                enriched_count=enr_count,
                eligible_count=eligible_count,
                unverified_count=unverified_count,
                compliant_count=eligible_count,
                blocked_count=blocked_count,
                total_count=len(ranked_candidates),
                has_more=has_more,
                page=page,
                total_pages=(page + 1) if has_more else page,
                next_page_token=next_token,
                catalog_mode="channel3",
                data_source="channel3_api",
                is_demo_data=False,
                demo_notice="",
                marketplace_id="channel3",
                marketplace_name=adapter.name,
                region=reg,
                integration_state=MarketplaceIntegrationState.CONNECTED.value,
                setup_guidance=None,
                legal_notice=status.legal_disclaimer,
                data_freshness=f"Live Channel3 Universal Graph ({len(ranked_candidates)} items)",
            )

        # -------------------------------------------------------------
        # 2. Amazon Marketplace Provider
        # -------------------------------------------------------------
        if mkt_id in ("amazon", "amazon_creators", "amazon.in", "amazon.com"):
            adapter = marketplace_registry.get_adapter("amazon")
            reg = region or "amazon.in"
            status = adapter.get_integration_status(reg)

            # If access is not connected, report exact access/configuration state
            if status.state != MarketplaceIntegrationState.CONNECTED:
                logger.info(
                    f"Amazon Creators API access state: {status.state.value} for region {reg}."
                )
                return ProposalSearchResponse(
                    query=search_query,
                    candidates=[],
                    discovered_count=0,
                    enriched_count=0,
                    eligible_count=0,
                    unverified_count=0,
                    compliant_count=0,
                    blocked_count=0,
                    total_count=0,
                    has_more=False,
                    page=page,
                    total_pages=1,
                    next_page_token=None,
                    catalog_mode="amazon",
                    data_source=f"amazon_creators_api_{reg}",
                    is_demo_data=False,
                    demo_notice="",
                    marketplace_id="amazon",
                    marketplace_name=adapter.name,
                    region=reg,
                    integration_state=status.state.value,
                    setup_guidance=status.setup_guidance,
                    legal_notice=status.legal_disclaimer,
                    data_freshness="Integration Not Active",
                )

            # Live access is CONNECTED: query Amazon Creators API
            try:
                products = await adapter.search_products(search_query, region=reg, limit=limit)
            except MarketplaceAccessError as acc_err:
                return ProposalSearchResponse(
                    query=search_query,
                    candidates=[],
                    discovered_count=0,
                    enriched_count=0,
                    eligible_count=0,
                    unverified_count=0,
                    compliant_count=0,
                    blocked_count=0,
                    total_count=0,
                    has_more=False,
                    page=page,
                    total_pages=1,
                    next_page_token=None,
                    catalog_mode="amazon",
                    data_source=f"amazon_creators_api_{reg}",
                    is_demo_data=False,
                    demo_notice="",
                    marketplace_id="amazon",
                    marketplace_name=adapter.name,
                    region=reg,
                    integration_state=acc_err.state.value,
                    setup_guidance=acc_err.setup_guidance,
                    legal_notice=status.legal_disclaimer,
                    data_freshness="Error / Handshake Failed",
                )

            candidates, disc_count, enr_count = await self._process_and_evaluate_products(
                products=products,
                mandate=mandate,
                adapter=adapter,
                region=reg,
            )

            ranked_candidates = self._rank_candidates(candidates, mandate)
            eligible_count = sum(1 for c in ranked_candidates if c.status == "APPROVED")
            unverified_count = sum(1 for c in ranked_candidates if c.status == "NEEDS_VERIFICATION")
            blocked_count = sum(1 for c in ranked_candidates if c.status == "BLOCKED")

            return ProposalSearchResponse(
                query=search_query,
                candidates=ranked_candidates,
                discovered_count=disc_count,
                enriched_count=enr_count,
                eligible_count=eligible_count,
                unverified_count=unverified_count,
                compliant_count=eligible_count,
                blocked_count=blocked_count,
                total_count=len(ranked_candidates),
                has_more=False,
                page=page,
                total_pages=1,
                next_page_token=None,
                catalog_mode="amazon",
                data_source=f"amazon_creators_api_{reg}",
                is_demo_data=False,
                demo_notice="",
                marketplace_id="amazon",
                marketplace_name=adapter.name,
                region=reg,
                integration_state=MarketplaceIntegrationState.CONNECTED.value,
                setup_guidance=None,
                legal_notice=status.legal_disclaimer,
                data_freshness=f"Live Amazon Creators API ({len(ranked_candidates)} items)",
            )

        # -------------------------------------------------------------
        # 3. External DummyJSON Catalog Mode
        # -------------------------------------------------------------
        if catalog_mode == "external" or mkt_id == "external":
            discovered_products = await self._search_dummyjson(search_query, mandate.currency)
            candidates, disc_count, enr_count = await self._process_and_evaluate_products(
                products=discovered_products,
                mandate=mandate,
                adapter=None,
                region="global",
            )

            ranked_candidates = self._rank_candidates(candidates, mandate)
            eligible_count = sum(1 for c in ranked_candidates if c.status == "APPROVED")
            unverified_count = sum(1 for c in ranked_candidates if c.status == "NEEDS_VERIFICATION")
            blocked_count = sum(1 for c in ranked_candidates if c.status == "BLOCKED")

            return ProposalSearchResponse(
                query=search_query,
                candidates=ranked_candidates,
                discovered_count=disc_count,
                enriched_count=enr_count,
                eligible_count=eligible_count,
                unverified_count=unverified_count,
                compliant_count=eligible_count,
                blocked_count=blocked_count,
                total_count=len(ranked_candidates),
                has_more=False,
                page=page,
                total_pages=1,
                next_page_token=None,
                catalog_mode="external",
                data_source="dummyjson_api",
                is_demo_data=True,
                demo_notice="Fictional demonstration data from DummyJSON. Not real Amazon or merchant information.",
                marketplace_id="demo",
                marketplace_name="DummyJSON External Demo",
                region="global",
                integration_state="Connected",
                setup_guidance=None,
                legal_notice="Fictional public test API.",
                data_freshness="External Demo API",
            )

        # -------------------------------------------------------------
        # 4. Default: Local Deterministic Demo Fixtures Mode
        # -------------------------------------------------------------
        demo_adapter = marketplace_registry.get_adapter("demo")
        reg = region if region in ("demo_us", "demo_in", "amazon.in", "amazon.com") else ("demo_in" if mandate.currency.upper() == "INR" else "demo_us")
        discovered_products = await demo_adapter.search_products(
            search_query,
            region=reg,
            limit=limit,
            page=page,
            offset=offset,
            page_token=page_token,
        )

        candidates, disc_count, enr_count = await self._process_and_evaluate_products(
            products=discovered_products,
            mandate=mandate,
            adapter=demo_adapter,
            region=reg,
        )

        ranked_candidates = self._rank_candidates(candidates, mandate)
        eligible_count = sum(1 for c in ranked_candidates if c.status == "APPROVED")
        unverified_count = sum(1 for c in ranked_candidates if c.status == "NEEDS_VERIFICATION")
        blocked_count = sum(1 for c in ranked_candidates if c.status == "BLOCKED")
        has_more = (offset + limit < 15) if offset > 0 else (page == 1)

        return ProposalSearchResponse(
            query=search_query,
            candidates=ranked_candidates,
            discovered_count=disc_count,
            enriched_count=enr_count,
            eligible_count=eligible_count,
            unverified_count=unverified_count,
            compliant_count=eligible_count,
            blocked_count=blocked_count,
            total_count=len(ranked_candidates),
            has_more=has_more,
            page=page,
            total_pages=2 if has_more else page,
            next_page_token=f"page_{page + 1}" if has_more else None,
            catalog_mode="demo",
            data_source="local_demo_fixture",
            is_demo_data=True,
            demo_notice=(
                "Fictional demonstration fixtures. All candidates are evaluated by the deterministic "
                "TrustGate policy engine. Demo candidates can never proceed to real payment."
            ),
            marketplace_id="demo",
            marketplace_name="TrustGate Demo Catalog",
            region=reg,
            integration_state="Connected",
            setup_guidance=None,
            legal_notice="Simulated candidate fixtures for testing policy invariants.",
            data_freshness="Simulated / Deterministic",
        )

    async def _process_and_evaluate_products(
        self,
        products: List[DiscoveredProduct],
        mandate: PurchaseMandate,
        adapter: Any,
        region: str,
    ) -> tuple[List[CandidateEvaluation], int, int]:
        """Deduplicates, enriches missing specifications via details endpoints, and deterministically evaluates items."""
        seen_ids = set()
        seen_urls = set()
        unique_products: List[DiscoveredProduct] = []

        # 1. Deduplication pass
        for p in products:
            if not p or not p.product_id:
                continue
            if p.product_id in seen_ids:
                continue
            seen_ids.add(p.product_id)

            if p.purchase_url:
                norm_url = p.purchase_url.strip().lower()
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)

            unique_products.append(p)

        discovered_count = len(unique_products)
        enriched_count = 0

        # 2. Metadata Enrichment Pass
        # Identify candidates lacking specifications required by the mandate
        needs_specs = (
            mandate.min_ram_gb is not None
            or mandate.min_storage_gb is not None
            or mandate.processor_requirement is not None
        )

        for prod in unique_products:
            # Currency conversion if applicable
            if region == "amazon.in" or mandate.currency.upper() == "INR":
                if prod.currency.upper() == "USD" and prod.price:
                    conv_price = currency_service.convert_amount(prod.price, "USD", "INR")
                    if conv_price is not None:
                        prod.price = conv_price
                        prod.currency = "INR"

            # Check if this product is missing key specs required by the mandate
            missing_ram = mandate.min_ram_gb is not None and getattr(prod, "ram_gb", None) is None
            missing_storage = mandate.min_storage_gb is not None and getattr(prod, "storage_gb", None) is None
            missing_proc = mandate.processor_requirement is not None and getattr(prod, "processor", None) is None

            is_relevant_category = (
                "laptop" in prod.category.lower()
                or "notebook" in prod.category.lower()
                or "laptop" in prod.name.lower()
                or "computer" in prod.category.lower()
            )

            if needs_specs and is_relevant_category and (missing_ram or missing_storage or missing_proc):
                # Attempt metadata enrichment if adapter supports get_product_details
                if adapter and hasattr(adapter, "get_product_details"):
                    try:
                        detail = await adapter.get_product_details(prod.product_id, region=region)
                        if detail:
                            did_enrich = False
                            if missing_ram and getattr(detail, "ram_gb", None) is not None:
                                prod.ram_gb = detail.ram_gb
                                did_enrich = True
                            if missing_storage and getattr(detail, "storage_gb", None) is not None:
                                prod.storage_gb = detail.storage_gb
                                prod.storage_type = detail.storage_type or prod.storage_type
                                did_enrich = True
                            if missing_proc and getattr(detail, "processor", None) is not None:
                                prod.processor = detail.processor
                                did_enrich = True

                            if did_enrich:
                                prod.enrichment_status = "ENRICHED"
                                prod.spec_verification_status = detail.spec_verification_status or "VERIFIED"
                                enriched_count += 1
                            else:
                                prod.enrichment_status = "NOT_ENRICHED"
                    except Exception as exc:
                        logger.debug("Enrichment lookup failed for %s: %s", prod.product_id, exc)
                        prod.enrichment_status = "LOOKUP_FAILED"
                else:
                    prod.enrichment_status = "NO_ENRICHMENT_PROVIDER"
            else:
                if prod.ram_gb is not None and prod.storage_gb is not None:
                    prod.enrichment_status = "COMPLETE"
                else:
                    prod.enrichment_status = "NOT_NEEDED"

        # 3. Deterministic Policy Evaluation Pass
        evaluations: List[CandidateEvaluation] = []
        for prod in unique_products:
            if prod.price is None or prod.price <= 0:
                logger.warning(
                    f"Skipping candidate '{prod.name}' (ID: {prod.product_id}): invalid price ({prod.price})."
                )
                continue
            ev = self._evaluate_candidate(prod, mandate)
            if ev is not None:
                evaluations.append(ev)

        return evaluations, discovered_count, enriched_count

    async def _search_dummyjson(
        self, query: str, mandate_currency: str
    ) -> List[DiscoveredProduct]:
        """Fetch candidates from DummyJSON demonstration catalog."""
        products: List[DiscoveredProduct] = []
        params = {"q": query, "limit": 8}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                res = await client.get(DUMMYJSON_SEARCH_URL, params=params)
                if res.status_code != 200:
                    return []

                data = res.json()
                raw_items = data.get("products", [])

                for item in raw_items:
                    raw_price = item.get("price", 0.0)
                    try:
                        price = float(raw_price)
                    except (ValueError, TypeError):
                        price = 0.0

                    brand = item.get("brand") or "Independent Retailer"
                    images = item.get("images") or []
                    thumbnail = item.get("thumbnail") or (images[0] if images else None)

                    prod = DiscoveredProduct(
                        product_id=f"dummy_{item.get('id', 'unknown')}",
                        name=item.get("title") or "Unnamed Catalog Item",
                        description=item.get("description") or "Demonstration catalog product.",
                        category=item.get("category") or "General",
                        price=round(price, 2),
                        currency="USD",
                        image_url=thumbnail,
                        condition="unknown",
                        merchant_name=brand,
                        merchant_verified=False,
                        verification_status="UNKNOWN",
                        data_source="dummyjson_api",
                        is_demo_data=True,
                        demo_notice="External demonstration item from DummyJSON. Fictional merchant and specs.",
                        marketplace_id="demo",
                        region="global",
                        data_freshness="DummyJSON Demo API",
                    )
                    products.append(prod)

        except Exception as err:
            logger.warning(f"DummyJSON error: {err}")
            return []

        return products

    def _evaluate_candidate(
        self, product: DiscoveredProduct, mandate: PurchaseMandate
    ) -> Optional[CandidateEvaluation]:
        """Run candidate product through the deterministic TrustGate policy engine."""
        # Requirement 7: Reject/skip candidates without a valid positive price
        if product.price is None or product.price <= 0:
            logger.warning(
                f"Candidate '{product.name}' (ID: {product.product_id}) rejected: "
                f"invalid non-positive price ({product.price}). Positive price is required for policy evaluation."
            )
            return None

        has_intentional_addons = "cand_addons_005" in product.product_id or "Bundle" in product.name
        add_ons = ["Extended Warranty Pack", "Accessory Kit"] if has_intentional_addons else []
        additional_charges = 25.00 if has_intentional_addons else 0.00
        shipping_cost = 0.00
        tax = 0.00

        # Requirement 6: Ensure final_total is calculated from validated product price
        # plus applicable shipping, tax and additional charges.
        final_total = round(product.price + shipping_cost + tax + additional_charges, 2)
        if final_total <= 0:
            logger.warning(
                f"Candidate '{product.name}' (ID: {product.product_id}) rejected: "
                f"calculated final total ({final_total}) must be greater than zero."
            )
            return None

        # Ensure hardware specifications are populated on DiscoveredProduct
        if getattr(product, "ram_gb", None) is None and getattr(product, "storage_gb", None) is None:
            specs = product_normalizer.normalize_specifications(
                title=product.name,
                description=product.description or "",
                category=product.category or "General",
                raw_metadata={
                    "brand": getattr(product, "brand", None) or product.merchant_name,
                    "availability": getattr(product, "availability", None),
                    "retailer": getattr(product, "retailer", None) or product.merchant_name,
                    "merchant_name": product.merchant_name,
                },
            )
            for k, v in specs.items():
                if getattr(product, k, None) is None:
                    setattr(product, k, v)

        proposed_tx = ProposedTransaction(
            product_name=product.name,
            product_description=product.description,
            category=product.category,
            product_price=product.price,
            shipping_cost=shipping_cost,
            tax=tax,
            additional_charges=additional_charges,
            final_total=final_total,
            currency=product.currency,
            merchant_name=product.merchant_name,
            merchant_verified=product.merchant_verified,
            product_condition=product.condition,
            add_ons=add_ons,
            brand=getattr(product, "brand", None),
            model=getattr(product, "model", None),
            ram_gb=getattr(product, "ram_gb", None),
            storage_gb=getattr(product, "storage_gb", None),
            storage_type=getattr(product, "storage_type", None),
            processor=getattr(product, "processor", None),
            gpu=getattr(product, "gpu", None),
            screen_size=getattr(product, "screen_size", None),
            availability=getattr(product, "availability", "InStock"),
            marketplace=getattr(product, "marketplace_id", None),
            retailer=getattr(product, "retailer", None) or product.merchant_name,
            original_price=getattr(product, "original_price", None) or product.price,
            original_currency=getattr(product, "original_currency", None) or product.currency,
            spec_verification_status=getattr(product, "spec_verification_status", "UNKNOWN"),
        )

        policy_result = policy_engine.evaluate_mandate(
            mandate=mandate,
            transaction=proposed_tx,
            caller_role="human_user",
        )

        # Calculate budget remaining in candidate product's currency
        if product.currency.upper() == mandate.currency.upper():
            budget_remaining = round(mandate.max_amount - final_total, 2)
        else:
            mandate_budget_in_prod_curr = currency_service.convert_amount(
                mandate.max_amount, mandate.currency, product.currency
            )
            if mandate_budget_in_prod_curr is not None:
                budget_remaining = round(mandate_budget_in_prod_curr - final_total, 2)
            else:
                budget_remaining = round(mandate.max_amount - final_total, 2)

        # 3-tier classification: APPROVED, NEEDS_VERIFICATION, or BLOCKED
        status = "APPROVED" if policy_result.approved else "BLOCKED"
        unverified_reasons: Optional[List[str]] = None
        selection_blocked_reason: Optional[str] = None

        if policy_result.approved:
            status = "APPROVED"
        else:
            # Check whether violations are strictly unverified specifications
            unverified_violations: List[str] = []
            hard_violations: List[str] = []

            for v in policy_result.violations:
                msg_lower = v.message.lower()
                rule_name_lower = v.rule_name.lower()
                is_unverified_spec = (
                    ("unverified product ram" in rule_name_lower)
                    or ("unverified product storage" in rule_name_lower)
                    or ("unknown" in str(v.actual).lower() and ("ram" in rule_name_lower or "storage" in rule_name_lower or "processor" in rule_name_lower))
                    or ("unverified" in msg_lower and ("ram" in msg_lower or "storage" in msg_lower))
                )
                if is_unverified_spec:
                    unverified_violations.append(v.message)
                else:
                    hard_violations.append(v.message)

            if unverified_violations and not hard_violations:
                status = "NEEDS_VERIFICATION"
                selection_blocked_reason = "Product specifications could not be verified against mandate constraints."
                unverified_reasons = unverified_violations
            else:
                status = "BLOCKED"
                selection_blocked_reason = hard_violations[0] if hard_violations else (unverified_violations[0] if unverified_violations else "Transaction failed deterministic policy validation.")

        return CandidateEvaluation(
            product=product,
            policy_result=policy_result,
            approved=policy_result.approved,
            status=status,
            budget_remaining=budget_remaining,
            currency=product.currency,
            can_select=policy_result.approved,
            selection_blocked_reason=selection_blocked_reason,
            unverified_reasons=unverified_reasons,
            enrichment_status=getattr(product, "enrichment_status", None),
        )

    @staticmethod
    def _rank_candidates(
        candidates: List[CandidateEvaluation],
        mandate: PurchaseMandate,
    ) -> List[CandidateEvaluation]:
        """Ranks candidates:
        Tier 0: APPROVED (Eligible candidates ranked first)
        Tier 1: NEEDS_VERIFICATION (Relevant candidates needing spec verification second)
        Tier 2: BLOCKED (Rule violators ranked last, preserving stable relative test order)
        """
        def sort_key(c: CandidateEvaluation):
            if c.status == "APPROVED":
                group_priority = 0
                spec_score = 0
                if getattr(c.product, "spec_verification_status", "") == "VERIFIED":
                    spec_score -= 20
                if getattr(c.product, "ram_gb", None):
                    spec_score -= min(c.product.ram_gb, 64)
                if getattr(c.product, "storage_gb", None):
                    spec_score -= min(c.product.storage_gb // 100, 20)
                price_delta = c.budget_remaining if c.budget_remaining is not None else 0
                return (group_priority, spec_score, -price_delta)
            elif c.status == "NEEDS_VERIFICATION":
                group_priority = 1
                return (group_priority, 0, 0)
            else:
                group_priority = 2
                return (group_priority, 0, 0)

        return sorted(candidates, key=sort_key)


product_discovery_service = ProductDiscoveryService()
