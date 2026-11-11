"""Comprehensive tests for product discovery breadth, pagination, metadata enrichment,
3-tier classification, and invariant enforcement in PayPal TrustGate.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.policy import PurchaseMandate
from app.models.proposal import DiscoveredProduct, ProposalSearchRequest
from app.services.product_discovery_service import product_discovery_service
from app.services.marketplaces.demo_adapter import demo_adapter
from app.services.product_normalizer import product_normalizer
from app.services.channel3_service import channel3_service

client = TestClient(app)


@pytest.fixture
def laptop_mandate_strict():
    """Mandate requiring 16GB RAM, 512GB storage, Core i5 or better, within budget."""
    return PurchaseMandate(
        max_amount=150.0,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        min_ram_gb=16,
        min_storage_gb=512,
        processor_requirement="Intel Core i5",
        user_restrictions=["new laptop only"],
    )


class TestDiscoveryBreadthAndPagination:
    """Verifies retrieval breadth, pagination tokens, and deduplication across pages."""

    @pytest.mark.asyncio
    async def test_pagination_page_1_has_more(self, laptop_mandate_strict):
        """Page 1 returns initial candidate slice with has_more=True and next_page_token."""
        res = await product_discovery_service.search_candidates(
            mandate=laptop_mandate_strict,
            query="laptop",
            catalog_mode="demo",
            page=1,
            limit=10,
        )

        assert res.page == 1
        assert res.total_count == 6
        assert res.has_more is True
        assert res.next_page_token == "page_2"
        assert res.discovered_count == 6

    @pytest.mark.asyncio
    async def test_pagination_page_2_returns_next_slice(self, laptop_mandate_strict):
        """Page 2 returns subsequent slice with has_more=False and distinct products."""
        res = await product_discovery_service.search_candidates(
            mandate=laptop_mandate_strict,
            query="laptop",
            catalog_mode="demo",
            page=2,
            limit=10,
            page_token="page_2",
        )

        assert res.page == 2
        assert res.has_more is False
        assert res.next_page_token is None
        assert res.total_count > 0

        # Page 2 includes additional breadth fixtures
        prod_ids = [c.product.product_id for c in res.candidates]
        assert "demo_compliant_007" in prod_ids
        assert "demo_compliant_008" in prod_ids

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicate_items(self, laptop_mandate_strict):
        """Pipeline deduplicates identical product IDs and canonical URLs."""
        dup_products = [
            DiscoveredProduct(
                product_id="ch3_dup_001",
                name="Duplicate Laptop A",
                price=100.0,
                currency="USD",
                condition="new",
                merchant_name="Merchant A",
                merchant_verified=True,
                purchase_url="https://merchant-a.com/laptop-1",
            ),
            DiscoveredProduct(
                product_id="ch3_dup_001",  # Same product_id
                name="Duplicate Laptop A (Repeated)",
                price=100.0,
                currency="USD",
                condition="new",
                merchant_name="Merchant A",
                merchant_verified=True,
                purchase_url="https://merchant-a.com/laptop-1",
            ),
            DiscoveredProduct(
                product_id="ch3_dup_002",  # Different ID but identical canonical purchase_url
                name="Duplicate Laptop B",
                price=100.0,
                currency="USD",
                condition="new",
                merchant_name="Merchant B",
                merchant_verified=True,
                purchase_url="https://merchant-a.com/laptop-1",
            ),
        ]

        evals, disc_count, enr_count = await product_discovery_service._process_and_evaluate_products(
            products=dup_products,
            mandate=laptop_mandate_strict,
            adapter=None,
            region="global",
        )

        assert disc_count == 1
        assert len(evals) == 1
        assert evals[0].product.product_id == "ch3_dup_001"


class TestMetadataEnrichment:
    """Verifies that items with missing specs are enriched via detail endpoints before policy check."""

    @pytest.mark.asyncio
    async def test_enrichment_resolves_missing_specs(self, laptop_mandate_strict):
        """Item demo_unverified_010 is enriched with 16GB RAM and 512GB SSD via get_product_details."""
        raw_items = await demo_adapter.search_products("laptop", region="demo_us", limit=10, page=2)
        # Find demo_unverified_010 in page 2
        cand_010 = next(p for p in raw_items if p.product_id == "demo_unverified_010")

        # Initial listing had missing RAM/storage
        evals, disc_count, enr_count = await product_discovery_service._process_and_evaluate_products(
            products=[cand_010],
            mandate=laptop_mandate_strict,
            adapter=demo_adapter,
            region="demo_us",
        )

        assert disc_count == 1
        assert enr_count == 1
        eval_item = evals[0]
        # Successfully enriched: RAM=16, storage=512, processor=Core i5
        assert eval_item.product.ram_gb == 16
        assert eval_item.product.storage_gb == 512
        assert eval_item.product.enrichment_status == "ENRICHED"
        assert eval_item.approved is True
        assert eval_item.status == "APPROVED"
        assert eval_item.can_select is True

    @pytest.mark.asyncio
    async def test_enrichment_does_not_fabricate_when_unavailable(self, laptop_mandate_strict):
        """Item demo_unverified_011 remains unverified if detail lookup cannot provide required RAM."""
        raw_items = await demo_adapter.search_products("laptop", region="demo_us", limit=10, page=2)
        cand_011 = next(p for p in raw_items if p.product_id == "demo_unverified_011")

        evals, disc_count, enr_count = await product_discovery_service._process_and_evaluate_products(
            products=[cand_011],
            mandate=laptop_mandate_strict,
            adapter=demo_adapter,
            region="demo_us",
        )

        eval_item = evals[0]
        assert eval_item.product.ram_gb is None
        assert eval_item.approved is False
        assert eval_item.status == "NEEDS_VERIFICATION"
        assert eval_item.can_select is False
        assert eval_item.unverified_reasons is not None
        assert any("RAM" in r for r in eval_item.unverified_reasons)


class TestThreeTierResultCategorization:
    """Verifies distinct separation into ELIGIBLE, NEEDS_VERIFICATION, and BLOCKED tiers."""

    @pytest.mark.asyncio
    async def test_three_tier_classification_and_ranking(self, laptop_mandate_strict):
        """Page 2 contains candidates across all 3 tiers; ELIGIBLE ranked first."""
        res = await product_discovery_service.search_candidates(
            mandate=laptop_mandate_strict,
            query="laptop",
            catalog_mode="demo",
            page=2,
            limit=10,
        )

        # Confirm all 3 statuses are represented
        statuses = {c.status for c in res.candidates}
        assert "APPROVED" in statuses
        assert "NEEDS_VERIFICATION" in statuses
        assert "BLOCKED" in statuses

        # Ranking invariant: All APPROVED must precede NEEDS_VERIFICATION, which precede BLOCKED
        current_tier = 0
        tier_map = {"APPROVED": 0, "NEEDS_VERIFICATION": 1, "BLOCKED": 2}
        for c in res.candidates:
            c_tier = tier_map[c.status]
            assert c_tier >= current_tier, f"Ranking violation: {c.status} appeared after tier {current_tier}"
            current_tier = c_tier

        # Counts telemetry matches reality
        assert res.eligible_count == sum(1 for c in res.candidates if c.status == "APPROVED")
        assert res.unverified_count == sum(1 for c in res.candidates if c.status == "NEEDS_VERIFICATION")
        assert res.blocked_count == sum(1 for c in res.candidates if c.status == "BLOCKED")
        assert res.compliant_count == res.eligible_count


class TestZeroBypassAndSecurityInvariants:
    """Ensures that NEEDS_VERIFICATION and BLOCKED candidates can NEVER be staged or purchased."""

    @pytest.mark.asyncio
    async def test_needs_verification_candidate_cannot_be_selected(self, laptop_mandate_strict):
        """Candidates with status NEEDS_VERIFICATION have can_select=False and approved=False."""
        res = await product_discovery_service.search_candidates(
            mandate=laptop_mandate_strict,
            query="laptop",
            catalog_mode="demo",
            page=2,
            limit=10,
        )

        unverified = [c for c in res.candidates if c.status == "NEEDS_VERIFICATION"]
        assert len(unverified) > 0
        for cand in unverified:
            assert cand.approved is False
            assert cand.can_select is False
            assert cand.selection_blocked_reason is not None
            assert cand.unverified_reasons is not None

    def test_staging_unverified_candidate_returns_http_400(self, laptop_mandate_strict):
        """Attempting to stage an unverified candidate fails-closed with HTTP 400."""
        unverified_product = DiscoveredProduct(
            product_id="demo_unverified_999",
            name="Laptop With Missing Specs",
            description="Ultra-thin laptop with unknown RAM and storage.",
            category="Laptops",
            price=120.0,
            currency="USD",
            condition="new",
            merchant_name="Official Merchant",
            merchant_verified=True,
            ram_gb=None,  # Missing required 16GB
            storage_gb=None,
        )

        res = client.post(
            "/api/v1/proposals/stage",
            json={
                "mandate": laptop_mandate_strict.model_dump(),
                "candidate": unverified_product.model_dump(),
                "user_id": "test_operator",
            },
        )

        assert res.status_code == 400
        assert "Policy evaluation blocked this item" in res.json()["detail"]

    def test_channel3_normalization_extracts_structured_attributes(self):
        """Structured attributes and key_features from Channel3 payloads are extracted correctly."""
        raw_ch3_item = {
            "id": "item_ch3_test_spec",
            "title": "Galaxy Book Ultra Laptop",
            "description": "Premium ultraportable laptop.",
            "category": {"title": "Laptops"},
            "key_features": [
                "16GB LPDDR4x Memory",
                "512GB NVMe SSD storage",
                "Intel Core i7-1165G7 Processor",
            ],
            "structured_attributes": {
                "ram": ["16 GB"],
                "storage-capacity": ["512 GB"],
                "processor-family": ["Intel core i7"],
            },
            "offers": [
                {
                    "price": "899.99",
                    "currency": "USD",
                    "domain": "target.com",
                    "availability": "instock",
                    "condition": "new",
                }
            ],
        }

        normalized = channel3_service._normalize_product(raw_ch3_item, fallback_currency="USD")
        assert normalized is not None
        assert normalized.ram_gb == 16
        assert normalized.storage_gb == 512
        assert normalized.storage_type == "NVMe SSD"
        assert normalized.processor == "Intel Core i7-1165G7"
        assert normalized.spec_verification_status == "VERIFIED"

