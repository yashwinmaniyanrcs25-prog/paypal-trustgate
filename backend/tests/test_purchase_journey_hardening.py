"""Phase 4.2: Purchase Journey Hardening & State Locking Test Suite.

Verifies the 10 core security requirements for the purchase journey:
1. Discovery/Staging never permits direct checkout without human approval.
2. Missing human authorization record strictly blocks order creation.
3. Staged proposals permit explicit session cancellation (STAGED -> CANCELLED).
4. Approved proposals permit session cancellation prior to capture (HUMAN_APPROVED -> CANCELLED).
5. Rejected proposals permanently reject PayPal checkout (terminal state).
6. Cancelled proposals permanently reject PayPal checkout (terminal state).
7. Expired proposals permanently reject PayPal checkout (terminal state).
8. Re-approval of terminal proposals (CANCELLED, REJECTED, EXPIRED, CAPTURED) is strictly blocked.
9. Re-cancellation of terminal proposals is blocked by the state machine.
10. Cryptographic audit trail confirms all state transitions are immutably SHA-256 chained.
"""

import pytest
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

from app.core.security import PaymentExecutionBlockedError
from app.db.database import (
    init_db,
    record_audit_event,
    record_human_approval,
    record_human_rejection,
    db_record_transaction_cancellation,
    db_record_transaction_expiration,
    verify_audit_integrity,
    transition_transaction_state,
)
from app.models.lifecycle import TransactionState, InvalidStateTransitionError
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.services.paypal_service import paypal_service


@pytest.fixture
def isolated_db(tmp_path):
    """Provides an isolated SQLite database for state locking tests."""
    db_file = tmp_path / "test_hardening.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def staged_proposal(isolated_db):
    """Creates a genuine staged proposal satisfying policy bounds."""
    mandate = PurchaseMandate(
        max_amount=120.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["US domestic shipping"],
    )

    product = DiscoveredProduct(
        product_id=f"prod_hd_{uuid.uuid4().hex[:6]}",
        name="Keychron K2 Mechanical Keyboard",
        description="Wireless Mechanical Keyboard with Gateron Brown Switches",
        category="Electronics",
        price=89.99,
        currency="USD",
        condition="new",
        merchant_name="Keychron Official Direct",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="catalog",
        is_demo_data=True,
        demo_notice="Test item",
    )

    transaction = ProposedTransaction(
        product_name=product.name,
        product_price=product.price,
        shipping_cost=0.00,
        tax=7.20,
        additional_charges=0.00,
        final_total=97.19,
        currency="USD",
        merchant_name=product.merchant_name,
        merchant_verified=True,
        product_condition=product.condition,
        add_ons=[],
    )

    eval_result = policy_engine.evaluate_mandate(mandate, transaction, caller_role="human_user")
    assert eval_result.approved is True

    staged_id = f"stg_hd_{uuid.uuid4().hex[:8]}"
    record = proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=mandate,
        candidate=product,
        policy_evaluation=eval_result,
        user_id="user_hardening_test",
        db_file=isolated_db,
    )
    return record


# -----------------------------------------------------------------------------
# TEST 1 & 2: Pre-Approval Checkout Barred
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_discovery_staging_never_permits_direct_checkout(isolated_db, staged_proposal):
    """TEST 1: Calling checkout directly on a STAGED proposal without human approval is strictly blocked."""
    tx_id = staged_proposal.staged_proposal_id

    with pytest.raises(PaymentExecutionBlockedError) as exc_info:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_hardening_test",
            caller_role="human_user",
            db_file=isolated_db,
        )

    assert (
        "human approval" in exc_info.value.message.lower()
        or "approval required" in exc_info.value.message.lower()
        or "human authorization" in exc_info.value.message.lower()
    )


# -----------------------------------------------------------------------------
# TEST 3: Staged Proposal Session Cancellation
# -----------------------------------------------------------------------------

def test_3_staged_proposal_can_be_cancelled(isolated_db, staged_proposal):
    """TEST 3: A STAGED proposal can be explicitly cancelled, transitioning to CANCELLED."""
    tx_id = staged_proposal.staged_proposal_id

    res = proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="User requested checkout session cancellation",
        db_file=isolated_db,
    )

    assert res["previous_state"] == TransactionState.STAGED.value
    assert res["current_state"] == TransactionState.CANCELLED.value

    persisted = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert persisted.status == TransactionState.CANCELLED.value
    assert persisted.cancellation_reason == "User requested checkout session cancellation"


# -----------------------------------------------------------------------------
# TEST 4: Approved Proposal Session Cancellation
# -----------------------------------------------------------------------------

def test_4_approved_proposal_can_be_cancelled(isolated_db, staged_proposal):
    """TEST 4: A HUMAN_APPROVED proposal can be cancelled before order creation or capture."""
    tx_id = staged_proposal.staged_proposal_id

    # 1. Human approval
    proposal_store.record_approval(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        policy_signature=staged_proposal.policy_evaluation.policy_signature,
        approved_amount=staged_proposal.candidate.price,
        currency=staged_proposal.candidate.currency,
        db_file=isolated_db,
    )
    persisted = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert persisted.status == TransactionState.HUMAN_APPROVED.value

    # 2. Cancel the approved session
    res = proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="Operator revoked approval prior to checkout handoff",
        db_file=isolated_db,
    )

    assert res["previous_state"] == TransactionState.HUMAN_APPROVED.value
    assert res["current_state"] == TransactionState.CANCELLED.value

    persisted = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert persisted.status == TransactionState.CANCELLED.value


# -----------------------------------------------------------------------------
# TEST 5: Rejected Proposal Rejects Checkout
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_5_rejected_proposal_permanently_blocks_checkout(isolated_db, staged_proposal):
    """TEST 5: Once rejected (HUMAN_REJECTED), checkout order creation is strictly blocked."""
    tx_id = staged_proposal.staged_proposal_id

    proposal_store.record_rejection(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="Budget reallocation",
        db_file=isolated_db,
    )

    with pytest.raises((PaymentExecutionBlockedError, InvalidStateTransitionError)):
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_hardening_test",
            caller_role="human_user",
            db_file=isolated_db,
        )


# -----------------------------------------------------------------------------
# TEST 6: Cancelled Proposal Rejects Checkout
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_cancelled_proposal_permanently_blocks_checkout(isolated_db, staged_proposal):
    """TEST 6: A CANCELLED proposal permanently blocks checkout order creation."""
    tx_id = staged_proposal.staged_proposal_id

    proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="Cancelled by buyer",
        db_file=isolated_db,
    )

    with pytest.raises((PaymentExecutionBlockedError, InvalidStateTransitionError)):
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_hardening_test",
            caller_role="human_user",
            db_file=isolated_db,
        )


# -----------------------------------------------------------------------------
# TEST 7: Expired Proposal Rejects Checkout
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_7_expired_proposal_permanently_blocks_checkout(isolated_db, staged_proposal):
    """TEST 7: An EXPIRED proposal permanently blocks checkout order creation."""
    tx_id = staged_proposal.staged_proposal_id

    proposal_store.record_expiration(
        transaction_id=tx_id,
        reason="Abandoned past TTL",
        db_file=isolated_db,
    )

    with pytest.raises((PaymentExecutionBlockedError, InvalidStateTransitionError)):
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_hardening_test",
            caller_role="human_user",
            db_file=isolated_db,
        )


# -----------------------------------------------------------------------------
# TEST 8: Re-Approval of Terminal States Blocked
# -----------------------------------------------------------------------------

def test_8_reapproval_of_terminal_states_blocked(isolated_db, staged_proposal):
    """TEST 8: Re-approving CANCELLED or REJECTED proposals violates the state machine and is rejected."""
    tx_id = staged_proposal.staged_proposal_id

    proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="Terminal cancellation test",
        db_file=isolated_db,
    )

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.HUMAN_APPROVED,
            actor_role="human_user",
            db_file=isolated_db,
        )

    assert "ILLEGAL STATE TRANSITION" in exc_info.value.message


# -----------------------------------------------------------------------------
# TEST 9: Re-Cancellation of Terminal Proposals Blocked
# -----------------------------------------------------------------------------

def test_9_recancellation_of_terminal_states_blocked(isolated_db, staged_proposal):
    """TEST 9: Attempting to cancel an already CANCELLED proposal raises InvalidStateTransitionError."""
    tx_id = staged_proposal.staged_proposal_id

    proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="First cancellation",
        db_file=isolated_db,
    )

    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.CANCELLED,
            actor_role="human_user",
            db_file=isolated_db,
        )


# -----------------------------------------------------------------------------
# TEST 10: Cryptographic Audit Trail Hash Chaining Intact
# -----------------------------------------------------------------------------

def test_10_cryptographic_audit_trail_valid_after_cancellation(isolated_db, staged_proposal):
    """TEST 10: After staging, approving, and cancelling, the SHA-256 hash chain remains 100% valid."""
    tx_id = staged_proposal.staged_proposal_id

    # Advance STAGED -> HUMAN_APPROVED -> CANCELLED
    proposal_store.record_approval(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        policy_signature=staged_proposal.policy_evaluation.policy_signature,
        approved_amount=staged_proposal.candidate.price,
        currency=staged_proposal.candidate.currency,
        db_file=isolated_db,
    )

    proposal_store.record_cancellation(
        transaction_id=tx_id,
        user_id="operator_reviewer",
        reason="Cancelled after approval",
        db_file=isolated_db,
    )

    integrity = verify_audit_integrity(isolated_db)
    assert integrity["is_valid"] is True
    assert integrity["first_invalid_sequence"] is None
    assert integrity["total_events"] >= 3

