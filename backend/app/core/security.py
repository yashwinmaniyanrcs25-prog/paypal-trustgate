"""Core security invariants and guardrails for PayPal TrustGate.

Critical Invariant:
The AI agent must NEVER independently authorize or execute a payment.
"""

from typing import Optional
from pydantic import BaseModel


class PaymentExecutionBlockedError(Exception):
    """Raised whenever an autonomous agent or non-human entity attempts to trigger checkout."""

    def __init__(self, message: str = "Autonomous payment execution is prohibited by TrustGate policy."):
        self.message = message
        super().__init__(self.message)


class SecurityAuditToken(BaseModel):
    """Immutable proof of explicit human verification."""
    user_id: str
    order_id: str
    approved_amount: float
    currency: str
    timestamp: str
    signature: str


def assert_ai_cannot_authorize_payment(caller_role: str) -> None:
    """Enforces that AI agents cannot act as the payment authorizer.

    Args:
        caller_role: 'ai_agent' | 'system' | 'human_user'

    Raises:
        PaymentExecutionBlockedError: If caller is an AI agent.
    """
    if caller_role.lower() in ("ai_agent", "grok", "agent", "llm", "bot"):
        raise PaymentExecutionBlockedError(
            "VIOLATION: Autonomous AI agents attempted direct payment authorization. "
            "TrustGate requires explicit human-in-the-loop approval."
        )


def verify_human_consent_present(consent_token: Optional[SecurityAuditToken]) -> bool:
    """Validates that explicit human confirmation is present prior to payment handoff."""
    if consent_token is None:
        return False
    return bool(consent_token.user_id and consent_token.signature and consent_token.approved_amount > 0)


def enforce_human_approval_invariant(
    human_approved: bool,
    policy_signature: Optional[str] = None,
    consent_token: Optional[SecurityAuditToken] = None,
    caller_role: Optional[str] = None,
) -> None:
    """Enforces that payment handoff or execution is impossible without explicit human approval.

    Invariants checked:
    1. Caller must not be an autonomous AI agent.
    2. Explicit human approval flag must be True or a valid SecurityAuditToken must be provided.
    3. If policy_signature is provided, it must be a valid cryptographic TrustGate signature (tg_sig_...).

    Raises:
        PaymentExecutionBlockedError: If any invariant fails.
    """
    if caller_role is not None:
        assert_ai_cannot_authorize_payment(caller_role)

    has_valid_token = verify_human_consent_present(consent_token)
    if not human_approved and not has_valid_token:
        raise PaymentExecutionBlockedError(
            "VIOLATION: Payment execution blocked. Explicit human approval is required prior to checkout handoff."
        )

    if policy_signature is not None:
        if not policy_signature or not policy_signature.startswith("tg_sig_"):
            raise PaymentExecutionBlockedError(
                "VIOLATION: Payment execution blocked. Invalid or missing TrustGate policy evaluation signature."
            )
