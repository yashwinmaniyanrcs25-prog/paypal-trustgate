"""API endpoints for Trust & Audit Layer, Transaction Lifecycle, and Telemetry."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.models.audit import (
    AuditEventRecord,
    AuditTrailResponse,
    AuditSummaryResponse,
    AuditIntegrityResponse,
    TransactionLifecycleTimeline,
    TransactionListResponse,
)
from app.db.database import (
    count_audit_events,
    get_audit_event_by_id,
    get_audit_events,
    get_audit_summary,
    get_transaction_timeline_data,
    list_persisted_transactions,
    verify_audit_integrity,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trust & Audit Layer"])


@router.get(
    "/events",
    response_model=AuditTrailResponse,
    summary="Get filtered immutable audit trail events",
)
async def list_audit_events(
    transaction_id: Optional[str] = Query(default=None, description="Optional transaction/staged proposal ID filter"),
    event_type: Optional[str] = Query(default=None, description="Optional event type filter (e.g. PROPOSAL_STAGED, PAYPAL_ORDER_CREATED)"),
    stage: Optional[str] = Query(default=None, description="Optional lifecycle stage filter (e.g. PROPOSAL, APPROVAL, PAYMENT, RECEIPT, LIFECYCLE)"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Optional event status filter"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of events to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$", description="Sort order by sequence number"),
) -> AuditTrailResponse:
    """Queries persistent SQLite audit events with optional transaction ID, stage, status, or event type filtering and pagination."""
    try:
        events = get_audit_events(
            transaction_id=transaction_id,
            event_type=event_type,
            stage=stage,
            status=status_filter,
            limit=limit,
            offset=offset,
            order_by=order,
        )
        total = count_audit_events(
            transaction_id=transaction_id,
            event_type=event_type,
            stage=stage,
            status=status_filter,
        )
        return AuditTrailResponse(
            count=len(events),
            total=total,
            offset=offset,
            limit=limit,
            events=events,
        )
    except Exception as exc:
        logger.error(f"Error fetching audit events: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query persistent audit trail: {str(exc)}",
        )


@router.get(
    "/events/{event_id}",
    response_model=AuditEventRecord,
    summary="Get details for a specific immutable audit event",
)
async def get_single_audit_event(event_id: str) -> AuditEventRecord:
    """Retrieves a single immutable audit event by its event ID."""
    try:
        event = get_audit_event_by_id(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit event '{event_id}' not found.",
            )
        return AuditEventRecord.model_validate(event)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error retrieving audit event '{event_id}': {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit event: {str(exc)}",
        )


@router.get(
    "/timeline/{transaction_id}",
    response_model=TransactionLifecycleTimeline,
    summary="Get reconstructed end-to-end transaction lifecycle timeline",
)
async def get_transaction_timeline(transaction_id: str) -> TransactionLifecycleTimeline:
    """Reconstructs the 6-stage lifecycle for a specific transaction:

    Mandate ➔ Proposal Discovery ➔ Policy Evaluation ➔ Human Approval ➔ PayPal Sandbox Order ➔ Verified Receipt.
    """
    try:
        timeline_data = get_transaction_timeline_data(transaction_id)
        if not timeline_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction '{transaction_id}' not found in persistent database.",
            )
        return TransactionLifecycleTimeline.model_validate(timeline_data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error reconstructing transaction timeline for '{transaction_id}': {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assemble transaction timeline: {str(exc)}",
        )


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    summary="List all persisted staged transactions and their current status",
)
async def list_transactions(
    limit: int = Query(default=30, ge=1, le=100, description="Max transactions to retrieve"),
) -> TransactionListResponse:
    """Returns persisted staged transactions for quick switching and timeline inspection."""
    try:
        txs = list_persisted_transactions(limit=limit)
        return TransactionListResponse(count=len(txs), transactions=txs)
    except Exception as exc:
        logger.error(f"Error listing persisted transactions: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list persisted transactions: {str(exc)}",
        )


@router.get(
    "/integrity",
    response_model=AuditIntegrityResponse,
    summary="Cryptographically verify SHA-256 hash chain and sequence continuity",
)
async def check_audit_integrity() -> AuditIntegrityResponse:
    """Validates the unbroken cryptographic SHA-256 hash chain across all stored audit events.

    Detects:
    - Tampered payloads, timestamps, or statuses
    - Gaps in sequence numbers
    - Deleted, inserted, or reordered records
    - Disconnected previous hash links
    Returns whether the chain is valid and pinpoints the exact sequence number and event ID of any defect.
    """
    try:
        integrity_result = verify_audit_integrity()
        return AuditIntegrityResponse.model_validate(integrity_result)
    except Exception as exc:
        logger.error(f"Error checking audit integrity: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify cryptographic audit integrity: {str(exc)}",
        )


@router.get(
    "/summary",
    response_model=AuditSummaryResponse,
    summary="Get database persistence telemetry and audit metrics",
)
async def get_summary() -> AuditSummaryResponse:
    """Returns telemetry of total transactions, evaluations, human approvals, and captures."""
    try:
        summary_data = get_audit_summary()
        return AuditSummaryResponse.model_validate(summary_data)
    except Exception as exc:
        logger.error(f"Error fetching audit summary: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit summary: {str(exc)}",
        )

