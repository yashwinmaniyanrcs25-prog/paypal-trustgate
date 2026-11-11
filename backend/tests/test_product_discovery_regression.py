"""Regression test suite for Product Discovery and Provider Price Parsing in PayPal TrustGate.

Verifies:
1. Valid positive provider price extraction across diverse Channel3 schemas
   (standard offer amount, integer cents, formatted string, multi-offer fallback).
2. Missing price rejection and skipping (never fabricates 0.0 or synthetic prices).
3. Zero and negative price rejection and skipping.
4. Accurate final_total calculation from validated product price plus applicable charges.
5. Candidate evaluation rejection when product price is non-positive without raising Pydantic validation error.
6. Channel3 search endpoint (/api/v1/channel3/search) returns HTTP 200 and filters out zero/missing price items.
7. Stage proposal endpoint (/api/v1/proposals/stage) returns clean HTTP 400 when candidate price is non-positive.
"""

import httpx
import pytest
from unittest.mock import AsyncMock, patch, PropertyMock
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.channel3_service import Channel3Service, channel3_service
from app.services.product_discovery_service import product_discovery_service

client = TestClient(app)


# -----------------------------------------------------------------------------
# 1. Valid Positive Provider Price Extraction
# -----------------------------------------------------------------------------

def test_channel3_normalization_valid_positive_price():
    """Verifies that valid positive prices in various Channel3 offer structures are parsed accurately."""
    # 1. Standard Channel3 Offer: price object with amount & currency
    item_standard = {
        "id": "item_kbd_01",
        "title": "Logitech MX Keys Wireless Keyboard",
        "description": "Premium wireless keyboard with smart illumination",
        "category": "Electronics",
        "offers": [
            {
                "domain": "bestbuy.com",
                "price": {"amount": 109.99, "currency": "USD"},
                "availability": "InStock",
                "condition": "new",
                "url": "https://bestbuy.com/logitech-mx",
            }
        ],
    }
    prod = channel3_service._normalize_product(item_standard)
    assert prod is not None
    assert prod.product_id == "ch3_item_kbd_01"
    assert prod.price == 109.99
    assert prod.currency == "USD"
    assert prod.merchant_name == "bestbuy.com"
    assert prod.condition == "new"

    # 2. Cent-based pricing (price_cents / amount_cents)
    item_cents = {
        "id": "item_kbd_02",
        "title": "Keychron K2 Mechanical Keyboard",
        "offers": [
            {
                "domain": "target.com",
                "price_cents": 7999,
                "currency": "USD",
                "condition": "new",
            }
        ],
    }
    prod_cents = channel3_service._normalize_product(item_cents)
    assert prod_cents is not None
    assert prod_cents.price == 79.99
    assert prod_cents.currency == "USD"

    # 3. String formatted price with currency symbol ("$89.95")
    item_str = {
        "id": "item_kbd_03",
        "title": "Anker Ergonomic Wireless Keyboard",
        "offers": [
            {
                "domain": "amazon.com",
                "price": "$89.95",
                "condition": "new",
            }
        ],
    }
    prod_str = channel3_service._normalize_product(item_str)
    assert prod_str is not None
    assert prod_str.price == 89.95

    # 4. Multi-offer fallback: First offer has null price, second offer has valid price
    item_multi_offer = {
        "id": "item_kbd_04",
        "title": "Corsair K65 Wireless Mini",
        "offers": [
            {"domain": "unverified.com", "price": None, "availability": "OutOfStock"},
            {"domain": "bestbuy.com", "price": {"amount": 99.99, "currency": "USD"}, "availability": "InStock", "condition": "new"},
        ],
    }
    prod_multi = channel3_service._normalize_product(item_multi_offer)
    assert prod_multi is not None
    assert prod_multi.price == 99.99
    assert prod_multi.merchant_name == "bestbuy.com"


# -----------------------------------------------------------------------------
# 2. Missing Price Handling
# -----------------------------------------------------------------------------

def test_channel3_normalization_missing_price():
    """Verifies that items with missing or empty prices are cleanly skipped (never defaulted to 0.0)."""
    # 1. Empty offers list and no top-level price
    item_no_offers = {
        "id": "item_no_offer",
        "title": "Discontinued Keyboard",
        "offers": [],
    }
    prod = channel3_service._normalize_product(item_no_offers)
    assert prod is None, "Product without offers or price must be skipped (returned None)"

    # 2. Offer with null price
    item_null_price = {
        "id": "item_null",
        "title": "Unpriced Keyboard",
        "offers": [{"domain": "store.com", "price": None}],
    }
    prod_null = channel3_service._normalize_product(item_null_price)
    assert prod_null is None

    # 3. Offer with empty price dict
    item_empty_price_dict = {
        "id": "item_empty_dict",
        "title": "Malformed Price Keyboard",
        "offers": [{"domain": "store.com", "price": {}}],
    }
    prod_empty = channel3_service._normalize_product(item_empty_price_dict)
    assert prod_empty is None


# -----------------------------------------------------------------------------
# 3. Zero and Negative Price Handling
# -----------------------------------------------------------------------------

def test_channel3_normalization_zero_and_negative_price():
    """Verifies that zero or negative prices are strictly rejected and skipped."""
    # 1. Zero price float
    item_zero = {
        "id": "item_zero",
        "title": "Free Promotional Keyboard",
        "offers": [{"domain": "promo.com", "price": {"amount": 0.0, "currency": "USD"}}],
    }
    prod_zero = channel3_service._normalize_product(item_zero)
    assert prod_zero is None, "Zero price item must be skipped"

    # 2. Zero price string
    item_zero_str = {
        "id": "item_zero_str",
        "title": "Zero String Keyboard",
        "offers": [{"domain": "promo.com", "price": "$0.00"}],
    }
    assert channel3_service._normalize_product(item_zero_str) is None

    # 3. Negative price
    item_neg = {
        "id": "item_neg",
        "title": "Negative Price Anomaly",
        "offers": [{"domain": "glitch.com", "price": {"amount": -15.00, "currency": "USD"}}],
    }
    assert channel3_service._normalize_product(item_neg) is None


# -----------------------------------------------------------------------------
# 4. Correct final_total Calculation in Candidate Evaluation
# -----------------------------------------------------------------------------

def test_evaluate_candidate_correct_final_total_calculation():
    """Verifies that final_total is correctly calculated from validated product price plus applicable charges."""
    mandate = PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )
    product = DiscoveredProduct(
        product_id="prod_eval_valid",
        name="Logitech G915 TKL",
        description="Wireless RGB mechanical gaming keyboard",
        category="Electronics",
        price=129.99,
        currency="USD",
        condition="new",
        merchant_name="Official Electronics",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="channel3_api",
        is_demo_data=False,
        demo_notice="",
    )

    evaluation = product_discovery_service._evaluate_candidate(product, mandate)
    assert evaluation is not None
    assert evaluation.approved is True
    assert evaluation.status == "APPROVED"
    assert evaluation.can_select is True
    assert evaluation.product.price == 129.99

    # Verify final_total in transaction summary equals product price (no add-ons)
    tx_summary = evaluation.policy_result.transaction_summary
    assert tx_summary["final_total"] == 129.99
    assert tx_summary["currency"] == "USD"
    itemized = tx_summary["itemized_breakdown"]
    assert itemized["product_price"] == 129.99
    assert itemized["shipping_cost"] == 0.0
    assert itemized["tax"] == 0.0
    assert itemized["additional_charges"] == 0.0

    # Verify remaining budget
    expected_remaining = round(150.00 - 129.99, 2)
    assert evaluation.budget_remaining == expected_remaining


# -----------------------------------------------------------------------------
# 5. Candidate Evaluation Rejection on Non-Positive Price
# -----------------------------------------------------------------------------

def test_evaluate_candidate_rejects_zero_or_negative_price():
    """Verifies that zero price is rejected by _evaluate_candidate and negative price is rejected at model boundary."""
    mandate = PurchaseMandate(max_amount=150.00, currency="USD")

    # 1. Zero price candidate (valid DiscoveredProduct since ge=0, but rejected by _evaluate_candidate)
    zero_prod = DiscoveredProduct(
        product_id="prod_zero",
        name="Zero Price Item",
        category="Electronics",
        price=0.0,
        currency="USD",
        condition="new",
        merchant_name="Merchant",
        merchant_verified=True,
        data_source="channel3_api",
        is_demo_data=False,
    )
    eval_zero = product_discovery_service._evaluate_candidate(zero_prod, mandate)
    assert eval_zero is None, "Candidate with price=0.0 must be rejected/skipped gracefully"

    # 2. Negative price is rejected at the DiscoveredProduct validation boundary (ge=0)
    with pytest.raises(ValidationError):
        DiscoveredProduct(
            product_id="prod_neg",
            name="Negative Price Item",
            category="Electronics",
            price=-10.0,
            currency="USD",
            condition="new",
            merchant_name="Merchant",
            merchant_verified=True,
            data_source="channel3_api",
            is_demo_data=False,
        )


# -----------------------------------------------------------------------------
# 6. End-to-End API Search Path with Mandate (/api/v1/channel3/search)
# -----------------------------------------------------------------------------

def test_channel3_search_api_with_mandate_filters_zero_and_missing_prices():
    """Verifies that POST /api/v1/channel3/search returns HTTP 200 and filters out zero/missing price items."""
    # Mock raw response from Channel3 with 3 items: valid, zero price, and missing price
    mock_raw_items = [
        {
            "id": "ch3_valid_01",
            "title": "Logitech MX Mechanical Keyboard",
            "category": "Electronics",
            "offers": [
                {
                    "domain": "target.com",
                    "price": {"amount": 139.99, "currency": "USD"},
                    "availability": "InStock",
                    "condition": "new",
                }
            ],
        },
        {
            "id": "ch3_zero_02",
            "title": "Zero Price Promotion Item",
            "category": "Electronics",
            "offers": [
                {
                    "domain": "target.com",
                    "price": {"amount": 0.0, "currency": "USD"},
                    "availability": "InStock",
                    "condition": "new",
                }
            ],
        },
        {
            "id": "ch3_missing_03",
            "title": "Missing Price Item",
            "category": "Electronics",
            "offers": [],
        },
    ]

    # Mock the actual Channel3 provider HTTP response containing:
    # 1 valid product ($139.99), 1 zero-priced product ($0.0), 1 product with no price.
    mock_provider_payload = {"products": mock_raw_items}
    mock_response = httpx.Response(
        status_code=200,
        json=mock_provider_payload,
        request=httpx.Request("POST", f"{settings.get_channel3_base_url()}/search"),
    )

    # Configure the actual Channel3 settings field and mock the HTTP provider boundary
    with patch.object(settings, "CHANNEL3_API_KEY", "c3_test_valid_key_12345"), \
         patch.object(Channel3Service, "is_configured", new_callable=PropertyMock, return_value=True), \
         patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_response)):

        res = client.post(
            "/api/v1/channel3/search",
            json={
                "query": "wireless keyboard",
                "limit": 5,
                "currency": "USD",
                "mandate": {
                    "max_amount": 150.00,
                    "currency": "USD",
                    "allowed_conditions": ["new"],
                    "require_merchant_verification": False,
                    "allow_add_ons": False,
                },
            },
        )

        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
        data = res.json()
        assert "candidates" in data
        # Only the valid product ($139.99) should be present; zero and missing items must be excluded
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["product"]["name"] == "Logitech MX Mechanical Keyboard"
        assert data["candidates"][0]["product"]["price"] == 139.99
        assert data["compliant_count"] == 1
        assert data["total_count"] == 1


# -----------------------------------------------------------------------------
# 7. Safe Rejection on Staging Proposal with Non-Positive Price
# -----------------------------------------------------------------------------

def test_stage_proposal_rejects_zero_price_candidate():
    """Verifies that /api/v1/proposals/stage rejects candidates with price <= 0 with HTTP 400."""
    res = client.post(
        "/api/v1/proposals/stage",
        json={
            "mandate": {
                "max_amount": 150.00,
                "currency": "USD",
                "allowed_conditions": ["new"],
                "require_merchant_verification": False,
                "allow_add_ons": False,
            },
            "candidate": {
                "product_id": "prod_stage_zero",
                "name": "Zero Staged Candidate",
                "price": 0.0,
                "currency": "USD",
                "condition": "new",
                "merchant_name": "Target",
                "merchant_verified": True,
                "data_source": "channel3_api",
                "is_demo_data": False,
                "demo_notice": "",
            },
        },
    )
    assert res.status_code == 400
    assert "Invalid non-positive price" in res.json()["detail"]
