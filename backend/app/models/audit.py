"""Pydantic schemas for the Trust & Audit Layer.

Provides typed models for:
- Immutable audit event records
- Transaction lifecycle timeline reconstruction (Mandate ➔ Proposal ➔ Policy ➔ Approval ➔ Sandbox Order ➔ Verified Receipt)
- Audit summary telemetry and transaction lists
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AuditEventRecord(BaseModel):
    """An immutable audit trail entry with SHA-256 hash chaining."""
    sequence_number: Optional[int] = None
    event_id: str
    transaction_id: str
    event_type: str
    stage: str
    status: str
    linked_mandate_id: Optional[str] = None
    linked_proposal_id: Optional[str] = None
    linked_evaluation_id: Optional[str] = None
    linked_paypal_order_id: Optional[str] = None
    linked_capture_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    actor_role: str = "system"
    timestamp: str
    prev_hash: Optional[str] = None
    event_hash: Optional[str] = None


class HumanApprovalRecord(BaseModel):
    """Record of explicit human authorization."""
    approval_id: str
    transaction_id: str
    user_id: str
    policy_signature: str
    approved_amount: float
    currency: str
    action: str
    actor_role: str = "human_user"
    consent_token: Optional[str] = None
    created_at: str


class TransactionTimelineStage(BaseModel):
    """A distinct milestone in the transaction lifecycle."""
    stage_name: str
    stage_key: str  # mandate | proposal | policy | approval | order | receipt
    status: str     # COMPLETED | PENDING | BLOCKED | NOT_STARTED
    timestamp: Optional[str] = None
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)


class TransactionLifecycleTimeline(BaseModel):
    """Reconstructed end-to-end lifecycle for a transaction."""
    transaction_id: str
    current_status: str
    created_at: str
    updated_at: str
    mandate_summary: Optional[Dict[str, Any]] = None
    candidate_summary: Optional[Dict[str, Any]] = None
    policy_evaluation_summary: Optional[Dict[str, Any]] = None
    human_approval_summary: Optional[Dict[str, Any]] = None
    paypal_order_summary: Optional[Dict[str, Any]] = None
    capture_receipt_summary: Optional[Dict[str, Any]] = None
    stages: List[TransactionTimelineStage]
    events: List[AuditEventRecord]


class AuditTrailResponse(BaseModel):
    """Response containing filtered list of immutable audit events."""
    count: int
    total: Optional[int] = None
    offset: Optional[int] = 0
    limit: Optional[int] = 50
    events: List[AuditEventRecord]


class AuditSummaryResponse(BaseModel):
    """Telemetry metrics from the persistent SQLite database."""
    storage_engine: str
    db_path: str
    persisted: bool
    audit_chain_verified: Optional[bool] = None
    genesis_hash: Optional[str] = None
    last_event_hash: Optional[str] = None
    total_audit_events: int
    total_mandates: int
    total_staged_proposals: int
    total_paypal_captures: int
    total_evaluations: int
    approved_evaluations: int
    blocked_evaluations: int
    total_human_approvals: int


class AuditIntegrityResponse(BaseModel):
    """Cryptographic verification status of the entire audit trail."""
    is_valid: bool
    total_events: int
    genesis_hash: str
    last_event_hash: Optional[str] = None
    first_invalid_sequence: Optional[int] = None
    first_invalid_event_id: Optional[str] = None
    failure_reason: Optional[str] = None
    verified_at: str
    tamper_evident_guarantee: str



class TransactionSummaryItem(BaseModel):
    """Compact summary of a persisted transaction."""
    transaction_id: str
    product_name: str
    amount: float
    currency: str
    merchant_name: str
    policy_approved: bool
    status: str
    created_at: str
    paypal_order_id: Optional[str] = None
    capture_id: Optional[str] = None


class TransactionListResponse(BaseModel):
    """List of persisted transactions."""
    count: int
    transactions: List[TransactionSummaryItem]

