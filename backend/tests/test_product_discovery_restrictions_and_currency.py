"""
Regression tests for PayPal TrustGate Product Discovery:
1. Search query reflection in responses
2. INR / USD currency integrity and conversion
3. Product-category restrictions enforcement (e.g. 'new laptop only' blocking mouse/accessories)
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.services.policy_engine import policy_engine
from app.services.currency_service import currency_service
from app.services.product_discovery_service import product_discovery_service


@pytest.fixture
def client():
    return TestClient(app)


class TestCurrencyService:
    def test_usd_inr_conversion_math(self):
        # 1 USD = 83.0 INR benchmark
        usd_to_inr = currency_service.convert_amount(100.0, "USD", "INR")
        assert usd_to_inr == 8300.0

        inr_to_usd = currency_service.convert_amount(8300.0, "INR", "USD")
        assert inr_to_usd == 100.0

    def test_same_currency_no_op(self):
        assert currency_service.convert_amount(500.0, "INR", "INR") == 500.0
        assert currency_service.convert_amount(150.0, "USD", "USD") == 150.0

    def test_formatting(self):
        assert currency_service.get_symbol("INR") == "₹"
        assert currency_service.get_symbol("USD") == "$"
        assert currency_service.format_currency(60000, "INR") == "₹60,000.00"
        assert currency_service.format_currency(150, "USD") == "$150.00"


class TestPolicyEngineCategoryRestrictions:
    def test_laptop_mandate_approves_valid_laptop(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        tx = ProposedTransaction(
            product_name="Lenovo IdeaPad Slim 3 Intel Core i5 12th Gen 15.6 FHD Laptop",
            product_description="16GB RAM, 512GB SSD, Windows 11",
            category="Laptops",
            product_price=52990.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=52990.0,
            currency="INR",
            merchant_name="Official Lenovo Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )
        res = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
        assert res.approved is True
        assert len(res.violations) == 0

    def test_laptop_mandate_blocks_mouse_accessory(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        # Even though price is under 60,000, merchant verified, condition new,
        # it is a mouse accessory and must be deterministically BLOCKED by TG-003.
        tx = ProposedTransaction(
            product_name="Logitech MX Master 3S Wireless Performance Mouse",
            product_description="Ergonomic mouse with Quiet Clicks and 8K DPI sensor",
            category="Computer Accessories / Mice",
            product_price=8995.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=8995.0,
            currency="INR",
            merchant_name="Logitech Authorized Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )
        res = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
        assert res.approved is False
        assert any(v.rule_id == "TG-003" for v in res.violations)
        assert any("violates mandate restriction" in v.message for v in res.violations)

    def test_laptop_mandate_blocks_keyboard_accessory(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        tx = ProposedTransaction(
            product_name="Keychron K2 Wireless Mechanical Keyboard",
            product_description="75% Layout Bluetooth keyboard",
            category="Keyboards & Input Devices",
            product_price=8200.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=8200.0,
            currency="INR",
            merchant_name="Keychron India",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )
        res = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
        assert res.approved is False
        assert any(v.rule_id == "TG-003" for v in res.violations)


class TestProductDiscoveryServiceScenarios:
    @pytest.mark.asyncio
    async def test_scenario_a_laptop_search_amazon_in(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        response = await product_discovery_service.search_candidates(
            mandate=mandate,
            query="laptop",
            marketplace_id="demo",
            region="amazon.in",
        )

        assert response.query == "laptop"
        assert response.total_count > 0
        assert response.compliant_count > 0

        # Verify candidate 1 is Lenovo IdeaPad Slim 3, in INR, approved
        cand1 = response.candidates[0]
        assert cand1.product.currency == "INR"
        assert cand1.currency == "INR"
        assert cand1.approved is True
        assert cand1.budget_remaining > 0
        assert cand1.product.category == "Laptops"

    @pytest.mark.asyncio
    async def test_scenario_b_wireless_mouse_search_under_laptop_mandate(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        response = await product_discovery_service.search_candidates(
            mandate=mandate,
            query="wireless mouse",
            marketplace_id="demo",
            region="amazon.in",
        )

        assert response.query == "wireless mouse"
        assert response.total_count > 0
        # ALL mouse candidates must be blocked because the mandate specifies 'new laptop only'
        assert response.compliant_count == 0
        assert response.blocked_count == response.total_count

        for c in response.candidates:
            assert c.approved is False
            assert c.can_select is False
            assert any(v.rule_id == "TG-003" for v in c.policy_result.violations)

    @pytest.mark.asyncio
    async def test_scenario_c_amazon_us_usd_search(self):
        mandate = PurchaseMandate(
            max_amount=720.0,
            currency="USD",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
        )
        response = await product_discovery_service.search_candidates(
            mandate=mandate,
            query="laptop",
            marketplace_id="demo",
            region="amazon.com",
        )

        assert response.query == "laptop"
        assert response.total_count > 0
        # Candidates 1 through 5 are in USD matching the US marketplace
        for c in response.candidates[:5]:
            assert c.product.currency == "USD"
            assert c.currency == "USD"

        # Candidate 1 is fully compliant and approved in USD
        cand1 = response.candidates[0]
        assert cand1.approved is True
        assert cand1.budget_remaining > 0

        # Candidate 6 is an intentional European import demonstrating TG-002 Currency Mismatch blocking
        cand6 = response.candidates[5]
        assert cand6.approved is False
        assert any(v.rule_id == "TG-002" for v in cand6.policy_result.violations)


class TestProductDiscoveryApiEndpoint:
    def test_search_endpoint_reflects_query_and_currency(self, client):
        payload = {
            "mandate": {
                "max_amount": 60000.0,
                "currency": "INR",
                "allowed_conditions": ["new"],
                "require_merchant_verification": True,
                "allow_add_ons": False,
                "user_restrictions": ["new laptop only"],
            },
            "query": "laptop",
            "marketplace_id": "demo",
            "region": "amazon.in",
        }
        res = client.post("/api/v1/proposals/search", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "laptop"
        assert data["compliant_count"] >= 1
        assert data["candidates"][0]["currency"] == "INR"

    def test_search_endpoint_blocks_unrelated_category(self, client):
        payload = {
            "mandate": {
                "max_amount": 60000.0,
                "currency": "INR",
                "allowed_conditions": ["new"],
                "require_merchant_verification": True,
                "allow_add_ons": False,
                "user_restrictions": ["new laptop only"],
            },
            "query": "wireless mouse",
            "marketplace_id": "demo",
            "region": "amazon.in",
        }
        res = client.post("/api/v1/proposals/search", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "wireless mouse"
        assert data["compliant_count"] == 0
        assert data["blocked_count"] == data["total_count"]
