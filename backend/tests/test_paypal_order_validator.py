"""Unit test suite for TrustGate's internal PayPal Orders v2 pre-flight schema validator.

Verifies:
1. Valid Orders v2 payloads pass all schema rules.
2. Rejection of invalid intents (TG-ORD-001).
3. Rejection of missing/empty purchase units (TG-ORD-002).
4. Rejection of non-ISO-4217 currencies (TG-ORD-004).
5. Rejection of raw floating-point numbers in amounts (TG-ORD-005).
6. Rejection of invalid application context attributes (TG-ORD-006 / 007).
7. Validation of PayPal capture responses (TG-CAP-001 / 002).
"""

import pytest
from app.services.paypal_order_validator import paypal_order_validator
from app.main import app
from fastapi.testclient import TestClient

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


def test_valid_order_payload_passes_validation():
    """Verify that a compliant PayPal Orders v2 payload passes all schema rules."""
    result = paypal_order_validator.validate_order_request(VALID_ORDER_PAYLOAD)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.rules_checked >= 5
    assert result.rules_passed == result.rules_checked
    assert result.action == "orders_create"
    assert len(result.contract_hash) == 64


def test_invalid_intent_rejected():
    """Verify that an unauthorized intent is blocked by TG-ORD-001."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["intent"] = "AUTONOMOUS_DIRECT_CHARGE"

    result = paypal_order_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any("TG-ORD-001" in r.rule_id and not r.passed for r in result.rule_evaluations)
    assert any("intent" in err.lower() for err in result.errors)


def test_empty_purchase_units_rejected():
    """Verify that missing purchase units is blocked by TG-ORD-002."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["purchase_units"] = []

    result = paypal_order_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any("TG-ORD-002" in r.rule_id and not r.passed for r in result.rule_evaluations)


def test_unsupported_currency_code_rejected():
    """Verify that a non-standard 4-letter or invalid currency is blocked by TG-ORD-004."""
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

    result = paypal_order_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any("TG-ORD-004" in r.rule_id and not r.passed for r in result.rule_evaluations)
    assert any("currency_code" in err for err in result.errors)


def test_raw_float_amount_rejected_to_prevent_precision_drift():
    """Verify that raw float numbers in amount.value are blocked per schema rules."""
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

    result = paypal_order_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any("TG-ORD-005" in r.rule_id and not r.passed for r in result.rule_evaluations)
    assert any("must be serialized as a string" in err for err in result.errors)


def test_invalid_landing_page_rejected():
    """Verify that unapproved application context values are blocked by TG-ORD-006."""
    bad_payload = dict(VALID_ORDER_PAYLOAD)
    bad_payload["application_context"] = {
        "landing_page": "AUTONOMOUS_BROWSER_INLINE",
        "user_action": "PAY_NOW",
    }

    result = paypal_order_validator.validate_order_request(bad_payload)
    assert result.is_valid is False
    assert any("TG-ORD-006" in r.rule_id and not r.passed for r in result.rule_evaluations)


def test_capture_response_validation():
    """Verify that a completed PayPal capture response passes schema validation."""
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

    result = paypal_order_validator.validate_capture_response(valid_capture_resp)
    assert result.is_valid is True
    assert result.action == "orders_capture"


def test_order_validation_result_has_apimatic_controller():
    """Verify that OrderValidationResult includes controller attribute for APIMatic SDK conformance."""
    result = paypal_order_validator.validate_order_request(VALID_ORDER_PAYLOAD)
    assert hasattr(result, "controller")
    assert result.controller == "OrdersController"


def test_apimatic_api_endpoints():
    """Verify APIMatic status and validate API endpoints return HTTP 200 without 404."""
    # 1. Status endpoint
    status_res = client.get("/api/v1/apimatic/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] == "ACTIVE"
    assert status_data["controller"] == "OrdersController"

    # 2. Validate endpoint
    val_res = client.post("/api/v1/apimatic/validate", json=VALID_ORDER_PAYLOAD)
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is True
    assert val_data["controller"] == "OrdersController"


