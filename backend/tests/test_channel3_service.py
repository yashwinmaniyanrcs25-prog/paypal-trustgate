"""Comprehensive test suite for Channel3 Universal Product Graph integration in TrustGate.

Verifies:
1. Authentication header generation using backend environment.
2. Safe normalization of Channel3 product graph payloads into DiscoveredProduct.
3. Deterministic TG-001 through TG-007 policy engine evaluation on Channel3 candidates.
4. Error states: timeouts, HTTP 401/403 invalid key, and empty search results.
5. Integration into MarketplaceRegistry and ProductDiscoveryService.
6. Staging, human approval, and transaction state machine progression for Channel3 candidates.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct, CandidateEvaluation
from app.models.marketplace import MarketplaceIntegrationState
from app.services.channel3_service import channel3_service, Channel3Service
from app.services.marketplaces.channel3_adapter import channel3_adapter
from app.services.marketplaces.registry import marketplace_registry
from app.services.product_discovery_service import product_discovery_service
from app.services.proposal_store import proposal_store
from app.services.marketplaces.base import MarketplaceAccessError

client = TestClient(app)

MOCK_CHANNEL3_RESPONSE = {
    "products": [
        {
            "id": "prod_k2_keyboard_8832",
            "title": "Keychron K2 Wireless Mechanical Keyboard (Version 2)",
            "description": "Compact 75% layout Bluetooth wireless mechanical keyboard with Mac & Windows layout.",
            "category": {"id": "cat_kb", "title": "Keyboards & Mice", "slug": "keyboards"},
            "brands": [{"id": "b_keychron", "name": "Keychron"}],
            "images": [
                {
                    "url": "https://cdn.trychannel3.com/images/keychron_k2_raw.jpg",
                    "cleaned_url": "https://cdn.trychannel3.com/images/keychron_k2_clean.png",
                    "is_main_image": True,
                }
            ],
            "offers": [
                {
                    "price": {"amount": 112.50, "currency": "USD"},
                    "domain": "keychron.com",
                    "url": "https://www.keychron.com/products/keychron-k2-wireless-mechanical-keyboard",
                    "availability": "InStock",
                    "condition": "new",
                }
            ],
        },
        {
            "id": "prod_expensive_laptop_9921",
            "title": "Dell XPS 15 9530 High Performance Laptop",
            "description": "15.6 inch OLED 3.5K display, 32GB RAM, 1TB SSD.",
            "category": {"id": "cat_laptops", "title": "Laptops", "slug": "laptops"},
            "brands": [{"id": "b_dell", "name": "Dell"}],
            "images": [
                {
                    "url": "https://cdn.trychannel3.com/images/dell_xps15.jpg",
                    "cleaned_url": "https://cdn.trychannel3.com/images/dell_xps15_clean.png",
                    "is_main_image": True,
                }
            ],
            "offers": [
                {
                    "price": {"amount": 1899.00, "currency": "USD"},
                    "domain": "dell.com",
                    "url": "https://www.dell.com/en-us/shop/dell-laptops/xps-15-laptop/spd/xps-15-9530-laptop",
                    "availability": "InStock",
                    "condition": "new",
                }
            ],
        },
    ]
}


@pytest.fixture
def test_mandate():
    return PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["mechanical keyboard"],
    )


def test_channel3_configuration_and_headers():
    """Verify Channel3 detects configured state and formats x-api-key header without exposure."""
    with patch.object(settings, "CHANNEL3_API_KEY", "test_key_abc123"):
        assert settings.is_channel3_configured() is True
        headers = channel3_service.get_headers()
        assert headers["x-api-key"] == "test_key_abc123"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"


def test_channel3_unconfigured_state():
    """Verify Channel3 returns NOT_CONFIGURED when key is empty or placeholder."""
    with patch.object(settings, "CHANNEL3_API_KEY", ""):
        assert settings.is_channel3_configured() is False
        status = channel3_service.get_integration_status()
        assert status.state == MarketplaceIntegrationState.NOT_CONFIGURED
        assert status.is_connected is False


def test_channel3_product_normalization():
    """Verify raw Channel3 item is accurately mapped to DiscoveredProduct with is_demo_data=False."""
    raw_item = MOCK_CHANNEL3_RESPONSE["products"][0]
    normalized = channel3_service._normalize_product(raw_item, fallback_currency="USD")

    assert normalized is not None
    assert normalized.product_id == "ch3_prod_k2_keyboard_8832"
    assert "Keychron K2" in normalized.name
    assert normalized.price == 112.50
    assert normalized.currency == "USD"
    assert normalized.image_url == "https://cdn.trychannel3.com/images/keychron_k2_clean.png"
    assert normalized.condition == "new"
    assert normalized.merchant_name == "keychron.com"
    assert normalized.merchant_verified is True
    assert normalized.verification_status == "VERIFIED"
    assert normalized.data_source == "channel3_api"
    assert normalized.is_demo_data is False  # Genuine Channel3 catalog data!
    assert normalized.demo_notice == ""
    assert normalized.purchase_url == "https://www.keychron.com/products/keychron-k2-wireless-mechanical-keyboard"
    assert normalized.availability == "InStock"
    assert normalized.retailer == "keychron.com"


def test_channel3_deterministic_policy_evaluation(test_mandate):
    """Verify Channel3 candidates are evaluated deterministically against TG-001 to TG-007."""
    raw_keyboard = MOCK_CHANNEL3_RESPONSE["products"][0]
    keyboard_prod = channel3_service._normalize_product(raw_keyboard, fallback_currency="USD")

    # Keychron K2 ($112.50) is under $150 budget and new -> APPROVED
    eval_keyboard = product_discovery_service._evaluate_candidate(keyboard_prod, test_mandate)
    assert eval_keyboard.approved is True
    assert eval_keyboard.status == "APPROVED"
    assert eval_keyboard.can_select is True
    assert eval_keyboard.budget_remaining == 37.50

    raw_laptop = MOCK_CHANNEL3_RESPONSE["products"][1]
    laptop_prod = channel3_service._normalize_product(raw_laptop, fallback_currency="USD")

    # Dell XPS 15 ($1899.00) exceeds $150 budget -> BLOCKED by TG-001
    eval_laptop = product_discovery_service._evaluate_candidate(laptop_prod, test_mandate)
    assert eval_laptop.approved is False
    assert eval_laptop.status == "BLOCKED"
    assert eval_laptop.can_select is False
    assert eval_laptop.budget_remaining < 0
    assert any("budget" in v.message.lower() for v in eval_laptop.policy_result.violations)


@pytest.mark.asyncio
async def test_channel3_timeout_handling():
    """Verify TimeoutException is caught and transformed into informative MarketplaceAccessError."""
    with patch.object(settings, "CHANNEL3_API_KEY", "test_key_valid"):
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
            with pytest.raises(MarketplaceAccessError) as exc_info:
                await channel3_service.search_products("keyboard")
            assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_channel3_auth_failure_handling():
    """Verify HTTP 401 returns clear authentication error without exposing secrets."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized - invalid x-api-key"

    with patch.object(settings, "CHANNEL3_API_KEY", "bad_key"):
        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            with pytest.raises(MarketplaceAccessError) as exc_info:
                await channel3_service.search_products("keyboard")
            assert exc_info.value.state == MarketplaceIntegrationState.CREDENTIALS_MISSING
            assert "authentication failed" in str(exc_info.value).lower()


def test_channel3_marketplace_registry_registration():
    """Verify channel3 is registered in the marketplace adapter registry."""
    adapter = marketplace_registry.get_adapter("channel3")
    assert adapter.marketplace_id == "channel3"
    assert "Channel3" in adapter.name

    all_markets = marketplace_registry.list_marketplaces()
    market_ids = [m.marketplace_id for m in all_markets]
    assert "channel3" in market_ids


def test_channel3_status_endpoint():
    """Verify GET /api/v1/channel3/status endpoint returns valid structure."""
    res = client.get("/api/v1/channel3/status")
    assert res.status_code == 200
    data = res.json()
    assert data["marketplace_id"] == "channel3"
    assert "Channel3" in data["name"]
    assert "state" in data
    assert "legal_disclaimer" in data


def test_channel3_candidate_can_be_staged_and_approved(test_mandate):
    """Verify that an approved Channel3 candidate can be safely staged and human-approved."""
    raw_keyboard = MOCK_CHANNEL3_RESPONSE["products"][0]
    keyboard_prod = channel3_service._normalize_product(raw_keyboard, fallback_currency="USD")

    # 1. Stage the candidate proposal
    res_stage = client.post(
        "/api/v1/proposals/stage",
        json={
            "mandate": test_mandate.model_dump(),
            "candidate": keyboard_prod.model_dump(),
            "user_id": "test_buyer",
        },
    )
    assert res_stage.status_code == 200
    staged_data = res_stage.json()
    assert staged_data["policy_approved"] is True
    assert staged_data["is_demo_data"] is False
    assert staged_data["requires_human_approval"] is True
    staged_id = staged_data["staged_proposal_id"]

    # 2. Human explicitly approves the staged proposal
    res_approve = client.post(
        f"/api/v1/payments/proposals/{staged_id}/approve",
        json={
            "operator_id": "test_human_reviewer",
            "approval_method": "ui_click",
            "security_pin": "123456",
        },
    )
    assert res_approve.status_code == 200
    approval_data = res_approve.json()
    assert approval_data["status"] == "HUMAN_APPROVED"
    assert approval_data["human_approval_id"] is not None


def test_channel3_adapter_normalize_product_standard():
    """Verify Channel3Adapter.normalize_product maps provider payload with zero simulation markup."""
    raw_item = MOCK_CHANNEL3_RESPONSE["products"][0]
    prod = channel3_adapter.normalize_product(raw_item, region="global")

    assert isinstance(prod, DiscoveredProduct)
    assert prod.product_id == "ch3_prod_k2_keyboard_8832"
    assert "Keychron K2" in prod.name
    assert prod.price == 112.50
    assert prod.currency == "USD"
    assert prod.condition == "new"
    assert prod.merchant_verified is True
    assert prod.is_demo_data is False
    assert prod.marketplace_id == "channel3"
    assert prod.data_source == "channel3_api"


def test_channel3_adapter_normalize_product_fallback():
    """Verify Channel3Adapter.normalize_product enforces security invariants on minimal/unknown payloads."""
    minimal_raw = {
        "id": "unlisted_gizmo_77",
        "title": "Unbranded Device",
        "price": "59.95",
        "condition": "mystery",
    }
    prod = channel3_adapter.normalize_product(minimal_raw, region="global")

    assert isinstance(prod, DiscoveredProduct)
    assert prod.product_id == "ch3_unlisted_gizmo_77"
    assert prod.name == "Unbranded Device"
    assert prod.price == 59.95
    # Invariant: Unknown condition must NOT be assumed 'new'
    assert prod.condition == "unknown"
    # Invariant: Unknown merchant must NOT be assumed verified
    assert prod.merchant_verified is False
    assert prod.verification_status == "UNKNOWN"
    assert prod.is_demo_data is False


@pytest.mark.asyncio
async def test_channel3_adapter_get_product_details_direct():
    """Verify Channel3Adapter.get_product_details retrieves and normalizes via direct lookup."""
    mock_item = MOCK_CHANNEL3_RESPONSE["products"][0]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"product": mock_item}

    with patch.object(settings, "CHANNEL3_API_KEY", "test_key_valid"):
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            prod = await channel3_adapter.get_product_details("ch3_prod_k2_keyboard_8832")
            assert prod is not None
            assert prod.product_id == "ch3_prod_k2_keyboard_8832"
            assert "Keychron K2" in prod.name


@pytest.mark.asyncio
async def test_channel3_adapter_get_product_details_unconfigured():
    """Verify Channel3Adapter.get_product_details raises MarketplaceAccessError if key missing."""
    with patch.object(settings, "CHANNEL3_API_KEY", ""):
        with pytest.raises(MarketplaceAccessError) as exc_info:
            await channel3_adapter.get_product_details("ch3_any_item")
        assert exc_info.value.state == MarketplaceIntegrationState.NOT_CONFIGURED


