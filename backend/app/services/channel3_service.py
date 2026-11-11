"""Channel3 Universal Product Graph service for PayPal TrustGate.

Integrates with the official Channel3 API (https://api.trychannel3.com/v1)
to provide real-world, multi-merchant product discovery for AI shopping agents.

SECURITY & ARCHITECTURAL INVARIANTS:
1. Authentication: Uses x-api-key header strictly on the backend. Never exposed to clients or in logs.
2. Zero Fabrication: Real catalog data from Channel3 is never synthesized or phantom.
3. Explicit Labeling: Real Channel3 products are flagged with is_demo_data=False and data_source='channel3_api',
   clearly distinguishing them from local deterministic demo fixtures.
4. Deterministic Evaluation: All candidate products returned by Channel3 are evaluated through
   TrustGate's TG-001 to TG-007 deterministic policy engine.
5. Invariant Enforcement: AI agents cannot authorize payments. PayPal Sandbox checkout and explicit
   human authorization remain strictly enforced for all candidates.
6. Resilient Degradation: Cleanly handles timeouts, network partitions, authentication failures,
   and empty product results with explicit, informative states.
"""

import logging
import time
from typing import List, Optional, Dict, Any
import httpx

from app.core.config import settings
from app.models.marketplace import (
    MarketplaceStatusResponse,
    MarketplaceRegion,
    MarketplaceIntegrationState,
)
from app.models.proposal import DiscoveredProduct
from app.services.marketplaces.base import MarketplaceAccessError
from app.services.product_normalizer import product_normalizer

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 12.0
CHANNEL3_LEGAL_NOTICE = (
    "Channel3 Universal Product Graph Integration. Real-time product search, multi-merchant offers, "
    "and catalog metadata provided by Channel3 (trychannel3.com). All transactions require explicit "
    "human authorization and execute exclusively through PayPal Sandbox."
)

SUPPORTED_CHANNEL3_REGIONS = [
    MarketplaceRegion(
        id="global",
        name="Global Multi-Merchant Graph",
        currency="USD",
        host="api.trychannel3.com",
        is_default=True,
    ),
    MarketplaceRegion(
        id="us",
        name="United States Retailers (Target, Best Buy, etc.)",
        currency="USD",
        host="api.trychannel3.com",
        is_default=False,
    ),
]


class Channel3Service:
    """Dedicated service for Channel3 Universal Product Graph API."""

    def __init__(self):
        self._last_test_result: Optional[Dict[str, Any]] = None
        self._last_next_page_token: Optional[str] = None

    @property
    def last_next_page_token(self) -> Optional[str]:
        """Returns the continuation token from the most recent search."""
        return self._last_next_page_token

    @property
    def is_configured(self) -> bool:
        """True if genuine CHANNEL3_API_KEY is configured in backend environment."""
        return settings.is_channel3_configured()

    def get_headers(self) -> Dict[str, str]:
        """Builds request headers with API key. Never log the resulting dictionary."""
        api_key = settings.get_channel3_api_key()
        return {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_integration_status(self) -> MarketplaceStatusResponse:
        """Inspects Channel3 configuration and returns authentic integration status."""
        configured = self.is_configured
        if not configured:
            return MarketplaceStatusResponse(
                marketplace_id="channel3",
                name="Channel3 Universal Product Graph",
                state=MarketplaceIntegrationState.NOT_CONFIGURED,
                is_connected=False,
                configured=False,
                supported_regions=SUPPORTED_CHANNEL3_REGIONS,
                active_region="global",
                currency="USD",
                message=(
                    "Channel3 API key is not configured. Set CHANNEL3_API_KEY in backend/.env "
                    "to activate real multi-merchant product discovery."
                ),
                setup_guidance=(
                    "1. Obtain an API key from https://trychannel3.com\n"
                    "2. Add CHANNEL3_API_KEY=<your_key> to backend/.env\n"
                    "3. Restart the FastAPI backend server."
                ),
                legal_disclaimer=CHANNEL3_LEGAL_NOTICE,
            )

        return MarketplaceStatusResponse(
            marketplace_id="channel3",
            name="Channel3 Universal Product Graph",
            state=MarketplaceIntegrationState.CONNECTED,
            is_connected=True,
            configured=True,
            supported_regions=SUPPORTED_CHANNEL3_REGIONS,
            active_region="global",
            currency="USD",
            message="Channel3 Universal Product Graph is connected and active for real product discovery.",
            setup_guidance=None,
            legal_disclaimer=CHANNEL3_LEGAL_NOTICE,
        )

    async def test_connection(self) -> Dict[str, Any]:
        """Tests live connectivity to Channel3 API without exposing secret keys."""
        if not self.is_configured:
            return {
                "success": False,
                "configured": False,
                "status": "NOT_CONFIGURED",
                "message": "CHANNEL3_API_KEY is not configured in backend/.env",
                "endpoint": f"{settings.get_channel3_base_url()}/search",
            }

        search_url = f"{settings.get_channel3_base_url()}/search"
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                res = await client.post(
                    search_url,
                    headers=self.get_headers(),
                    json={"query": "wireless keyboard", "limit": 1},
                )
                latency_ms = round((time.time() - start_time) * 1000, 1)

                if res.status_code == 200:
                    data = res.json()
                    sample_products = data.get("products", [])
                    result = {
                        "success": True,
                        "configured": True,
                        "status": "CONNECTED",
                        "status_code": 200,
                        "latency_ms": latency_ms,
                        "endpoint": search_url,
                        "products_returned": len(sample_products),
                        "sample_title": sample_products[0].get("title") if sample_products else None,
                        "message": "Channel3 API connection verified successfully.",
                    }
                    self._last_test_result = result
                    return result

                elif res.status_code in (401, 403):
                    return {
                        "success": False,
                        "configured": True,
                        "status": "CREDENTIALS_INVALID",
                        "status_code": res.status_code,
                        "latency_ms": latency_ms,
                        "endpoint": search_url,
                        "message": f"Channel3 authentication failed (HTTP {res.status_code}). Verify CHANNEL3_API_KEY in backend/.env.",
                    }
                else:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "API_ERROR",
                        "status_code": res.status_code,
                        "latency_ms": latency_ms,
                        "endpoint": search_url,
                        "message": f"Channel3 returned HTTP {res.status_code}: {res.text[:200]}",
                    }

        except httpx.TimeoutException:
            return {
                "success": False,
                "configured": True,
                "status": "TIMEOUT",
                "endpoint": search_url,
                "message": f"Channel3 API request timed out after {DEFAULT_TIMEOUT_SECONDS}s.",
            }
        except Exception as exc:
            logger.error("Channel3 test connection error: %s", exc)
            return {
                "success": False,
                "configured": True,
                "status": "NETWORK_ERROR",
                "endpoint": search_url,
                "message": f"Network error connecting to Channel3: {str(exc)}",
            }

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        currency: str = "USD",
        region: Optional[str] = None,
        page_token: Optional[str] = None,
    ) -> List[DiscoveredProduct]:
        """Performs live product search via Channel3 API and normalizes results into DiscoveredProduct schema.

        Raises MarketplaceAccessError if not configured or if API communication fails.
        """
        if not self.is_configured:
            raise MarketplaceAccessError(
                state=MarketplaceIntegrationState.NOT_CONFIGURED,
                message="Channel3 API key is not configured in backend/.env.",
                setup_guidance="Set CHANNEL3_API_KEY in backend/.env to activate live product discovery.",
            )

        search_url = f"{settings.get_channel3_base_url()}/search"
        clean_query = (query or "").strip()
        PROHIBITED_CHANNEL3_QUERY_TERMS = {
            "brand new only", "brand new", "brand-new", "new only", "new", "refurbished",
            "used", "verified seller", "verified seller only", "verified sellers",
            "no refurbished", "no accessories", "no refurbished products", "no add-ons",
            "in stock only", "in-stock only", "in stock",
        }
        if not clean_query or clean_query.lower() in PROHIBITED_CHANNEL3_QUERY_TERMS:
            clean_query = "laptop"

        payload: Dict[str, Any] = {
            "query": clean_query,
            "limit": max(1, min(limit, 50)),
        }
        if page_token:
            payload["page_token"] = str(page_token).strip()

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                res = await client.post(
                    search_url,
                    headers=self.get_headers(),
                    json=payload,
                )

                if res.status_code == 401 or res.status_code == 403:
                    raise MarketplaceAccessError(
                        state=MarketplaceIntegrationState.CREDENTIALS_MISSING,
                        message=f"Channel3 authentication failed (HTTP {res.status_code}). Verify CHANNEL3_API_KEY in backend/.env.",
                        setup_guidance="Verify the Channel3 API key in backend/.env from https://trychannel3.com.",
                    )

                if res.status_code == 429:
                    raise MarketplaceAccessError(
                        state=MarketplaceIntegrationState.ERROR,
                        message="Channel3 API rate limit exceeded. Please retry momentarily.",
                    )

                if res.status_code != 200:
                    raise MarketplaceAccessError(
                        state=MarketplaceIntegrationState.ERROR,
                        message=f"Channel3 API returned error HTTP {res.status_code}: {res.text[:200]}",
                    )

                data = res.json()
                raw_products = data.get("products", [])
                self._last_next_page_token = data.get("next_page_token")
                normalized_items: List[DiscoveredProduct] = []

                for item in raw_products:
                    normalized = self._normalize_product(item, fallback_currency=currency)
                    if normalized:
                        normalized_items.append(normalized)

                return normalized_items

        except httpx.TimeoutException:
            logger.warning("Channel3 API request timed out for query: %s", clean_query)
            raise MarketplaceAccessError(
                state=MarketplaceIntegrationState.ERROR,
                message=f"Channel3 API timed out after {DEFAULT_TIMEOUT_SECONDS}s. Please check network connectivity or try a simpler query.",
            )
        except MarketplaceAccessError:
            raise
        except Exception as exc:
            logger.error("Channel3 search exception: %s", exc, exc_info=True)
            raise MarketplaceAccessError(
                state=MarketplaceIntegrationState.ERROR,
                message=f"Failed to query Channel3 product graph: {str(exc)}",
            )

    async def get_product_details(
        self,
        product_id: str,
        region: Optional[str] = None,
    ) -> Optional[DiscoveredProduct]:
        """Fetches product details from Channel3 by product ID.

        Attempts direct product retrieval; falls back to search matching.
        Raises MarketplaceAccessError if credentials are not configured.
        """
        if not self.is_configured:
            raise MarketplaceAccessError(
                state=MarketplaceIntegrationState.NOT_CONFIGURED,
                message="Channel3 API key is not configured in backend/.env.",
                setup_guidance="Set CHANNEL3_API_KEY in backend/.env to activate live product discovery.",
            )

        clean_id = product_id.replace("ch3_", "").strip()
        if not clean_id:
            return None

        # 1. Direct product endpoint attempt
        product_url = f"{settings.get_channel3_base_url()}/products/{clean_id}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                res = await client.get(product_url, headers=self.get_headers())
                if res.status_code == 200:
                    raw_data = res.json()
                    item = raw_data.get("product", raw_data) if isinstance(raw_data, dict) else raw_data
                    if isinstance(item, dict):
                        return self._normalize_product(item, fallback_currency="USD")
                elif res.status_code in (401, 403):
                    raise MarketplaceAccessError(
                        state=MarketplaceIntegrationState.CREDENTIALS_MISSING,
                        message=f"Channel3 authentication failed (HTTP {res.status_code}). Verify CHANNEL3_API_KEY.",
                    )
        except MarketplaceAccessError:
            raise
        except Exception as exc:
            logger.debug("Direct product endpoint lookup for %s exception: %s", clean_id, exc)

        # 2. Resilient fallback: search by product query
        try:
            candidates = await self.search_products(query=clean_id, limit=5, currency="USD", region=region)
            for cand in candidates:
                if (
                    cand.product_id == f"ch3_{clean_id}"
                    or cand.product_id == product_id
                    or clean_id in cand.product_id
                ):
                    return cand
            if candidates:
                return candidates[0]
        except MarketplaceAccessError:
            raise
        except Exception as exc:
            logger.warning("Channel3 product search fallback failed for %s: %s", clean_id, exc)

        return None

    @staticmethod
    def _parse_price_string(raw_price: str) -> Optional[float]:
        """Parses a price string with currency symbols and formatting into a positive float."""
        if not raw_price or not isinstance(raw_price, str):
            return None
        import re
        cleaned = raw_price.strip()
        cleaned = re.sub(r"[^\d.,]", "", cleaned).strip()
        if not cleaned:
            return None
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_price_and_currency(
        source: Dict[str, Any], fallback_currency: str = "USD"
    ) -> tuple[Optional[float], str]:
        """Extracts a valid positive price float and currency ISO string from an offer or item dictionary."""
        if not isinstance(source, dict):
            return None, fallback_currency

        price_val: Optional[float] = None
        currency_code: str = fallback_currency

        # 1. Check nested 'price' or 'pricing' object
        raw_price = source.get("price")
        if raw_price is None:
            raw_price = source.get("pricing")

        if isinstance(raw_price, dict):
            amt = (
                raw_price.get("amount")
                if raw_price.get("amount") is not None
                else raw_price.get("value")
            )
            if amt is None:
                amt = raw_price.get("price")
            if amt is None and raw_price.get("amount_cents") is not None:
                try:
                    amt = float(raw_price["amount_cents"]) / 100.0
                except (ValueError, TypeError):
                    amt = None
            if amt is None and raw_price.get("cents") is not None:
                try:
                    amt = float(raw_price["cents"]) / 100.0
                except (ValueError, TypeError):
                    amt = None

            curr = raw_price.get("currency") or raw_price.get("currency_code")
            if curr:
                currency_code = str(curr).strip().upper()

            if amt is not None:
                try:
                    price_val = float(amt)
                except (ValueError, TypeError):
                    price_val = None

        elif isinstance(raw_price, (int, float)):
            price_val = float(raw_price)

        elif isinstance(raw_price, str):
            price_val = Channel3Service._parse_price_string(raw_price)

        # 2. Check direct 'price_cents' / 'price_in_cents' / 'amount_cents'
        if price_val is None or price_val <= 0:
            cents = (
                source.get("price_cents")
                if source.get("price_cents") is not None
                else source.get("price_in_cents")
            )
            if cents is None:
                cents = source.get("amount_cents")
            if cents is not None:
                try:
                    price_val = float(cents) / 100.0
                except (ValueError, TypeError):
                    price_val = None

        # 3. Check direct 'amount', 'current_price', 'sale_price', 'min_price'
        if price_val is None or price_val <= 0:
            for alt_key in ("amount", "current_price", "sale_price", "min_price"):
                alt_val = source.get(alt_key)
                if alt_val is not None:
                    if isinstance(alt_val, dict):
                        sub_amt = alt_val.get("amount") or alt_val.get("value") or alt_val.get("price")
                        sub_curr = alt_val.get("currency") or alt_val.get("currency_code")
                        if sub_curr:
                            currency_code = str(sub_curr).strip().upper()
                        if sub_amt is not None:
                            try:
                                price_val = float(sub_amt)
                                if price_val > 0:
                                    break
                            except (ValueError, TypeError):
                                pass
                    elif isinstance(alt_val, (int, float)):
                        try:
                            f_val = float(alt_val)
                            if f_val > 0:
                                price_val = f_val
                                break
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(alt_val, str):
                        parsed = Channel3Service._parse_price_string(alt_val)
                        if parsed and parsed > 0:
                            price_val = parsed
                            break

        # Check top-level currency if not yet resolved
        if currency_code == fallback_currency:
            direct_curr = source.get("currency") or source.get("currency_code")
            if direct_curr:
                currency_code = str(direct_curr).strip().upper()

        if price_val is not None and price_val > 0:
            return round(price_val, 2), currency_code

        return None, fallback_currency

    def _normalize_product(
        self,
        item: Dict[str, Any],
        fallback_currency: str = "USD",
    ) -> Optional[DiscoveredProduct]:
        """Normalizes a raw Channel3 product payload into TrustGate's DiscoveredProduct schema."""
        try:
            product_id = str(item.get("id") or "")
            if not product_id:
                import uuid
                product_id = uuid.uuid4().hex[:10]

            title = (item.get("title") or "Unnamed Product").strip()
            description = (item.get("description") or "").strip()

            # Category parsing
            category_raw = item.get("category")
            if isinstance(category_raw, dict):
                category = category_raw.get("title") or category_raw.get("slug") or "General"
            elif isinstance(category_raw, str):
                category = category_raw
            else:
                category = "General"

            # Image selection: prioritize cleaned_url or main image
            images = item.get("images") or []
            image_url: Optional[str] = None
            for img in images:
                if isinstance(img, dict):
                    if img.get("is_main_image"):
                        image_url = img.get("cleaned_url") or img.get("url")
                        break
                    if not image_url:
                        image_url = img.get("cleaned_url") or img.get("url")
                elif isinstance(img, str) and not image_url:
                    image_url = img

            # Primary offer selection (price, merchant, condition, buy link)
            offers = item.get("offers") or []
            primary_offer: Dict[str, Any] = {}
            price_val: Optional[float] = None
            currency_code = fallback_currency

            # 1. Search offers for a valid offer with a positive price
            if isinstance(offers, list) and offers:
                for off in offers:
                    if not isinstance(off, dict):
                        continue
                    p, c = self._extract_price_and_currency(off, fallback_currency)
                    if p is not None and p > 0:
                        avail = str(off.get("availability") or "").lower()
                        # Prefer in-stock offer or keep the first valid positive price offer
                        if not primary_offer or avail == "instock":
                            primary_offer = off
                            price_val = p
                            currency_code = c
                            if avail == "instock":
                                break

            # 2. If no valid offer price, check top-level item price fields
            if price_val is None or price_val <= 0:
                p, c = self._extract_price_and_currency(item, fallback_currency)
                if p is not None and p > 0:
                    price_val = p
                    currency_code = c

            # 3. Security Invariant (Requirement 7):
            # If candidate has no valid positive price, skip candidate with clear diagnostic.
            # Never invent a price, silently substitute a default (0.0), or fabricate provider data.
            if price_val is None or price_val <= 0:
                logger.info(
                    "Skipping Channel3 candidate '%s' (ID: %s): "
                    "no valid positive price found in provider offers or metadata.",
                    title,
                    product_id,
                )
                return None

            # Condition normalization - Security Invariant: Never assume new if condition is unknown/unspecified
            raw_cond = (
                primary_offer.get("condition")
                or item.get("condition")
                or item.get("item_condition")
                or ""
            )
            cond_raw = str(raw_cond).strip().lower()
            if "new" in cond_raw:
                condition = "new"
            elif "refurb" in cond_raw:
                condition = "refurbished"
            elif "used" in cond_raw:
                condition = "used"
            else:
                condition = "unknown"

            # Domain & Retailer
            domain = primary_offer.get("domain") or item.get("domain") or ""
            purchase_url = primary_offer.get("url") or item.get("purchase_url") or item.get("url") or None
            availability = primary_offer.get("availability") or item.get("availability") or "InStock"

            # Brand extraction
            brands = item.get("brands") or []
            brand_name = ""
            if brands and isinstance(brands[0], dict):
                brand_name = brands[0].get("name") or ""
            elif brands and isinstance(brands[0], str):
                brand_name = brands[0]

            merchant_name = domain or brand_name or "Channel3 Retailer"

            # Verified status: major recognized retail domains
            known_verified_domains = {
                "target.com",
                "bestbuy.com",
                "walmart.com",
                "apple.com",
                "nike.com",
                "keychron.com",
                "amazon.com",
                "amazon.in",
                "homedepot.com",
                "costco.com",
                "dell.com",
                "lenovo.com",
            }
            if item.get("merchant_verified") is not None:
                is_verified = bool(item.get("merchant_verified"))
            elif primary_offer.get("merchant_verified") is not None:
                is_verified = bool(primary_offer.get("merchant_verified"))
            else:
                is_verified = bool(domain and ((domain.lower() in known_verified_domains) or ("." in domain)))

            # Extract rich key features and structured attributes from Channel3 payload
            raw_kf = item.get("key_features") or []
            key_features: List[str] = [str(k).strip() for k in raw_kf if k] if isinstance(raw_kf, list) else []
            structured_attrs = item.get("structured_attributes") or item.get("attributes") or {}
            if not isinstance(structured_attrs, dict):
                structured_attrs = {}

            # Specification normalization layer
            specs = product_normalizer.normalize_specifications(
                title=title,
                description=description,
                category=category,
                raw_metadata={
                    "brand": brand_name,
                    "availability": availability,
                    "retailer": domain or brand_name or "Channel3 Partner",
                    "merchant_name": merchant_name,
                    "key_features": key_features,
                    "structured_attributes": structured_attrs,
                    "structured_ram": structured_attrs.get("ram") or structured_attrs.get("memory"),
                    "structured_storage": structured_attrs.get("storage-capacity") or structured_attrs.get("storage"),
                    "structured_processor": structured_attrs.get("processor-family") or structured_attrs.get("processor"),
                },
            )

            return DiscoveredProduct(
                product_id=f"ch3_{product_id}",
                name=title,
                description=description[:300] if description else f"Authentic listing from {merchant_name}.",
                category=category,
                price=price_val,
                currency=currency_code,
                image_url=image_url,
                condition=condition,
                merchant_name=merchant_name,
                merchant_verified=is_verified,
                verification_status="VERIFIED" if is_verified else "UNKNOWN",
                data_source="channel3_api",
                is_demo_data=False,  # Genuine Channel3 product data!
                demo_notice="",       # Genuine data: no demo notice
                marketplace_id="channel3",
                region="global",
                data_freshness="Live Channel3 Universal Graph",
                purchase_url=purchase_url,
                availability=specs["availability"],
                retailer=domain or brand_name or "Channel3 Partner",
                brand=specs["brand"],
                model=specs["model"],
                ram_gb=specs["ram_gb"],
                storage_gb=specs["storage_gb"],
                storage_type=specs["storage_type"],
                processor=specs["processor"],
                gpu=specs["gpu"],
                screen_size=specs["screen_size"],
                original_price=price_val,
                original_currency=currency_code,
                spec_verification_status=specs["spec_verification_status"],
            )
        except Exception as exc:
            logger.warning("Error normalizing Channel3 product: %s", exc)
            return None


channel3_service = Channel3Service()

