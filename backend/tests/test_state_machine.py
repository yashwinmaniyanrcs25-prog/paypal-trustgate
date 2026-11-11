"""Targeted test suite for TrustGate Stage 2: Strict Transaction Lifecycle State Machine."""

import pytest
import sqlite3
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.lifecycle import (
    TransactionState,
    PERMITTED_TRANSITIONS,
    is_transition_permitted,
    InvalidStateTransitionError,
)
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.db.database import (
    init_db,
    get_db_connection,
    verify_audit_integrity,
    record_human_approval,
    record_human_rejection,
    record_transaction_cancellation,
    record_transaction_expiration,
    transition_transaction_state,
)

client = TestClient(app)


@pytest.fixture
def test_db_path(tmp_path):
    """Provides an isolated SQLite database file with initialized schema and append triggers."""
    db_file = tmp_path / "test_lifecycle.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def staged_tx(test_db_path):
    """Creates and stages a valid purchase candidate in the isolated database."""
    mandate = PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )
    candidate = DiscoveredProduct(
        product_id="cand_state_machine_01",
        name="Keychron K2 Mechanical Keyboard",
        description="Wireless ergonomic keyboard",
        category="Keyboards",
        price=112.50,
        currency="USD",
        condition="new",
        merchant_name="Official Keychron Store",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="local_demo_fixture",
        is_demo_data=True,
    )
    tx = ProposedTransaction(
        product_name=candidate.name,
        product_description=candidate.description,
        product_price=candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=candidate.price,
        currency=candidate.currency,
        merchant_name=candidate.merchant_name,
        merchant_verified=candidate.merchant_verified,
        product_condition=candidate.condition,
        add_ons=[],
    )
    evaluation = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
    tx_id = f"tx_stage2_{uuid.uuid4().hex[:8]}"

    rec = proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
        user_id="user_test",
        db_file=test_db_path,
    )
    return rec


# -----------------------------------------------------------------------------
# 1. Permitted State Transitions Matrix Unit Tests
# -----------------------------------------------------------------------------

def test_transition_matrix_permitted_paths():
    """Verifies that all standard lifecycle transitions are permitted by the matrix."""
    assert is_transition_permitted(TransactionState.STAGED, TransactionState.HUMAN_APPROVED)
    assert is_transition_permitted(TransactionState.STAGED, TransactionState.HUMAN_REJECTED)
    assert is_transition_permitted(TransactionState.STAGED, TransactionState.CANCELLED)
    assert is_transition_permitted(TransactionState.STAGED, TransactionState.EXPIRED)

    assert is_transition_permitted(TransactionState.HUMAN_APPROVED, TransactionState.ORDER_CREATED)
    assert is_transition_permitted(TransactionState.HUMAN_APPROVED, TransactionState.ORDER_CREATION_FAILED)
    assert is_transition_permitted(TransactionState.HUMAN_APPROVED, TransactionState.CANCELLED)

    assert is_transition_permitted(TransactionState.ORDER_CREATED, TransactionState.CAPTURED)
    assert is_transition_permitted(TransactionState.ORDER_CREATED, TransactionState.CAPTURE_FAILED)
    assert is_transition_permitted(TransactionState.ORDER_CREATED, TransactionState.CANCELLED)
    assert is_transition_permitted(TransactionState.ORDER_CREATED, TransactionState.EXPIRED)

    # Recovery transitions
    assert is_transition_permitted(TransactionState.ORDER_CREATION_FAILED, TransactionState.ORDER_CREATED)
    assert is_transition_permitted(TransactionState.ORDER_CREATION_FAILED, TransactionState.CANCELLED)
    assert is_transition_permitted(TransactionState.CAPTURE_FAILED, TransactionState.CAPTURED)
    assert is_transition_permitted(TransactionState.CAPTURE_FAILED, TransactionState.CANCELLED)


def test_transition_matrix_forbidden_paths():
    """Verifies that illegal transitions are strictly rejected by the matrix."""
    # Cannot jump from STAGED directly to ORDER_CREATED or CAPTURED
    assert not is_transition_permitted(TransactionState.STAGED, TransactionState.ORDER_CREATED)
    assert not is_transition_permitted(TransactionState.STAGED, TransactionState.CAPTURED)

    # Terminal states cannot transition to anything
    for target in TransactionState:
        assert not is_transition_permitted(TransactionState.CAPTURED, target)
        assert not is_transition_permitted(TransactionState.HUMAN_REJECTED, target)
        assert not is_transition_permitted(TransactionState.CANCELLED, target)
        assert not is_transition_permitted(TransactionState.EXPIRED, target)


# -----------------------------------------------------------------------------
# 2. Database State Transition & Audit Trail Tests
# -----------------------------------------------------------------------------

def test_happy_path_lifecycle(test_db_path, staged_tx):
    """Tests full progression: STAGED -> HUMAN_APPROVED -> ORDER_CREATED -> CAPTURED."""
    tx_id = staged_tx.staged_proposal_id

    # 1. STAGED -> HUMAN_APPROVED
    appr_res = record_human_approval(
        transaction_id=tx_id,
        user_id="user_test",
        policy_signature="sig_mock_123",
        approved_amount=112.50,
        currency="USD",
        db_file=test_db_path,
    )
    assert appr_res["current_state"] == TransactionState.HUMAN_APPROVED

    # 2. HUMAN_APPROVED -> ORDER_CREATED
    order_res = transition_transaction_state(
        transaction_id=tx_id,
        target_state=TransactionState.ORDER_CREATED,
        actor_role="system",
        paypal_order_id="PAYPAL_ORD_112233",
        db_file=test_db_path,
    )
    assert order_res["current_state"] == TransactionState.ORDER_CREATED

    # 3. ORDER_CREATED -> CAPTURED
    cap_res = transition_transaction_state(
        transaction_id=tx_id,
        target_state=TransactionState.CAPTURED,
        actor_role="system",
        capture_id="PAYPAL_CAP_445566",
        db_file=test_db_path,
    )
    assert cap_res["current_state"] == TransactionState.CAPTURED

    # Verify audit chain remains unbroken
    integrity = verify_audit_integrity(test_db_path)
    assert integrity["is_valid"] is True
    # At least 4 events: STAGED + APPROVED + ORDER_CREATED + CAPTURED
    assert integrity["total_events"] >= 4


def test_illegal_transition_rejection(test_db_path, staged_tx):
    """Attempting illegal transition raises InvalidStateTransitionError and rolls back atomically."""
    tx_id = staged_tx.staged_proposal_id

    # STAGED -> CAPTURED is illegal
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.CAPTURED,
            db_file=test_db_path,
        )

    assert exc_info.value.from_state == TransactionState.STAGED
    assert exc_info.value.to_state == TransactionState.CAPTURED

    # Database record must still be STAGED
    rec = proposal_store.get_staged_proposal(tx_id, db_file=test_db_path)
    assert rec.status == TransactionState.STAGED.value

    # Audit chain must remain unbroken
    integrity = verify_audit_integrity(test_db_path)
    assert integrity["is_valid"] is True


def test_human_rejection_terminal_state(test_db_path, staged_tx):
    """STAGED -> HUMAN_REJECTED sets rejection reason and prevents further transitions."""
    tx_id = staged_tx.staged_proposal_id

    rej_res = record_human_rejection(
        transaction_id=tx_id,
        user_id="user_test",
        reason="Price is acceptable but wait for holiday discount",
        db_file=test_db_path,
    )
    assert rej_res["current_state"] == TransactionState.HUMAN_REJECTED

    # Attempting to approve or create order after rejection must fail
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.ORDER_CREATED,
            db_file=test_db_path,
        )


def test_cancellation_flow(test_db_path, staged_tx):
    """Active checkout can be cancelled from HUMAN_APPROVED."""
    tx_id = staged_tx.staged_proposal_id

    record_human_approval(
        transaction_id=tx_id,
        user_id="user_test",
        policy_signature="sig_mock",
        approved_amount=112.50,
        currency="USD",
        db_file=test_db_path,
    )

    canc_res = record_transaction_cancellation(
        transaction_id=tx_id,
        user_id="user_test",
        reason="User decided not to complete checkout",
        db_file=test_db_path,
    )
    assert canc_res["current_state"] == TransactionState.CANCELLED

    # Cancelled is terminal
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.ORDER_CREATED,
            db_file=test_db_path,
        )


def test_expiration_flow(test_db_path, staged_tx):
    """Abandoned transaction can be expired past TTL."""
    tx_id = staged_tx.staged_proposal_id

    exp_res = record_transaction_expiration(
        transaction_id=tx_id,
        reason="Session TTL expired after 30 minutes of inactivity",
        db_file=test_db_path,
    )
    assert exp_res["current_state"] == TransactionState.EXPIRED

    # Expired is terminal
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.ORDER_CREATED,
            db_file=test_db_path,
        )


def test_order_creation_failure_and_recovery(test_db_path, staged_tx):
    """HUMAN_APPROVED -> ORDER_CREATION_FAILED -> ORDER_CREATED (successful retry)."""
    tx_id = staged_tx.staged_proposal_id

    record_human_approval(
        transaction_id=tx_id,
        user_id="user_test",
        policy_signature="sig_mock",
        approved_amount=112.50,
        currency="USD",
        db_file=test_db_path,
    )

    # 1. Order creation fails (e.g. PayPal 503 or network timeout)
    proposal_store.mark_order_creation_failed(
        tx_id,
        reason="PayPal Sandbox API 503 Service Unavailable",
        db_file=test_db_path,
    )
    rec = proposal_store.get_staged_proposal(tx_id, db_file=test_db_path)
    assert rec.status == TransactionState.ORDER_CREATION_FAILED.value

    # 2. Retry succeeds: ORDER_CREATION_FAILED -> ORDER_CREATED
    proposal_store.link_paypal_order(
        tx_id,
        "SANDBOX_ORD_RETRY_123",
        db_file=test_db_path,
    )
    rec_after = proposal_store.get_staged_proposal(tx_id, db_file=test_db_path)
    assert rec_after.status == TransactionState.ORDER_CREATED.value
    assert rec_after.paypal_order_id == "SANDBOX_ORD_RETRY_123"


def test_capture_failure_and_recovery(test_db_path, staged_tx):
    """ORDER_CREATED -> CAPTURE_FAILED -> CAPTURED (successful retry)."""
    tx_id = staged_tx.staged_proposal_id
    order_id = "SANDBOX_ORD_CAP_FAIL_TEST"

    record_human_approval(
        transaction_id=tx_id,
        user_id="user_test",
        policy_signature="sig_mock",
        approved_amount=112.50,
        currency="USD",
        db_file=test_db_path,
    )
    proposal_store.link_paypal_order(tx_id, order_id, db_file=test_db_path)

    # 1. Capture fails
    proposal_store.mark_capture_failed(
        tx_id,
        reason="Buyer session not yet authorized in Sandbox popup",
        db_file=test_db_path,
    )
    rec = proposal_store.get_staged_proposal(tx_id, db_file=test_db_path)
    assert rec.status == TransactionState.CAPTURE_FAILED.value

    # 2. Retry succeeds: CAPTURE_FAILED -> CAPTURED
    proposal_store.mark_captured(
        order_id,
        "SANDBOX_CAP_RETRY_7788",
        raw_capture_data={"status": "COMPLETED"},
        db_file=test_db_path,
    )
    rec_after = proposal_store.get_staged_proposal(tx_id, db_file=test_db_path)
    assert rec_after.status == TransactionState.CAPTURED.value
    assert rec_after.capture_id == "SANDBOX_CAP_RETRY_7788"


# -----------------------------------------------------------------------------
# 3. HTTP API Endpoints for State Transitions
# -----------------------------------------------------------------------------

def test_api_approve_proposal_endpoint():
    """POST /api/v1/payments/proposals/{id}/approve transitions state and returns 200."""
    # Stage a proposal in default store
    mandate = PurchaseMandate(max_amount=100.0, currency="USD")
    candidate = DiscoveredProduct(
        product_id="prod_api_appr",
        name="Mouse",
        price=50.0,
        currency="USD",
        merchant_name="MouseStore",
    )
    tx = ProposedTransaction(
        product_name=candidate.name,
        product_price=candidate.price,
        final_total=candidate.price,
        currency="USD",
        merchant_name=candidate.merchant_name,
    )
    evaluation = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
    tx_id = f"tx_api_{uuid.uuid4().hex[:8]}"
    proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
    )

    # Call approval endpoint
    res = client.post(f"/api/v1/payments/proposals/{tx_id}/approve", json={"user_id": "human_operator_1"})
    assert res.status_code == 200
    data = res.json()
    assert data["transaction_id"] == tx_id
    assert data["previous_state"] == "STAGED"
    assert data["current_state"] == "HUMAN_APPROVED"
    assert "audit_event_hash" in data

    # Verify state endpoint
    state_res = client.get(f"/api/v1/payments/proposals/{tx_id}/state")
    assert state_res.status_code == 200
    assert state_res.json()["status"] == "HUMAN_APPROVED"


def test_api_reject_proposal_endpoint():
    """POST /api/v1/payments/proposals/{id}/reject transitions state to HUMAN_REJECTED."""
    mandate = PurchaseMandate(max_amount=100.0, currency="USD")
    candidate = DiscoveredProduct(
        product_id="prod_api_rej",
        name="Mouse",
        price=50.0,
        currency="USD",
        merchant_name="MouseStore",
    )
    tx = ProposedTransaction(
        product_name=candidate.name,
        product_price=candidate.price,
        final_total=candidate.price,
        currency="USD",
        merchant_name=candidate.merchant_name,
    )
    evaluation = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
    tx_id = f"tx_api_rej_{uuid.uuid4().hex[:8]}"
    proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
    )

    res = client.post(
        f"/api/v1/payments/proposals/{tx_id}/reject",
        json={"user_id": "human_operator_1", "reason": "Found better price elsewhere"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["current_state"] == "HUMAN_REJECTED"


def test_api_cancel_proposal_endpoint():
    """POST /api/v1/payments/proposals/{id}/cancel transitions state to CANCELLED."""
    mandate = PurchaseMandate(max_amount=100.0, currency="USD")
    candidate = DiscoveredProduct(
        product_id="prod_api_canc",
        name="Mouse",
        price=50.0,
        currency="USD",
        merchant_name="MouseStore",
    )
    tx = ProposedTransaction(
        product_name=candidate.name,
        product_price=candidate.price,
        final_total=candidate.price,
        currency="USD",
        merchant_name=candidate.merchant_name,
    )
    evaluation = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
    tx_id = f"tx_api_canc_{uuid.uuid4().hex[:8]}"
    proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
    )

    res = client.post(
        f"/api/v1/payments/proposals/{tx_id}/cancel",
        json={"user_id": "human_operator_1", "reason": "User cancelled"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["current_state"] == "CANCELLED"

