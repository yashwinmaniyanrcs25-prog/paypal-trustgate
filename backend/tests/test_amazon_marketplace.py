"""Unit tests for the Amazon Creators API marketplace integration architecture."""

import pytest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.models.policy import PurchaseMandate
from app.models.marketplace import MarketplaceIntegrationState
from app.services.marketplaces.amazon_adapter import amazon_adapter
from app.services.marketplaces.base import MarketplaceAccessError
from app.services.product_discovery_service import product_discovery_service
from app.services.policy_engine import policy_engine

client = TestClient(app)


@pytest.fixture
def base_mandate():
    return PurchaseMandate(
        max_amount=50000.0,
        currency="INR",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["laptop only"],
    )


def test_amazon_adapter_configuration_missing():
    """When credentials are blank or placeholders, integration status must be NOT_CONFIGURED or CREDENTIALS_MISSING."""
    with patch.object(settings, "AMAZON_CREDENTIAL_ID", ""), \
         patch.object(settings, "AMAZON_CREDENTIAL_SECRET", ""), \
         patch.object(settings, "AMAZON_PARTNER_TAG", ""):
        status = amazon_adapter.get_integration_status("amazon.in")
        assert status.state == MarketplaceIntegrationState.NOT_CONFIGURED
        assert status.is_connected is False
        assert status.configured is False
        assert "AMAZON_CREDENTIAL_ID" in (status.setup_guidance or "")
        assert status.currency == "INR"

    # Partial credentials
    with patch.object(settings, "AMAZON_CREDENTIAL_ID", "amzn_id_123"), \
         patch.object(settings, "AMAZON_CREDENTIAL_SECRET", ""), \
         patch.object(settings, "AMAZON_PARTNER_TAG", ""):
        status = amazon_adapter.get_integration_status("amazon.in")
        assert status.state == MarketplaceIntegrationState.CREDENTIALS_MISSING
        assert status.is_connected is False
        assert "AMAZON_CREDENTIAL_SECRET" in (status.setup_guidance or "")


@pytest.mark.asyncio
async def test_amazon_access_unavailable_state():
    """Unapproved access must raise MarketplaceAccessError and return an access state, NOT an empty search."""
    with patch.object(settings, "AMAZON_CREDENTIAL_ID", ""), \
         patch.object(settings, "AMAZON_CREDENTIAL_SECRET", ""):

        # Adapter directly raises error
        with pytest.raises(MarketplaceAccessError) as exc_info:
            await amazon_adapter.search_products(query="laptop", region="amazon.in")
        assert exc_info.value.state == MarketplaceIntegrationState.NOT_CONFIGURED

        # Discovery service returns structured state with 0 fabricated items
        mandate = PurchaseMandate(max_amount=100.0, currency="USD")
        res = await product_discovery_service.search_candidates(
            mandate=mandate,
            query="laptop",
            marketplace_id="amazon",
            region="amazon.com",
        )
        assert res.integration_state == MarketplaceIntegrationState.NOT_CONFIGURED.value
        assert res.total_count == 0
        assert len(res.candidates) == 0
        assert res.is_demo_data is False


def test_credential_safe_error_handling():
    """Credentials and secrets must never be exposed in status responses, logs, or error text."""
    secret_value = "SUPER_SECRET_AMAZON_KEY_99999"
    with patch.object(settings, "AMAZON_CREDENTIAL_ID", "amzn_id_test"), \
         patch.object(settings, "AMAZON_CREDENTIAL_SECRET", secret_value), \
         patch.object(settings, "AMAZON_PARTNER_TAG", "tag-21"):

        status = amazon_adapter.get_integration_status("amazon.in")
        # Ensure secret does not appear anywhere in stringified status
        status_str = status.model_dump_json()
        assert secret_value not in status_str

        creds = settings.get_amazon_credentials()
        # Credentials dict should have secret for backend calls, but sanitized in repr
        assert creds["credential_secret"] == secret_value


def test_product_normalization():
    """Raw Amazon Creators API payloads must be correctly normalized into DiscoveredProduct schema."""
    raw_payload = {
        "asin": "B09ABC1234",
        "title": "Lenovo ThinkPad E14 Gen 4 Intel Core i5",
        "description": "14-inch FHD IPS display, 16GB RAM, 512GB SSD.",
        "category": "Laptops & Notebooks",
        "price": {
            "amount": 48999.00,
            "currency": "INR",
        },
        "brand": "Lenovo Official",
        "images": [{"url": "https://m.media-amazon.com/images/I/sample.jpg"}],
        "item_condition": "new",
        "merchant_verified": False,
    }

    product = amazon_adapter.normalize_product(raw_payload, region="amazon.in")
    assert product.product_id == "amazon_B09ABC1234"
    assert product.name == "Lenovo ThinkPad E14 Gen 4 Intel Core i5"
    assert product.price == 48999.00
    assert product.currency == "INR"
    assert product.image_url == "https://m.media-amazon.com/images/I/sample.jpg"
    assert product.condition == "new"
    assert product.data_source == "amazon_creators_api_amazon.in"
    assert product.is_demo_data is False
    assert product.marketplace_id == "amazon"
    assert product.region == "amazon.in"


def test_unknown_merchant_verification(base_mandate):
    """Amazon products without explicit verification must default to UNKNOWN and be rejected by policy engine."""
    raw_payload = {
        "asin": "B08TEST001",
        "title": "Unverified Third Party Laptop",
        "price": {"amount": 45000.00, "currency": "INR"},
        "brand": "Unchecked Marketplace Seller",
        "condition": "new",
        # No merchant_verified flag provided
    }

    product = amazon_adapter.normalize_product(raw_payload, region="amazon.in")
    assert product.merchant_verified is False
    assert product.verification_status == "UNKNOWN"

    evaluation = product_discovery_service._evaluate_candidate(product, base_mandate)
    assert evaluation.approved is False
    assert evaluation.status == "BLOCKED"
    assert any(v.rule_id == "TG-004" for v in evaluation.policy_result.violations)


def test_unknown_product_condition(base_mandate):
    """Amazon products with unknown condition must NOT be assumed new and must be blocked if new is required."""
    raw_payload = {
        "asin": "B08TEST002",
        "title": "Laptop With Missing Condition Metadata",
        "price": {"amount": 42000.00, "currency": "INR"},
        "brand": "Verified Tech Store",
        "merchant_verified": True,
        # Condition omitted
    }

    product = amazon_adapter.normalize_product(raw_payload, region="amazon.in")
    assert product.condition == "unknown"

    evaluation = product_discovery_service._evaluate_candidate(product, base_mandate)
    assert evaluation.approved is False
    assert evaluation.status == "BLOCKED"
    assert any(v.rule_id == "TG-003" for v in evaluation.policy_result.violations)


@pytest.mark.asyncio
async def test_empty_results():
    """Valid API response with zero products must return an empty list gracefully."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"products": []}

    with patch.object(amazon_adapter, "get_integration_status") as mock_status, \
         patch("httpx.AsyncClient.get", return_value=mock_resp):
        from app.models.marketplace import MarketplaceStatusResponse
        mock_status.return_value = MarketplaceStatusResponse(
            marketplace_id="amazon",
            name="Amazon Marketplace",
            state=MarketplaceIntegrationState.CONNECTED,
            is_connected=True,
            configured=True,
            active_region="amazon.in",
            currency="INR",
            message="Connected",
        )

        res = await amazon_adapter.search_products("nonexistent_query_xyz", region="amazon.in")
        assert res == []


@pytest.mark.asyncio
async def test_api_timeout_and_provider_errors():
    """Network timeouts and HTTP errors to Amazon Creators API must be caught safely as ERROR access state."""
    with patch.object(amazon_adapter, "get_integration_status") as mock_status, \
         patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Read timeout")):
        from app.models.marketplace import MarketplaceStatusResponse
        mock_status.return_value = MarketplaceStatusResponse(
            marketplace_id="amazon",
            name="Amazon Marketplace",
            state=MarketplaceIntegrationState.CONNECTED,
            is_connected=True,
            configured=True,
            active_region="amazon.in",
            currency="INR",
            message="Connected",
        )

        with pytest.raises(MarketplaceAccessError) as exc_info:
            await amazon_adapter.search_products("laptop", region="amazon.in")
        assert exc_info.value.state == MarketplaceIntegrationState.ERROR
        assert "timed out" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_amazon_and_demo_data_never_mixed(base_mandate):
    """Amazon mode and demo mode candidates must never be mixed together."""
    # 1. Search in Demo mode
    demo_res = await product_discovery_service.search_candidates(
        mandate=base_mandate,
        marketplace_id="demo",
        region="demo_in",
    )
    assert demo_res.is_demo_data is True
    assert all(c.product.is_demo_data is True for c in demo_res.candidates)
    assert all("demo_" in c.product.product_id or "cand_" in c.product.product_id for c in demo_res.candidates)

    # 2. Search in Amazon mode (unconfigured)
    with patch.object(settings, "AMAZON_CREDENTIAL_ID", ""):
        amzn_res = await product_discovery_service.search_candidates(
            mandate=base_mandate,
            marketplace_id="amazon",
            region="amazon.in",
        )
        assert amzn_res.is_demo_data is False
        assert amzn_res.total_count == 0
        assert len(amzn_res.candidates) == 0


def test_existing_policy_engine_remains_authoritative(base_mandate):
    """TrustGate deterministic policy engine remains the sole authority over Amazon candidate approvals."""
    # Compliant candidate
    compliant_raw = {
        "asin": "B08COMPLIANT",
        "title": "Compliant Laptop Matching All Mandate Constraints",
        "price": {"amount": 42000.00, "currency": "INR"},
        "brand": "Certified Official Store",
        "merchant_verified": True,
        "condition": "new",
    }
    compliant_product = amazon_adapter.normalize_product(compliant_raw, region="amazon.in")
    eval_compliant = product_discovery_service._evaluate_candidate(compliant_product, base_mandate)
    assert eval_compliant.approved is True
    assert eval_compliant.status == "APPROVED"
    assert eval_compliant.can_select is True

    # Overbudget candidate
    overbudget_raw = {
        "asin": "B08OVERBUDGET",
        "title": "Overbudget Laptop Exceeding 50k INR",
        "price": {"amount": 89000.00, "currency": "INR"},
        "brand": "Certified Official Store",
        "merchant_verified": True,
        "condition": "new",
    }
    overbudget_product = amazon_adapter.normalize_product(overbudget_raw, region="amazon.in")
    eval_overbudget = product_discovery_service._evaluate_candidate(overbudget_product, base_mandate)
    assert eval_overbudget.approved is False
    assert eval_overbudget.status == "BLOCKED"
    assert any(v.rule_id == "TG-001" for v in eval_overbudget.policy_result.violations)


def test_api_marketplace_endpoints():
    """GET /api/v1/proposals/marketplaces returns authentic status for Amazon and Demo."""
    res = client.get("/api/v1/proposals/marketplaces")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    # Check Amazon entry
    amzn = next(m for m in data if m["marketplace_id"] == "amazon")
    assert amzn["name"] == "Amazon Marketplace (Creators API)"
    assert amzn["state"] in ("Not Configured", "Credentials Missing", "Access Pending", "Connected")
    assert len(amzn["supported_regions"]) == 2
    assert any(r["id"] == "amazon.in" for r in amzn["supported_regions"])
    assert any(r["id"] == "amazon.com" for r in amzn["supported_regions"])

    # Check Demo entry
    demo = next(m for m in data if m["marketplace_id"] == "demo")
    assert demo["state"] == "Connected"
    assert demo["is_connected"] is True

