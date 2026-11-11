"""Centralized Transaction Lifecycle State Machine Models for PayPal TrustGate.

Defines:
- TransactionState enum (explicit discrete states)
- Permitted state transitions matrix
- Transition request and response schemas
- State transition validation logic
"""

from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pydantic import BaseModel, Field, model_validator


class TransactionState(str, Enum):
    """Explicit, discrete lifecycle states for a TrustGate purchasing transaction."""

    # 1. Staged & Discovered: Candidate verified against policy, awaiting human review
    STAGED = "STAGED"

    # 2. Human Approval Granted: Explicit, authenticated human authorization
    HUMAN_APPROVED = "HUMAN_APPROVED"

    # 3. Human Rejection: Explicit human refusal (Terminal)
    HUMAN_REJECTED = "HUMAN_REJECTED"

    # 4. PayPal Sandbox Order Created: Server-side order successfully created
    ORDER_CREATED = "ORDER_CREATED"

    # 5. Order Creation Failed: Network timeout or PayPal API error (Recoverable)
    ORDER_CREATION_FAILED = "ORDER_CREATION_FAILED"

    # 6. Capture Completed: Verified PayPal capture response received (Terminal success)
    CAPTURED = "CAPTURED"

    # 7. Capture Failed: PayPal declined or gateway error (Recoverable / Inspectable)
    CAPTURE_FAILED = "CAPTURE_FAILED"

    # 8. Cancelled: User explicitly abandoned or cancelled checkout session (Terminal)
    CANCELLED = "CANCELLED"

    # 9. Expired: Session timed out without action (Terminal)
    EXPIRED = "EXPIRED"


# Permitted State Transition Rules Matrix
PERMITTED_TRANSITIONS: Dict[TransactionState, Set[TransactionState]] = {
    TransactionState.STAGED: {
        TransactionState.HUMAN_APPROVED,
        TransactionState.HUMAN_REJECTED,
        TransactionState.CANCELLED,
        TransactionState.EXPIRED,
    },
    TransactionState.HUMAN_APPROVED: {
        TransactionState.ORDER_CREATED,
        TransactionState.ORDER_CREATION_FAILED,
        TransactionState.CANCELLED,
        TransactionState.EXPIRED,
    },
    TransactionState.ORDER_CREATION_FAILED: {
        TransactionState.ORDER_CREATED,  # Retry order creation
        TransactionState.CANCELLED,
        TransactionState.EXPIRED,
    },
    TransactionState.ORDER_CREATED: {
        TransactionState.CAPTURED,
        TransactionState.CAPTURE_FAILED,
        TransactionState.CANCELLED,
        TransactionState.EXPIRED,
    },
    TransactionState.CAPTURE_FAILED: {
        TransactionState.CAPTURED,  # Safe retry if issue resolved
        TransactionState.CANCELLED,
    },
    # Terminal States: No forward transitions allowed
    TransactionState.CAPTURED: set(),
    TransactionState.HUMAN_REJECTED: set(),
    TransactionState.CANCELLED: set(),
    TransactionState.EXPIRED: set(),
}


def is_transition_permitted(current_state: TransactionState, target_state: TransactionState) -> bool:
    """Evaluates whether transitioning from current_state to target_state is permitted."""
    allowed_targets = PERMITTED_TRANSITIONS.get(current_state, set())
    return target_state in allowed_targets


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""

    def __init__(self, current_state: TransactionState, target_state: TransactionState, transaction_id: str):
        self.current_state = current_state
        self.target_state = target_state
        self.from_state = current_state
        self.to_state = target_state
        self.transaction_id = transaction_id
        self.message = (
            f"ILLEGAL STATE TRANSITION: Cannot transition transaction '{transaction_id}' "
            f"from '{current_state.value}' to '{target_state.value}'. "
            f"Permitted next states: {[s.value for s in PERMITTED_TRANSITIONS.get(current_state, set())]}."
        )
        super().__init__(self.message)


class HumanApprovalRequest(BaseModel):
    """Payload to explicitly approve a staged candidate for PayPal Sandbox checkout."""
    user_id: Optional[str] = Field(default="user_operator", description="Authenticated user ID granting approval")
    operator_id: Optional[str] = Field(default=None, description="Optional operator ID alias")
    approval_method: Optional[str] = Field(default="ui_click", description="Approval method")
    security_pin: Optional[str] = Field(default=None, description="Security PIN if required")
    notes: Optional[str] = Field(default=None, description="Optional operator notes")
    consent_token: Optional[str] = Field(default=None, description="Optional client-provided confirmation token")

    @model_validator(mode="before")
    @classmethod
    def resolve_user_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("user_id") and data.get("operator_id"):
                data["user_id"] = data["operator_id"]
        return data


class HumanRejectionRequest(BaseModel):
    """Payload to explicitly reject a staged candidate."""
    user_id: str = Field(default="user_operator", description="Authenticated user ID rejecting proposal")
    reason: str = Field(..., min_length=3, max_length=500, description="Explicit human rejection rationale")


class TransactionCancelRequest(BaseModel):
    """Payload to explicitly cancel an active checkout session."""
    user_id: str = Field(default="user_operator", description="User ID requesting cancellation")
    reason: Optional[str] = Field(default="User cancelled checkout session", description="Cancellation reason")


class StateTransitionResponse(BaseModel):
    """Result of a successful state machine transition."""

    transaction_id: str
    previous_state: TransactionState
    current_state: TransactionState
    updated_at: str
    audit_event_hash: Optional[str] = None
    message: str

    # Compatibility fields for approval API consumers
    status: Optional[TransactionState] = None
    human_approval_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_compatibility_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("status") is None and "current_state" in data:
                data["status"] = data["current_state"]
            if data.get("human_approval_id") is None and "approval_id" in data:
                data["human_approval_id"] = data["approval_id"]
        return data

    @model_validator(mode="after")
    def sync_compatibility_fields(self) -> "StateTransitionResponse":
        if self.status is None:
            self.status = self.current_state
        return self
