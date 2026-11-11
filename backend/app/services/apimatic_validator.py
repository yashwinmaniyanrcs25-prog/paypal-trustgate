"""Redirect for backward compatibility.

TrustGate uses internal pre-flight validation in app.services.paypal_order_validator.
"""

from app.services.paypal_order_validator import (
    paypal_order_validator,
    paypal_order_validator as apimatic_validator,
    OrderValidationResult,
    OrderValidationResult as APIMaticValidationResult,
    TrustGatePayPalOrderValidator,
    TrustGatePayPalOrderValidator as APIMaticValidator,
)

__all__ = [
    "paypal_order_validator",
    "apimatic_validator",
    "OrderValidationResult",
    "APIMaticValidationResult",
    "TrustGatePayPalOrderValidator",
    "APIMaticValidator",
]
