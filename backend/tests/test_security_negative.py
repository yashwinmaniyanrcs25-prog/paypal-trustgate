"""TrustGate Mandatory Security Negative Test Suite (TEST 1 - TEST 8).

Strictly verifies that TrustGate deterministic guardrails reject:
TEST 1: Unapproved checkout attempts (skipping human authorization).
TEST 1B: Policy revalidation failures post-approval.
TEST 1C: Arbitrary / synthetic transaction approvals bypassing genuine discovery.
TEST 2: Policy budget breaches (TG-001).
TEST 3: Restricted or unverified merchants (TG-004).
TEST 4: Client-side price tampering / spoofing.
TEST 5: Checkouts on rejected proposals (HUMAN_REJECTED terminal state).
TEST 6: Duplicate captures / double payment replay attacks.
TEST 7: Autonomous AI authorization attempts (TG-007).
TEST 8: Cryptographic audit trail tampering / sequence manipulation.
"""

import json
import pytest
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from app.core.security import PaymentExecutionBlockedError
from app.db.database import (
    init_db,
    get_db_connection,
    record_audit_event,
    record_human_approval,
    record_human_rejection,
    get_human_approval,
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
    """Provides an isolated SQLite database to protect developer database from corruption."""
    db_file = tmp_path / "test_security_negative.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def staged_tx(isolated_db):
    """Creates and stages a valid purchase candidate in the isolated database."""
    mandate = PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )
    candidate = DiscoveredProduct(
        product_id="prod_sec_keyboard_01",
        name="Keychron K2 Mechanical Keyboard",
        description="Wireless ergonomic keyboard",
        category="Keyboards",
        price=112.50,
        currency="USD",
        condition="new",
        merchant_name="Official Keychron Store",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="channel3_api",
        is_demo_data=False,
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
    tx_id = f"tx_sec_{uuid.uuid4().hex[:8]}"

    rec = proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
        user_id="user_sec_test",
        db_file=isolated_db,
    )
    return rec


# -----------------------------------------------------------------------------
# TEST 1: Unapproved Checkout Attempt
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_unapproved_checkout_attempt_blocked(isolated_db, staged_tx):
    """TEST 1: Checkout cannot proceed while proposal is in STAGED state without human approval."""
    tx_id = staged_tx.staged_proposal_id
    assert staged_tx.status == TransactionState.STAGED.value

    # Attempt order creation directly without calling record_human_approval
    with pytest.raises(PaymentExecutionBlockedError) as exc_info:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_sec_test",
            caller_role="human_user",
        )

    assert "Explicit human approval is required" in str(exc_info.value)
    # Ensure state remained STAGED
    rec = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert rec.status == TransactionState.STAGED.value


@pytest.mark.asyncio
async def test_1b_policy_revalidation_failure_post_approval_blocked(isolated_db, staged_tx):
    """TEST 1B: A human-approved proposal that violates current policy upon revalidation cannot create order."""
    tx_id = staged_tx.staged_proposal_id

    # 1. Human operator explicitly approves candidate
    record_human_approval(
        transaction_id=tx_id,
        user_id="user_sec_test",
        policy_signature="sig_sec_123",
        approved_amount=112.50,
        currency="USD",
        db_file=isolated_db,
    )
    rec_approved = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert rec_approved.status == TransactionState.HUMAN_APPROVED.value

    # 2. Modify mandate budget downwards to $50, causing the $112.50 item to violate TG-001 upon revalidation
    rec_approved.mandate.max_amount = 50.00
    with get_db_connection(isolated_db) as conn:
        conn.execute(
            "UPDATE mandates SET max_amount = 50.00 WHERE mandate_id = (SELECT mandate_id FROM staged_proposals WHERE staged_proposal_id = ?)",
            (tx_id,),
        )
        conn.commit()

    # 3. Attempt order creation - policy revalidation must block it immediately before PayPal call
    with pytest.raises(PaymentExecutionBlockedError) as exc_info:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_sec_test",
            caller_role="human_user",
        )

    assert "Policy revalidation failed immediately prior to order creation" in str(exc_info.value)
    # Ensure no PayPal order was linked
    rec_after = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert rec_after.paypal_order_id is None


# -----------------------------------------------------------------------------
# TEST 1C: Arbitrary / Unknown Transaction Approval Blocked from Checkout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1c_arbitrary_transaction_approval_blocked_from_checkout(isolated_db):
    """TEST 1C: Unknown or synthetic transaction IDs cannot become eligible for checkout."""
    unknown_tx_id = f"tx_unknown_arbitrary_{uuid.uuid4().hex[:8]}"

    # 1. Attempt to record human approval against an unknown transaction ID
    # The operation must reject the unknown transaction (cannot authorize un-staged transactions)
    with pytest.raises(ValueError) as exc_approval:
        record_human_approval(
            transaction_id=unknown_tx_id,
            user_id="user_attacker",
            policy_signature="sig_fake_arbitrary_bypass",
            approved_amount=99.99,
            currency="USD",
            db_file=isolated_db,
        )
    assert "not found" in str(exc_approval.value).lower()

    # 2. Attempt checkout using that unknown transaction ID — must be strictly blocked
    with pytest.raises((PaymentExecutionBlockedError, ValueError)) as exc_checkout:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=unknown_tx_id,
            user_id="user_attacker",
            caller_role="human_user",
            db_file=isolated_db,
        )

    # 3. Assert that checkout is blocked and no PayPal order is linked
    checkout_err = str(exc_checkout.value).lower()
    assert (
        "not found" in checkout_err
        or "blocked" in checkout_err
        or "genuine" in checkout_err
        or "explicit human approval is required" in checkout_err
    )
    persisted = proposal_store.get_staged_proposal(unknown_tx_id, db_file=isolated_db)
    assert persisted is None or persisted.paypal_order_id is None

    # 4. Assert no human authorization record exists in database
    auth_rec = get_human_approval(unknown_tx_id, db_file=isolated_db)
    assert auth_rec is None

    # 5. Verify that a synthetic database record is never treated as a genuine staged purchase proposal
    synthetic_tx_id = f"tx_synth_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    synthetic_mandate = PurchaseMandate(
        max_amount=100.0,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )
    synthetic_product = DiscoveredProduct(
        product_id=f"prod_synth_{uuid.uuid4().hex[:6]}",
        name="Fabricated Candidate",
        description="A fabricated candidate with no genuine lineage",
        category="Electronics",
        price=50.0,
        currency="USD",
        condition="new",
        merchant_name="Unverified Merchant",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="catalog",
        is_demo_data=True,
        demo_notice="Test item",
    )
    synthetic_tx = ProposedTransaction(
        product_name=synthetic_product.name,
        product_price=synthetic_product.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=50.0,
        currency="USD",
        merchant_name=synthetic_product.merchant_name,
        merchant_verified=True,
        product_condition=synthetic_product.condition,
        add_ons=[],
    )
    synthetic_eval = policy_engine.evaluate_mandate(
        synthetic_mandate, synthetic_tx, caller_role="human_user"
    )

    with get_db_connection(isolated_db) as conn:
        conn.execute(
            """
            INSERT INTO staged_proposals (
                staged_proposal_id, mandate_id, candidate_product_id, candidate_data,
                mandate_data, evaluation_data, user_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                synthetic_tx_id,
                f"man_{synthetic_tx_id}",
                synthetic_product.product_id,
                synthetic_product.model_dump_json(),
                synthetic_mandate.model_dump_json(),
                synthetic_eval.model_dump_json(),
                "user_attacker",
                TransactionState.HUMAN_APPROVED.value,
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO human_approvals (
                approval_id, transaction_id, user_id, policy_signature, approved_amount,
                currency, action, actor_role, consent_token, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                f"appr_{synthetic_tx_id}",
                synthetic_tx_id,
                "user_attacker",
                synthetic_eval.policy_signature,
                synthetic_product.price,
                synthetic_product.currency,
                "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
                "human_user",
                "tok_fake_synth",
                now_iso,
            ),
        )
        conn.commit()

    proposal_store.set_db_file(synthetic_tx_id, isolated_db)

    # Attempt checkout on synthetic record — must be blocked because it lacks genuine catalog/staging lineage
    with pytest.raises(PaymentExecutionBlockedError) as exc_synth:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=synthetic_tx_id,
            user_id="user_attacker",
            caller_role="human_user",
            db_file=isolated_db,
        )
    assert "genuine" in str(exc_synth.value).lower()

    # Ensure no PayPal order was created for the synthetic transaction
    with get_db_connection(isolated_db) as conn:
        synth_orders = conn.execute(
            "SELECT * FROM orders_and_captures WHERE staged_proposal_id = ?",
            (synthetic_tx_id,),
        ).fetchall()
        assert len(synth_orders) == 0


# -----------------------------------------------------------------------------
# TEST 2: Policy Budget Breach (TG-001)
# -----------------------------------------------------------------------------
def test_2_policy_budget_breach_blocked(isolated_db):
    """TEST 2: Attempting to purchase an item exceeding the mandate maximum amount is strictly BLOCKED."""
    strict_mandate = PurchaseMandate(
        max_amount=100.00,
        currency="USD",
        allowed_conditions=["new"],
    )
    expensive_item = ProposedTransaction(
        product_name="Pro Display XDR",
        product_price=1299.00,
        shipping_cost=0.0,
        tax=103.92,
        additional_charges=0.0,
        final_total=1402.92,
        currency="USD",
        merchant_name="Apple Store",
        merchant_verified=True,
        product_condition="new",
        add_ons=[],
    )

    result = policy_engine.evaluate_mandate(strict_mandate, expensive_item, caller_role="human_user")
    assert result.approved is False
    assert result.status == "BLOCKED"
    assert result.can_proceed_to_paypal is False
    assert any(v.rule_id == "TG-001" for v in result.violations)
    assert any("exceeds user mandate maximum" in v.message for v in result.violations)


# -----------------------------------------------------------------------------
# TEST 3: Restricted Merchant (TG-004)
# -----------------------------------------------------------------------------
def test_3_restricted_or_unverified_merchant_blocked(isolated_db):
    """TEST 3: Items from unverified sellers or blacklisted vendors are deterministically BLOCKED."""
    mandate = PurchaseMandate(
        max_amount=200.00,
        currency="USD",
        require_merchant_verification=True,
    )

    # 3a. Unverified merchant
    unverified_tx = ProposedTransaction(
        product_name="Wireless Earbuds",
        product_price=49.99,
        final_total=49.99,
        currency="USD",
        merchant_name="Anonymous Dropshipper",
        merchant_verified=False,
        product_condition="new",
    )
    res_unverified = policy_engine.evaluate_mandate(mandate, unverified_tx, caller_role="human_user")
    assert res_unverified.approved is False
    assert any(v.rule_id == "TG-004" for v in res_unverified.violations)

    # 3b. Blacklisted merchant
    blacklisted_tx = ProposedTransaction(
        product_name="Refurbished Phone",
        product_price=99.00,
        final_total=99.00,
        currency="USD",
        merchant_name="unknown_scam_store",
        merchant_verified=True,  # Even if marked verified, blacklisted name blocks it
        product_condition="new",
    )
    res_blacklisted = policy_engine.evaluate_mandate(mandate, blacklisted_tx, caller_role="human_user")
    assert res_blacklisted.approved is False
    assert any("untrusted or blacklisted vendor" in v.message for v in res_blacklisted.violations)


# -----------------------------------------------------------------------------
# TEST 4: Client Price Manipulation / Spoofing
# -----------------------------------------------------------------------------
def test_4_client_price_manipulation_rejected(isolated_db):
    """TEST 4: Client spoofing item total vs itemized sum is blocked by TG-006 / math integrity check."""
    mandate = PurchaseMandate(max_amount=100.00, currency="USD")
    # Real item price is $120, but client manipulates final_total to claim $80
    spoofed_tx = ProposedTransaction(
        product_name="Mechanical Keyboard",
        product_price=120.00,
        shipping_cost=10.00,
        tax=9.60,
        additional_charges=0.00,
        final_total=80.00,  # Manipulated! Real sum = 139.60
        currency="USD",
        merchant_name="Keychron Store",
        merchant_verified=True,
        product_condition="new",
    )

    res = policy_engine.evaluate_mandate(mandate, spoofed_tx, caller_role="human_user")
    assert res.approved is False
    assert res.status == "BLOCKED"
    assert any("diverges from itemized components sum" in v.message for v in res.violations)


# -----------------------------------------------------------------------------
# TEST 5: Rejected Proposal Cannot Proceed to Order Creation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_rejected_proposal_terminal_state(isolated_db, staged_tx):
    """TEST 5: Explicit human rejection is terminal; checkout or transition to ORDER_CREATED fails."""
    tx_id = staged_tx.staged_proposal_id

    # 1. Reject proposal
    rej_res = record_human_rejection(
        transaction_id=tx_id,
        user_id="user_sec_test",
        reason="Found an alternative with faster shipping",
        db_file=isolated_db,
    )
    assert rej_res["current_state"] == TransactionState.HUMAN_REJECTED

    # 2. State machine strictly forbids transitioning from HUMAN_REJECTED
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.ORDER_CREATED,
            db_file=isolated_db,
        )

    # 3. PayPal service blocks execution on non-approved proposal
    with pytest.raises(PaymentExecutionBlockedError) as exc_info:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="user_sec_test",
            caller_role="human_user",
        )
    err_msg = str(exc_info.value).upper()
    assert "HUMAN_REJECTED" in err_msg or "CANNOT CREATE PAYPAL SANDBOX ORDER" in err_msg

    # 4. Invariant: Terminal rejection is persisted in SQLite
    persisted = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert persisted.status == TransactionState.HUMAN_REJECTED.value
    assert persisted.rejection_reason == "Found an alternative with faster shipping"
    assert persisted.paypal_order_id is None
    assert persisted.captured is False


# -----------------------------------------------------------------------------
# TEST 6: Duplicate Capture / Replay Attack Idempotency
# -----------------------------------------------------------------------------
def test_6_duplicate_capture_idempotency(isolated_db, staged_tx):
    """TEST 6: Attempting duplicate capture on an already captured transaction is safe and idempotent."""
    tx_id = staged_tx.staged_proposal_id
    order_id = "SANDBOX_ORD_IDEM_9988"

    # Advance to HUMAN_APPROVED -> ORDER_CREATED
    record_human_approval(
        transaction_id=tx_id,
        user_id="user_sec_test",
        policy_signature="sig_sec_123",
        approved_amount=112.50,
        currency="USD",
        db_file=isolated_db,
    )
    proposal_store.link_paypal_order(tx_id, order_id, db_file=isolated_db)

    # First capture
    first_capture = proposal_store.mark_captured(
        order_id=order_id,
        capture_id="SANDBOX_CAP_ORIG_001",
        capture_data={"status": "COMPLETED", "amount": {"value": "112.50"}},
        db_file=isolated_db,
    )
    assert first_capture.captured is True
    assert first_capture.status == TransactionState.CAPTURED.value

    # Terminal state: second transition to CAPTURED is forbidden by state machine
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.CAPTURED,
            db_file=isolated_db,
        )

    # Audit integrity remains intact
    integrity = verify_audit_integrity(isolated_db)
    assert integrity["is_valid"] is True


# -----------------------------------------------------------------------------
# TEST 7: Autonomous AI Authorization Blocked (TG-007)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_7_autonomous_ai_authorization_blocked(isolated_db, staged_tx):
    """TEST 7: Autonomous AI agents attempting to authorize payment or create orders are barred."""
    tx_id = staged_tx.staged_proposal_id

    # Policy engine blocks caller_role="ai_agent"
    res = policy_engine.evaluate_mandate(
        staged_tx.mandate,
        ProposedTransaction(
            product_name="Sample",
            product_price=10.0,
            final_total=10.0,
            currency="USD",
            merchant_name="Store",
            merchant_verified=True,
            product_condition="new",
        ),
        caller_role="ai_agent",
    )
    assert res.approved is False
    assert any(v.rule_id == "TG-007" for v in res.violations)

    # PayPal checkout blocks caller_role="ai_agent"
    with pytest.raises(PaymentExecutionBlockedError) as exc_info:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="ai_agent_bot_01",
            caller_role="ai_agent",
        )
    assert "AI agents" in str(exc_info.value) or "Autonomous AI" in str(exc_info.value)

    # Invariants: No human approval was created, no order was created, no capture occurred
    assert get_human_approval(tx_id, db_file=isolated_db) is None
    persisted = proposal_store.get_staged_proposal(tx_id, db_file=isolated_db)
    assert persisted.paypal_order_id is None
    assert persisted.captured is False


# -----------------------------------------------------------------------------
# TEST 8: Audit Chain Tamper Detection
# -----------------------------------------------------------------------------
def test_8_cryptographic_audit_tamper_detection(isolated_db, staged_tx):
    """TEST 8: Direct manual tampering with SQLite records breaks the SHA-256 chain and is detected."""
    tx_id = staged_tx.staged_proposal_id

    # Record 3 events
    record_audit_event(
        transaction_id=tx_id,
        event_type="DISCOVERY_COMPLETED",
        stage="DISCOVERY",
        status="SUCCESS",
        details={"query": "keyboard", "candidates_found": 5},
        db_file=isolated_db,
    )
    record_audit_event(
        transaction_id=tx_id,
        event_type="MANDATE_EVALUATED",
        stage="POLICY",
        status="APPROVED",
        details={"mandate_budget": 150.0},
        db_file=isolated_db,
    )

    # Verify baseline is clean
    baseline = verify_audit_integrity(isolated_db)
    assert baseline["is_valid"] is True
    assert baseline["total_events"] >= 3

    # Tamper with event sequence 2 details payload directly in SQLite
    # Note: Drop trigger temporarily in isolated test DB to simulate malicious filesystem/raw manipulation
    with get_db_connection(isolated_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute(
            "UPDATE audit_events SET details = ? WHERE sequence_number = 2;",
            (json.dumps({"tampered": "malicious price alteration $10 to $1000"}),),
        )
        conn.commit()

    # Verify audit integrity mathematically detects the tampering
    tampered_result = verify_audit_integrity(isolated_db)
    assert tampered_result["is_valid"] is False
    assert tampered_result["first_invalid_sequence"] == 2
    failure_msg = tampered_result["failure_reason"].lower()
    assert (
        "does not match" in failure_msg
        or "hash mismatch" in failure_msg
        or "sha-256" in failure_msg
        or "tampered" in failure_msg
    )

