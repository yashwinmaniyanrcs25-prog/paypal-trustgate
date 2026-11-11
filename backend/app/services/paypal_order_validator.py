"""TrustGate Internal PayPal Orders v2 Schema Pre-Flight Guardrail.

NOTE: This is TrustGate's proprietary internal deterministic schema validation layer,
NOT an APIMatic runtime validator or package. It enforces strict compliance with
standard PayPal Orders v2 API specifications before sending payloads to PayPal Sandbox.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ISO 4217 3-letter currency codes commonly supported in PayPal Sandbox
VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "CNY",
    "SGD", "NZD", "HKD", "SEK", "DKK", "PLN", "NOK", "MXN", "BRL",
    "TWD", "THB", "ILS", "PHP"
}

ALLOWED_INTENTS = {"CAPTURE", "AUTHORIZE"}
ALLOWED_LANDING_PAGES = {"BILLING", "LOGIN", "NO_PREFERENCE"}
ALLOWED_USER_ACTIONS = {"PAY_NOW", "CONTINUE"}

# Regex for financial decimal amount string (e.g. "112.50" or "100")
DECIMAL_AMOUNT_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")


class OrderSchemaRule(BaseModel):
    """Specification of a TrustGate schema validation check."""
    rule_id: str
    target_field: str
    description: str
    passed: bool
    detail: Optional[str] = None


class OrderValidationResult(BaseModel):
    """Result of validating a PayPal payload against TrustGate's Orders v2 schema guardrails."""
    is_valid: bool
    schema_spec: str = "PayPal Orders API v2 (TrustGate Pre-Flight Guardrail)"
    action: str
    controller: str = "OrdersController"
    contract_hash: str
    rules_checked: int
    rules_passed: int
    errors: List[str] = Field(default_factory=list)
    rule_evaluations: List[OrderSchemaRule] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrustGatePayPalOrderValidator:
    """Internal pre-flight deterministic validator for PayPal Orders v2 requests."""

    def validate_order_request(self, payload: Dict[str, Any]) -> OrderValidationResult:
        """Validates an Orders v2 create-order payload before submitting to PayPal Sandbox."""
        rules: List[OrderSchemaRule] = []
        errors: List[str] = []

        # Rule 1: Root Intent
        intent = payload.get("intent")
        if intent in ALLOWED_INTENTS:
            rules.append(OrderSchemaRule(
                rule_id="TG-ORD-001",
                target_field="intent",
                description="Intent must be 'CAPTURE' or 'AUTHORIZE'",
                passed=True,
                detail=f"Intent: {intent}",
            ))
        else:
            msg = f"Invalid or missing 'intent': {intent}. Must be one of {sorted(ALLOWED_INTENTS)}."
            errors.append(msg)
            rules.append(OrderSchemaRule(
                rule_id="TG-ORD-001",
                target_field="intent",
                description="Intent must be 'CAPTURE' or 'AUTHORIZE'",
                passed=False,
                detail=msg,
            ))

        # Rule 2: Purchase Units Existence
        purchase_units = payload.get("purchase_units")
        if isinstance(purchase_units, list) and len(purchase_units) > 0:
            rules.append(OrderSchemaRule(
                rule_id="TG-ORD-002",
                target_field="purchase_units",
                description="purchase_units must be a non-empty array",
                passed=True,
                detail=f"{len(purchase_units)} purchase unit(s) found",
            ))
        else:
            msg = "Missing or empty 'purchase_units' array in OrderRequest."
            errors.append(msg)
            rules.append(OrderSchemaRule(
                rule_id="TG-ORD-002",
                target_field="purchase_units",
                description="purchase_units must be a non-empty array",
                passed=False,
                detail=msg,
            ))
            purchase_units = []

        # Rules 3, 4, 5: Amount and Currency
        for idx, pu in enumerate(purchase_units):
            prefix = f"purchase_units[{idx}]"
            amount = pu.get("amount") if isinstance(pu, dict) else None

            if not isinstance(amount, dict):
                msg = f"{prefix}.amount is missing or not an object."
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id=f"TG-ORD-003-{idx}",
                    target_field=f"{prefix}.amount",
                    description="Amount object is mandatory for each purchase unit",
                    passed=False,
                    detail=msg,
                ))
                continue

            # Currency Code validation
            currency = str(amount.get("currency_code", "")).upper()
            if currency in VALID_CURRENCIES:
                rules.append(OrderSchemaRule(
                    rule_id=f"TG-ORD-004-{idx}",
                    target_field=f"{prefix}.amount.currency_code",
                    description="currency_code must be a valid ISO-4217 3-letter currency code",
                    passed=True,
                    detail=f"Currency: {currency}",
                ))
            else:
                msg = f"{prefix}.amount.currency_code '{currency}' is not a supported ISO-4217 code."
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id=f"TG-ORD-004-{idx}",
                    target_field=f"{prefix}.amount.currency_code",
                    description="currency_code must be a valid ISO-4217 3-letter currency code",
                    passed=False,
                    detail=msg,
                ))

            # Amount Value precision validation (string with max 2 decimal places)
            val = amount.get("value")
            if isinstance(val, str) and DECIMAL_AMOUNT_PATTERN.match(val):
                try:
                    num_val = float(val)
                    if num_val > 0:
                        rules.append(OrderSchemaRule(
                            rule_id=f"TG-ORD-005-{idx}",
                            target_field=f"{prefix}.amount.value",
                            description="Amount value must be a string representation with 2 decimal precision (no floating-point rounding hazards)",
                            passed=True,
                            detail=f"Value: '{val}' ({currency})",
                        ))
                    else:
                        msg = f"{prefix}.amount.value must be greater than zero, got '{val}'."
                        errors.append(msg)
                        rules.append(OrderSchemaRule(
                            rule_id=f"TG-ORD-005-{idx}",
                            target_field=f"{prefix}.amount.value",
                            description="Amount value must be greater than zero",
                            passed=False,
                            detail=msg,
                        ))
                except ValueError:
                    msg = f"{prefix}.amount.value '{val}' is not a valid decimal number."
                    errors.append(msg)
                    rules.append(OrderSchemaRule(
                        rule_id=f"TG-ORD-005-{idx}",
                        target_field=f"{prefix}.amount.value",
                        description="Amount value must be a valid decimal string",
                        passed=False,
                        detail=msg,
                    ))
            elif isinstance(val, (int, float)):
                msg = (
                    f"{prefix}.amount.value must be serialized as a string (e.g. '{val:.2f}'), "
                    f"not a raw {type(val).__name__} to avoid precision drift."
                )
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id=f"TG-ORD-005-{idx}",
                    target_field=f"{prefix}.amount.value",
                    description="Amount value must be a string per PayPal Orders v2 specifications",
                    passed=False,
                    detail=msg,
                ))
            else:
                msg = f"{prefix}.amount.value is missing or malformed: {val}."
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id=f"TG-ORD-005-{idx}",
                    target_field=f"{prefix}.amount.value",
                    description="Amount value must be formatted as decimal string",
                    passed=False,
                    detail=msg,
                ))

        # Rule 6: Application Context Constraints
        app_ctx = payload.get("application_context")
        if app_ctx and isinstance(app_ctx, dict):
            landing = app_ctx.get("landing_page")
            if landing and landing not in ALLOWED_LANDING_PAGES:
                msg = f"application_context.landing_page '{landing}' is invalid. Allowed: {sorted(ALLOWED_LANDING_PAGES)}."
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id="TG-ORD-006",
                    target_field="application_context.landing_page",
                    description="landing_page must conform to PayPal ApplicationContext schema",
                    passed=False,
                    detail=msg,
                ))
            else:
                rules.append(OrderSchemaRule(
                    rule_id="TG-ORD-006",
                    target_field="application_context.landing_page",
                    description="landing_page conforms to PayPal ApplicationContext schema",
                    passed=True,
                    detail=f"Landing page: {landing or 'Default'}",
                ))

            user_action = app_ctx.get("user_action")
            if user_action and user_action not in ALLOWED_USER_ACTIONS:
                msg = f"application_context.user_action '{user_action}' is invalid. Allowed: {sorted(ALLOWED_USER_ACTIONS)}."
                errors.append(msg)
                rules.append(OrderSchemaRule(
                    rule_id="TG-ORD-007",
                    target_field="application_context.user_action",
                    description="user_action must conform to PayPal ApplicationContext schema",
                    passed=False,
                    detail=msg,
                ))
            else:
                rules.append(OrderSchemaRule(
                    rule_id="TG-ORD-007",
                    target_field="application_context.user_action",
                    description="user_action conforms to PayPal ApplicationContext schema",
                    passed=True,
                    detail=f"User action: {user_action or 'Default'}",
                ))

        # Compute deterministic contract hash
        canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        contract_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        is_valid = len(errors) == 0
        rules_passed = sum(1 for r in rules if r.passed)

        return OrderValidationResult(
            is_valid=is_valid,
            action="orders_create",
            contract_hash=contract_hash,
            rules_checked=len(rules),
            rules_passed=rules_passed,
            errors=errors,
            rule_evaluations=rules,
        )

    def validate_capture_response(self, response_data: Dict[str, Any]) -> OrderValidationResult:
        """Validates that a PayPal capture response conforms to Orders v2 capture schema."""
        rules: List[OrderSchemaRule] = []
        errors: List[str] = []

        order_id = response_data.get("id")
        if order_id and isinstance(order_id, str):
            rules.append(OrderSchemaRule(
                rule_id="TG-CAP-001",
                target_field="id",
                description="PayPal Order ID must be present in capture response",
                passed=True,
                detail=f"Order ID: {order_id}",
            ))
        else:
            msg = "Missing order ID in capture response."
            errors.append(msg)
            rules.append(OrderSchemaRule(
                rule_id="TG-CAP-001",
                target_field="id",
                description="PayPal Order ID must be present in capture response",
                passed=False,
                detail=msg,
            ))

        status = response_data.get("status")
        if status in ("COMPLETED", "APPROVED", "VOIDED", "PAYER_ACTION_REQUIRED"):
            rules.append(OrderSchemaRule(
                rule_id="TG-CAP-002",
                target_field="status",
                description="Status must match standard OrderStatus enum",
                passed=True,
                detail=f"Status: {status}",
            ))
        else:
            msg = f"Unexpected status '{status}' in capture response."
            errors.append(msg)
            rules.append(OrderSchemaRule(
                rule_id="TG-CAP-002",
                target_field="status",
                description="Status must match standard OrderStatus enum",
                passed=False,
                detail=msg,
            ))

        canonical_str = json.dumps(response_data, sort_keys=True, separators=(",", ":"))
        contract_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return OrderValidationResult(
            is_valid=(len(errors) == 0),
            action="orders_capture",
            contract_hash=contract_hash,
            rules_checked=len(rules),
            rules_passed=sum(1 for r in rules if r.passed),
            errors=errors,
            rule_evaluations=rules,
        )


paypal_order_validator = TrustGatePayPalOrderValidator()

