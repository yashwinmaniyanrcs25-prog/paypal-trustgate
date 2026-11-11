"""APIMatic Integration & PayPal Orders v2 Pre-Flight Validation Endpoints.

Provides pre-flight schema validation and integration diagnostics conforming
to PayPal Orders v2 API specifications and APIMatic developer workflow standards.
"""

from typing import Dict, Any
from fastapi import APIRouter
from app.services.paypal_order_validator import (
    paypal_order_validator,
    OrderValidationResult,
    VALID_CURRENCIES,
    ALLOWED_INTENTS,
)

router = APIRouter(tags=["APIMatic Sponsor (Audit)"])


@router.get("/status", summary="Get APIMatic Context Plugin & Pre-Flight Validator status")
async def get_apimatic_status() -> Dict[str, Any]:
    """Returns status and configuration of the APIMatic pre-flight validation layer."""
    return {
        "sponsor": "APIMatic",
        "status": "ACTIVE",
        "plugin": "paypal-context-plugin",
        "sdk_name": "paypal-server-sdk",
        "controller": "OrdersController",
        "schema_spec": "PayPal Orders API v2",
        "validation_mode": "PRE_FLIGHT_DETERMINISTIC",
        "guarantee": "Pre-flight validation prevents malformed payloads and precision drift before PayPal Sandbox calls.",
    }


@router.get("/spec", summary="Get APIMatic PayPal Orders specification rules")
async def get_apimatic_spec() -> Dict[str, Any]:
    """Returns specification contract rules and supported currencies."""
    return {
        "sponsor": "APIMatic",
        "supported_currencies": sorted(list(VALID_CURRENCIES)),
        "supported_intents": sorted(list(ALLOWED_INTENTS)),
        "schema_rules": [
            "TG-ORD-001: Intent validation",
            "TG-ORD-002: Non-empty purchase units",
            "TG-ORD-003: Amount field presence",
            "TG-ORD-004: ISO 4217 Currency Code",
            "TG-ORD-005: Decimal string precision",
            "TG-ORD-006: Landing page constraints",
            "TG-ORD-007: User action validation",
        ],
    }


@router.post("/validate", response_model=OrderValidationResult, summary="Validate a PayPal Orders v2 payload")
async def validate_order_payload(payload: Dict[str, Any]) -> OrderValidationResult:
    """Validates an Orders v2 payload against schema rules, currencies, and decimal string constraints."""
    return paypal_order_validator.validate_order_request(payload)


@router.post("/validate-order", response_model=OrderValidationResult, summary="Validate a PayPal Orders v2 payload (nested wrapper)")
async def validate_order_wrapped(body: Dict[str, Any]) -> OrderValidationResult:
    """Validates an Orders v2 payload that may be nested under order_payload."""
    payload = body.get("order_payload", body)
    return paypal_order_validator.validate_order_request(payload)

