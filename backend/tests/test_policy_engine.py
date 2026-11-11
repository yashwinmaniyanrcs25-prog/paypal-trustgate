"""Unit tests for TrustGate Deterministic Policy Engine."""

import pytest
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.services.policy_engine import policy_engine
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def base_mandate():
    return PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["US shipping only"],
    )


@pytest.fixture
def compliant_transaction():
    return ProposedTransaction(
        product_name="Keychron K2 Pro Wireless Mechanical Keyboard",
        product_description="Tactile brown switches, 75% layout, RGB backlit.",
        product_price=109.99,
        shipping_cost=0.00,
        tax=8.80,
        additional_charges=0.00,
        final_total=118.79,
        currency="USD",
        merchant_name="Keychron Official Direct",
        merchant_verified=True,
        product_condition="new",
        add_ons=[],
    )


def test_compliant_purchase_passes(base_mandate, compliant_transaction):
    """Compliant purchase satisfying all mandate constraints must pass."""
    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is True
    assert res.status == "APPROVED"
    assert len(res.violations) == 0
    assert all(c.passed for c in res.checks)
    assert res.can_proceed_to_paypal is True
    assert res.requires_human_approval is True
    assert res.policy_signature.startswith("tg_sig_")
    assert "strictly satisfies all mandate constraints" in res.explanation


def test_over_budget_blocked(base_mandate, compliant_transaction):
    """Purchase exceeding mandate maximum amount must be blocked."""
    compliant_transaction.product_price = 160.00
    compliant_transaction.tax = 12.80
    compliant_transaction.final_total = 172.80

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-001" for v in res.violations)
    assert any("exceeds user mandate maximum" in v.message for v in res.violations)


def test_math_tampering_blocked(base_mandate, compliant_transaction):
    """Declared final total not matching itemized charge components must be blocked."""
    # Itemized sum is 109.99 + 8.80 = 118.79, but declared final_total is spoofed as 99.00
    compliant_transaction.final_total = 99.00

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any("diverges from itemized components sum" in v.message for v in res.violations)


def test_currency_mismatch_blocked(base_mandate, compliant_transaction):
    """Transaction currency different from mandate currency must be blocked."""
    compliant_transaction.currency = "EUR"

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-002" for v in res.violations)
    assert any("does not match mandate requirement" in v.message for v in res.violations)


def test_wrong_condition_blocked(base_mandate, compliant_transaction):
    """Product condition not listed in allowed conditions must be blocked."""
    compliant_transaction.product_condition = "refurbished"

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-003" for v in res.violations)
    assert any("is not allowed by mandate" in v.message for v in res.violations)


def test_unverified_merchant_blocked(base_mandate, compliant_transaction):
    """Unverified merchant when verification is required must be blocked."""
    compliant_transaction.merchant_verified = False
    compliant_transaction.merchant_name = "Random Dropship Outlet"

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-004" for v in res.violations)
    assert any("is not verified" in v.message for v in res.violations)


def test_blacklisted_merchant_blocked(compliant_transaction):
    """Merchant on the malicious/blacklisted vendor list must be blocked even if require_verification is False."""
    mandate = PurchaseMandate(max_amount=200.0, require_merchant_verification=False)
    compliant_transaction.merchant_name = "unknown_scam_store"

    res = policy_engine.evaluate_mandate(mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-004" for v in res.violations)
    assert any("untrusted or blacklisted vendor" in v.message for v in res.violations)


def test_prohibited_add_ons_blocked(base_mandate, compliant_transaction):
    """Prohibited add-on items must be blocked when allow_add_ons is False."""
    compliant_transaction.add_ons = ["Express 2-Year Replacement Warranty", "Desk Mat Bundle"]
    compliant_transaction.product_price = 109.99
    compliant_transaction.additional_charges = 25.00
    compliant_transaction.final_total = 143.79  # Total is under $150 budget, but add-ons are prohibited

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-005" for v in res.violations)
    assert any("prohibits add-ons" in v.message for v in res.violations)


def test_invalid_or_missing_data_fails_safely(base_mandate, compliant_transaction):
    """Negative prices or empty product names must fail safely under Rule 6."""
    compliant_transaction.product_price = -10.00
    compliant_transaction.final_total = -10.00

    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="human_user")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-006" for v in res.violations)


def test_ai_agent_caller_blocked(base_mandate, compliant_transaction):
    """AI agent attempting to authorize payment must fail under Rule 7."""
    res = policy_engine.evaluate_mandate(base_mandate, compliant_transaction, caller_role="ai_agent")

    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any(v.rule_id == "TG-007" for v in res.violations)
    assert any("barred from authorizing financial transactions" in v.message for v in res.violations)


def test_api_endpoint_policy_evaluate():
    """Verify POST /api/v1/policy/evaluate endpoint works over HTTP."""
    payload = {
        "mandate": {
            "max_amount": 150.00,
            "currency": "USD",
            "allowed_conditions": ["new"],
            "require_merchant_verification": True,
            "allow_add_ons": False,
        },
        "transaction": {
            "product_name": "Keychron K2 Pro",
            "product_price": 109.99,
            "shipping_cost": 0.0,
            "tax": 8.80,
            "additional_charges": 0.0,
            "final_total": 118.79,
            "currency": "USD",
            "merchant_name": "Keychron Direct",
            "merchant_verified": True,
            "product_condition": "new",
            "add_ons": [],
        },
        "caller_role": "human_user",
    }

    response = client.post("/api/v1/policy/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True
    assert data["status"] == "APPROVED"
    assert len(data["violations"]) == 0
    assert len(data["checks"]) >= 6
    assert data["requires_human_approval"] is True


def test_api_endpoint_policy_evaluate_violation():
    """Verify POST /api/v1/policy/evaluate blocks over-budget violations."""
    payload = {
        "mandate": {
            "max_amount": 100.00,
            "currency": "USD",
            "allowed_conditions": ["new"],
            "require_merchant_verification": True,
            "allow_add_ons": False,
        },
        "transaction": {
            "product_name": "Over Budget Keyboard",
            "product_price": 120.00,
            "shipping_cost": 10.0,
            "tax": 0.0,
            "additional_charges": 0.0,
            "final_total": 130.00,
            "currency": "USD",
            "merchant_name": "Store",
            "merchant_verified": True,
            "product_condition": "new",
            "add_ons": [],
        },
        "caller_role": "human_user",
    }

    response = client.post("/api/v1/policy/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert data["status"] == "BLOCKED"
    assert len(data["violations"]) >= 1

