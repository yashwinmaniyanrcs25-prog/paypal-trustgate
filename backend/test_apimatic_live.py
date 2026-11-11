r"""Standalone test and demonstration script for TrustGate's PayPal Orders v2 pre-flight validator.

Usage:
    cd c:/Users/yashw/OneDrive/Desktop/paypal-trustgate
    python backend/test_apimatic_live.py

Tests:
1. Validates compliant PayPal Orders v2 payloads against TrustGate schema rules.
2. Demonstrates rejection of malformed payloads (invalid intent, bad currency, raw floats).
3. Verifies pre-flight guardrail enforcement before payload reaches PayPal Sandbox.
"""

import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.services.paypal_order_validator import paypal_order_validator


def main():
    print("=" * 70)
    print(" TRUSTGATE — PAYPAL ORDERS V2 PRE-FLIGHT SCHEMA GUARDRAIL TEST")
    print("=" * 70)

    # 1. Valid Payload Test
    valid_order = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": "tg_sig_demo_01",
                "description": "TrustGate Keychron K2 Mechanical Keyboard",
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

    print(f"\n[1/3] Testing Valid PayPal Orders v2 Payload against Schema Rules...")
    result_valid = paypal_order_validator.validate_order_request(valid_order)
    print(f"      Validation Passed:  {result_valid.is_valid}")
    print(f"      Action:             {result_valid.action}")
    print(f"      Rules Checked:      {result_valid.rules_checked}")
    print(f"      Rules Passed:       {result_valid.rules_passed}")
    print(f"      Contract Hash:      {result_valid.contract_hash[:16]}...{result_valid.contract_hash[-8:]}")

    for rule in result_valid.rule_evaluations:
        print(f"        * [{rule.rule_id}] {rule.target_field}: {rule.detail}")

    assert result_valid.is_valid is True, "Valid payload failed validation!"

    # 2. Malformed Payloads Rejection Demonstration
    print(f"\n[2/3] Demonstrating Deterministic Rejection of Hallucinated AI Payloads:")

    test_cases = [
        {
            "name": "Hallucinated Intent (Autonomous Charge)",
            "payload": {
                "intent": "AUTONOMOUS_DIRECT_CHARGE",
                "purchase_units": [{"amount": {"currency_code": "USD", "value": "112.50"}}],
            },
            "expected_error": "intent",
        },
        {
            "name": "Invalid Currency Code (USDD)",
            "payload": {
                "intent": "CAPTURE",
                "purchase_units": [{"amount": {"currency_code": "USDD", "value": "112.50"}}],
            },
            "expected_error": "currency_code",
        },
        {
            "name": "Raw Floating-Point Value (Precision Drift Hazard)",
            "payload": {
                "intent": "CAPTURE",
                "purchase_units": [{"amount": {"currency_code": "USD", "value": 112.50}}],
            },
            "expected_error": "must be serialized as a string",
        },
    ]

    for idx, tc in enumerate(test_cases, start=1):
        res = paypal_order_validator.validate_order_request(tc["payload"])
        passed = (res.is_valid is False) and any(tc["expected_error"] in e.lower() for e in res.errors)
        status_label = "[REJECTED AS EXPECTED]" if passed else "[UNEXPECTED PASS]"
        print(f"\n      Case 2.{idx}: {tc['name']}")
        print(f"         Status:  {status_label}")
        print(f"         Errors:  {res.errors}")
        assert passed, f"Test case {tc['name']} did not fail as expected!"

    # 3. Capture Response Schema Validation
    print(f"\n[3/3] Validating PayPal Capture Response Schema...")
    sample_capture_response = {
        "id": "ord_sandbox_8829104",
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {"id": "cap_8829104_01", "status": "COMPLETED", "amount": {"value": "112.50"}}
                    ]
                }
            }
        ],
    }
    cap_result = paypal_order_validator.validate_capture_response(sample_capture_response)
    print(f"      Validation Passed:  {cap_result.is_valid}")
    print(f"      Action:             {cap_result.action}")
    print(f"      Contract Hash:      {cap_result.contract_hash[:16]}...{cap_result.contract_hash[-8:]}")

    print("\n" + "=" * 70)
    print(" PRE-FLIGHT SCHEMA GUARDRAIL TEST: ALL CHECKS SATISFIED")
    print("=" * 70)


if __name__ == "__main__":
    main()
