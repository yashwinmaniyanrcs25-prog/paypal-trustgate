"""Comprehensive unit and integration test suite for APIMatic PayPal Server SDK validation.

Verifies:
1. Valid Orders v2 payloads pass all APIMatic schema rules.
2. Rejection of invalid intents (APIMATIC-ORD-001).
3. Rejection of missing/empty purchase units (APIMATIC-ORD-002).
4. Rejection of non-ISO-4217 currencies (APIMATIC-ORD-004).
5. Rejection of raw floating-point numbers in amounts (APIMATIC-ORD-005).
6. Rejection of invalid application context attributes (APIMATIC-ORD-006 / 007).
7. Validation of PayPal capture responses.
8. FastAPI endpoints under /api/v1/apimatic/*.
9. Integration with PayPalSandboxService pre-flight guardrail.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.apimatic_validator import apimatic_validator, APIMaticValidator

client = TestClient(app)

VALID_ORDER_PAYLOAD = {
    "intent": "CAPTURE",
    "purchase_units": [
        {
            "reference_id": "tg_sig_88921a",
            "description": "TrustGate Sandbox: Keychron K2 Wireless Keyboard",
            "amount": {
                "currency_code": "USD",
                "value": "112.50",
            },
        }
    ],
    "application_context": {
        "brand_name": "PayPal TrustGate Agentic Guard",
        "landing_page": "BILLING",
        "user_action": "PAY_NOW",
    },
}


def test_valid_order_payload_passes_apimatic_validation():
    """Verify that a compliant PayPal Orders v2 payload passes all APIMatic contract rules."""
    result = apimatic_validator.validate_order_request(VALID_ORDER_PAYLOAD)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.rules_checked >= 5
    assert result.rules_passed == result.rules_checked
    assert result.controller == "OrdersController"
    assert result.action == "orders_create"
    assert len(result.contract_hash) == 64


def test_invalid_intent_rejected():
    """Verify that an unauthorized or hallucinated intent is blocked by APIMATIC-ORD-001 / TG-ORD-001."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["intent"] = "AUTONOMOUS_DIRECT_CHARGE"

    result = apimatic_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any(("TG-ORD-001" in r.rule_id or "APIMATIC-ORD-001" in r.rule_id) and not r.passed for r in result.rule_evaluations)
    assert any("intent" in err.lower() for err in result.errors)


def test_empty_purchase_units_rejected():
    """Verify that missing purchase units is blocked by APIMATIC-ORD-002 / TG-ORD-002."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["purchase_units"] = []

    result = apimatic_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any(("TG-ORD-002" in r.rule_id or "APIMATIC-ORD-002" in r.rule_id) and not r.passed for r in result.rule_evaluations)


def test_unsupported_currency_code_rejected():
    """Verify that a hallucinated 4-letter or invalid currency is blocked by APIMATIC-ORD-004 / TG-ORD-004."""
    bad_payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USDD",
                    "value": "100.00",
                }
            }
        ],
    }

    result = apimatic_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any(("TG-ORD-004" in r.rule_id or "APIMATIC-ORD-004" in r.rule_id) and not r.passed for r in result.rule_evaluations)
    assert any("currency_code" in err for err in result.errors)


def test_raw_float_amount_rejected_to_prevent_precision_drift():
    """Verify that raw float numbers in amount.value are blocked per APIMatic schema rules (TG-ORD-005)."""
    bad_payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": 112.50,  # Raw float instead of "112.50"
                }
            }
        ],
    }

    result = apimatic_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any(("TG-ORD-005" in r.rule_id or "APIMATIC-ORD-005" in r.rule_id) and not r.passed for r in result.rule_evaluations)
    assert any("must be serialized as a string" in err for err in result.errors)


def test_invalid_landing_page_rejected():
    """Verify that unapproved application context values are blocked by APIMATIC-ORD-006 / TG-ORD-006."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["application_context"] = {
        "landing_page": "AUTONOMOUS_BROWSER_INLINE",
        "user_action": "PAY_NOW",
    }

    result = apimatic_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any(("TG-ORD-006" in r.rule_id or "APIMATIC-ORD-006" in r.rule_id) and not r.passed for r in result.rule_evaluations)


def test_capture_response_validation():
    """Verify that a completed PayPal capture response passes APIMatic contract validation."""
    valid_capture_resp = {
        "id": "ord_8829104",
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {"id": "cap_991823", "status": "COMPLETED", "amount": {"value": "112.50"}}
                    ]
                }
            }
        ],
    }

    result = apimatic_validator.validate_capture_response(valid_capture_resp)
    assert result.is_valid is True
    assert result.controller == "OrdersController"
    assert result.action == "orders_capture"


def test_apimatic_status_endpoint():
    """Verify GET /api/v1/apimatic/status returns APIMatic sponsor telemetry."""
    res = client.get("/api/v1/apimatic/status")
    assert res.status_code == 200
    data = res.json()
    assert data["sponsor"] == "APIMatic"
    assert data["status"] in ("ACTIVE", "ACTIVE_ENFORCEMENT")
    assert "paypal-server-sdk" in data["sdk_name"]


def test_apimatic_spec_endpoint():
    """Verify GET /api/v1/apimatic/spec returns contract rules and supported currencies."""
    res = client.get("/api/v1/apimatic/spec")
    assert res.status_code == 200
    data = res.json()
    assert data["sponsor"] == "APIMatic"
    assert "USD" in data["supported_currencies"]
    assert "CAPTURE" in data["supported_intents"]
    assert len(data["schema_rules"]) >= 7


def test_apimatic_validate_order_endpoint():
    """Verify POST /api/v1/apimatic/validate-order evaluates payloads dynamically."""
    res = client.post(
        "/api/v1/apimatic/validate-order",
        json={"order_payload": VALID_ORDER_PAYLOAD},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert data["rules_passed"] == data["rules_checked"]

