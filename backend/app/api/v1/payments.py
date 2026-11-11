"""API endpoints for PayPal Sandbox Checkout with Explicit Human Approval."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status

from app.core.security import PaymentExecutionBlockedError
from app.models.lifecycle import (
    HumanApprovalRequest,
    HumanRejectionRequest,
    TransactionCancelRequest,
    StateTransitionResponse,
    InvalidStateTransitionError,
)
from app.models.payment import (
    PaymentConfigResponse,
    CreateOrderRequest,
    CreateOrderResponse,
    CaptureOrderRequest,
    CaptureOrderResponse,
    PaymentStatusResponse,
)
from app.services.paypal_service import paypal_service
from app.services.proposal_store import proposal_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["PayPal Sandbox Payments"])


@router.get(
    "/config",
    response_model=PaymentConfigResponse,
    summary="Get PayPal Sandbox configuration and public client ID",
)
async def get_payment_config() -> PaymentConfigResponse:
    """Returns safe PayPal Sandbox configuration.

    SECURITY INVARIANT:
    Returns ONLY the public client ID when configured. Never reveals the client secret.
    """
    return paypal_service.get_config()


@router.get(
    "/verify-auth",
    summary="Test PayPal Sandbox OAuth authentication without exposing credentials",
)
async def verify_sandbox_auth():
    """Validates PayPal Sandbox client credentials against official Sandbox OAuth endpoint.

    Strictly restricted to Sandbox. Does not create or capture orders. Never exposes secrets.
    """
    return await paypal_service.verify_sandbox_auth()


@router.post(
    "/create-order",
    response_model=CreateOrderResponse,
    summary="Create a PayPal Sandbox order from a trusted staged proposal",
)
async def create_order(payload: CreateOrderRequest) -> CreateOrderResponse:
    """Creates a PayPal Sandbox order strictly derived from trusted server-side state.

    SECURITY INVARIANTS:
    1. Derives price, currency, and parameters from stored candidate; ignores client overrides.
    2. Deterministically revalidates candidate against purchase mandate before order creation.
    3. Storing internal proposal linkage.
    """
    if not paypal_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "PayPal Sandbox is not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in backend/.env to activate the Sandbox checkout."
            ),
        )

    try:
        response = await paypal_service.create_sandbox_order(
            staged_proposal_id=payload.staged_proposal_id,
            user_id=payload.user_id or "user_demo",
            caller_role="human_user",
        )
        return response
    except PaymentExecutionBlockedError as block_err:
        logger.warning(f"Payment order creation blocked by policy: {block_err.message}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=block_err.message,
        )
    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Order creation rejected by state machine: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Order creation validation error: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except TimeoutError as to_err:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(to_err),
        )
    except Exception as exc:
        logger.error(f"Unexpected error creating PayPal order: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PayPal order creation failed: {str(exc)}",
        )


@router.post(
    "/capture-order",
    response_model=CaptureOrderResponse,
    summary="Capture an approved PayPal Sandbox order",
)
async def capture_order(payload: CaptureOrderRequest) -> CaptureOrderResponse:
    """Captures a PayPal Sandbox order only after explicit buyer approval in Sandbox.

    SECURITY INVARIANTS:
    1. Captures ONLY orders created by this TrustGate backend and linked to an approved proposal.
    2. Server-side verification of completed PayPal capture response.
    3. Idempotent: repeated capture calls safely return existing verified receipt.
    """
    if not paypal_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayPal Sandbox is not configured. Cannot capture unconfigured order.",
        )

    try:
        response = await paypal_service.capture_sandbox_order(
            order_id=payload.order_id,
            user_id=payload.user_id or "user_demo",
            caller_role="human_user",
        )
        return response
    except PaymentExecutionBlockedError as block_err:
        logger.warning(f"Capture blocked: {block_err.message}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=block_err.message,
        )
    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Capture rejected by state machine: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Capture validation error: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except TimeoutError as to_err:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(to_err),
        )
    except Exception as exc:
        logger.error(f"Unexpected error capturing PayPal order: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PayPal order capture failed: {str(exc)}",
        )


@router.get(
    "/orders/{order_id}",
    response_model=PaymentStatusResponse,
    summary="Get status of a PayPal Sandbox order",
)
async def get_order_status(order_id: str) -> PaymentStatusResponse:
    """Returns safe status for a PayPal Sandbox order."""
    return await paypal_service.get_order_status(order_id)


# -----------------------------------------------------------------------------
# Explicit Transaction State Machine Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/proposals/{transaction_id}/approve",
    response_model=StateTransitionResponse,
    summary="Explicit human authorization for a staged proposal",
)
async def approve_proposal(
    transaction_id: str,
    payload: Optional[HumanApprovalRequest] = None,
) -> StateTransitionResponse:
    """Explicitly authorizes a staged proposal as a human operator.

    SECURITY INVARIANT:
    Order creation is forbidden before this explicit authorization is persisted.
    Transitions state from STAGED -> HUMAN_APPROVED and records audit event.
    """
    try:
        # Retrieve the original staged proposal.
        record = proposal_store.get_staged_proposal(transaction_id)

        if record is None:
            raise ValueError(f"Staged proposal not found: {transaction_id}")

        acting_user = (
            (payload.operator_id or payload.user_id) if payload else None
        ) or record.user_id or "user_operator"
        consent_token = payload.consent_token if payload else None

        # Use the original policy evaluation and candidate data.
        res = proposal_store.record_approval(
            transaction_id=transaction_id,
            user_id=acting_user,
            policy_signature=record.policy_evaluation.policy_signature,
            approved_amount=record.candidate.price,
            currency=record.candidate.currency,
            consent_token=consent_token,
        )

        res["status"] = res.get("current_state")
        res["human_approval_id"] = res.get("approval_id")

        return StateTransitionResponse(**res)

    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Approve proposal rejected: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Approve proposal failed: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error approving proposal: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record human approval: {str(exc)}",
        )


@router.post(
    "/proposals/{transaction_id}/reject",
    response_model=StateTransitionResponse,
    summary="Explicit human rejection of a staged proposal",
)
async def reject_proposal(
    transaction_id: str,
    payload: Optional[HumanRejectionRequest] = None,
) -> StateTransitionResponse:
    """Explicitly rejects a staged proposal.

    Terminal state: prevents any subsequent order creation or capture.
    Transitions state from STAGED -> HUMAN_REJECTED and records audit event.
    """
    user_id = payload.user_id if payload else "user_demo"
    reason = payload.reason if payload else "Rejected by human operator"

    try:
        res = proposal_store.record_rejection(
            transaction_id=transaction_id,
            user_id=user_id,
            reason=reason,
        )
        res["status"] = res.get("current_state")
        res["human_approval_id"] = res.get("approval_id")
        return StateTransitionResponse(**res)
    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Reject proposal rejected: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Reject proposal failed: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error rejecting proposal: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record rejection: {str(exc)}",
        )


@router.post(
    "/proposals/{transaction_id}/cancel",
    response_model=StateTransitionResponse,
    summary="Cancel an active checkout session",
)
async def cancel_proposal(
    transaction_id: str,
    payload: Optional[TransactionCancelRequest] = None,
) -> StateTransitionResponse:
    """Explicitly cancels an active checkout session (from STAGED, HUMAN_APPROVED, ORDER_CREATED, or failure states).

    Terminal state: prevents any further state changes.
    """
    user_id = payload.user_id if payload else "user_demo"
    reason = payload.reason if payload else "Cancelled by user"

    try:
        res = proposal_store.record_cancellation(
            transaction_id=transaction_id,
            user_id=user_id,
            reason=reason,
        )
        return StateTransitionResponse(**res)
    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Cancel transaction rejected: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Cancel transaction failed: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error cancelling transaction: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel transaction: {str(exc)}",
        )


@router.post(
    "/proposals/{transaction_id}/expire",
    response_model=StateTransitionResponse,
    summary="Expire an abandoned checkout session past its TTL",
)
async def expire_proposal(
    transaction_id: str,
    reason: Optional[str] = "Abandoned session expired past TTL",
) -> StateTransitionResponse:
    """Marks an abandoned checkout session as expired.

    Can be triggered by TTL monitoring or cleanup jobs.
    """
    try:
        res = proposal_store.record_expiration(
            transaction_id=transaction_id,
            reason=reason,
        )
        return StateTransitionResponse(**res)
    except InvalidStateTransitionError as trans_err:
        logger.warning(f"Expire transaction rejected: {trans_err.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=trans_err.message,
        )
    except ValueError as val_err:
        logger.warning(f"Expire transaction failed: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error expiring transaction: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to expire transaction: {str(exc)}",
        )


@router.get(
    "/proposals/{transaction_id}/state",
    summary="Get explicit transaction state and details",
)
async def get_proposal_state(transaction_id: str):
    """Returns the current state machine status and reasons for a transaction."""
    record = proposal_store.get_staged_proposal(transaction_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{transaction_id}' not found.",
        )
    return {
        "transaction_id": record.staged_proposal_id,
        "status": record.status,
        "paypal_order_id": record.paypal_order_id,
        "captured": record.captured,
        "capture_id": record.capture_id,
        "rejection_reason": record.rejection_reason,
        "cancellation_reason": record.cancellation_reason,
        "expires_at": record.expires_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
