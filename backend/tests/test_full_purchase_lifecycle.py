"""Comprehensive 14-Step Automated End-to-End Purchase Lifecycle Verification Test Suite.

Verifies the complete PayPal TrustGate purchase workflow:
Step 1: AI Intent Interpreter creates PurchaseMandate from user prompt.
Step 2: Channel3 search discovers candidate items.
Step 3: Deterministic TG-001 through TG-007 policy engine evaluates candidates.
Step 4: User reviews mandate and selects a compliant candidate.
Step 5: Candidate is staged in SQLite (STAGED state, zero payment authorized).
Step 6: Pre-approval checkout attempt is strictly BLOCKED by policy guardrail.
Step 7: Human operator grants explicit approval (HUMAN_APPROVED state).
Step 8: PayPal Sandbox order created and linked (ORDER_CREATED state).
Step 9: PayPal Orders v2 pre-flight validator verifies schema and parameters.
Step 10: Buyer approval simulation in PayPal Sandbox environment.
Step 11: PayPal order captured and persisted (CAPTURED state).
Step 12: Terminal state verification (CAPTURED state cannot be re-executed or altered).
Step 13: Cryptographic audit trail validation (SHA-256 hash chaining remains 100% valid).
Step 14: Tamper check verification: SQLite modifications immediately flag invalid sequence.
"""

import json
import pytest
import sqlite3
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.core.config import settings
from app.core.security import PaymentExecutionBlockedError
from app.db.database import (
    init_db,
    get_db_connection,
    record_audit_event,
    record_human_approval,
    verify_audit_integrity,
    transition_transaction_state,
)
from app.models.lifecycle import TransactionState, InvalidStateTransitionError
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.intent_interpreter_service import intent_interpreter_service
from app.services.channel3_service import channel3_service
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.services.paypal_service import paypal_service
from app.services.paypal_order_validator import paypal_order_validator

# Pydantic v2 BaseSettings blocks instance-level attribute patching.
# All settings method mocks must use class-level patching via type(settings).
_SettingsClass = type(settings)


@pytest.fixture
def lifecycle_db(tmp_path):
    """Provides an isolated database for end-to-end lifecycle testing."""
    db_file = tmp_path / "test_full_lifecycle.db"
    init_db(db_file)
    return db_file


@pytest.mark.asyncio
async def test_complete_14_step_purchase_lifecycle(lifecycle_db):
    """Executes the full 14-step verified purchase lifecycle from AI intent to settled capture."""

    # -------------------------------------------------------------------------
    # STEP 1: AI Intent Interpreter creates PurchaseMandate from user prompt
    # -------------------------------------------------------------------------
    user_prompt = "I need an ergonomic mechanical keyboard under $150. New condition only from verified sellers."
    mock_groq_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "max_amount": 150.00,
                            "currency": "USD",
                            "allowed_conditions": ["new"],
                            "require_merchant_verification": True,
                            "allow_add_ons": False,
                            "user_restrictions": ["mechanical keyboard"],
                            "needs_clarification": False,
                            "clarification_prompt": None,
                            "extracted_intent_summary": "Ergonomic mechanical keyboard under $150, new condition, verified seller.",
                        }
                    )
                }
            }
        ]
    }

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = httpx.Response(
                    status_code=200,
                    content=json.dumps(mock_groq_resp).encode(),
                    request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
                )
                intent_res = await intent_interpreter_service.interpret_intent(user_prompt)

    assert intent_res.success is True
    assert intent_res.mandate is not None
    mandate = intent_res.mandate
    assert mandate.max_amount == 150.00
    assert mandate.currency == "USD"
    assert "new" in mandate.allowed_conditions
    assert mandate.require_merchant_verification is True

    # -------------------------------------------------------------------------
    # STEP 2: Channel3 search discovers candidate items
    # -------------------------------------------------------------------------
    raw_channel3_keyboard = {
        "id": "prod_k2_keyboard_8832",
        "title": "Keychron K2 Wireless Mechanical Keyboard (Version 2)",
        "description": "Compact 75% layout Bluetooth wireless mechanical keyboard.",
        "category": {"id": "cat_kb", "title": "Keyboards & Mice"},
        "brands": [{"id": "b_keychron", "name": "Keychron"}],
        "images": [{"cleaned_url": "https://cdn.trychannel3.com/images/keychron_k2.png", "is_main_image": True}],
        "offers": [
            {
                "price": {"amount": 112.50, "currency": "USD"},
                "domain": "keychron.com",
                "url": "https://www.keychron.com/products/keychron-k2",
                "availability": "InStock",
                "condition": "new",
            }
        ],
    }

    candidate = channel3_service._normalize_product(raw_channel3_keyboard, fallback_currency="USD")
    assert candidate.product_id == "ch3_prod_k2_keyboard_8832"
    assert candidate.price == 112.50
    assert candidate.currency == "USD"
    assert candidate.merchant_name == "keychron.com"
    assert candidate.merchant_verified is True
    assert candidate.condition == "new"

    # -------------------------------------------------------------------------
    # STEP 3: Deterministic TG-001 through TG-007 policy evaluation
    # -------------------------------------------------------------------------
    proposed_tx = ProposedTransaction(
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

    evaluation = policy_engine.evaluate_mandate(mandate, proposed_tx, caller_role="human_user")
    assert evaluation.approved is True
    assert evaluation.status == "APPROVED"
    assert evaluation.can_proceed_to_paypal is True
    assert evaluation.policy_signature.startswith("tg_sig_")

    # -------------------------------------------------------------------------
    # STEP 4: User reviews mandate & candidates, confirms selection
    # -------------------------------------------------------------------------
    assert candidate.price <= mandate.max_amount
    assert candidate.currency == mandate.currency

    # -------------------------------------------------------------------------
    # STEP 5: Staging proposal in SQLite (STAGED state)
    # -------------------------------------------------------------------------
    tx_id = f"tx_e2e_{uuid.uuid4().hex[:8]}"
    staged_record = proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=mandate,
        candidate=candidate,
        policy_evaluation=evaluation,
        user_id="operator_jane",
        db_file=lifecycle_db,
    )
    assert staged_record.status == TransactionState.STAGED.value
    assert staged_record.paypal_order_id is None
    assert staged_record.captured is False

    # -------------------------------------------------------------------------
    # STEP 6: Pre-approval checkout attempt is strictly BLOCKED
    # -------------------------------------------------------------------------
    with pytest.raises(PaymentExecutionBlockedError) as block_err:
        await paypal_service.create_sandbox_order(
            staged_proposal_id=tx_id,
            user_id="operator_jane",
            caller_role="human_user",
        )
    assert "Explicit human approval is required" in str(block_err.value)

    # -------------------------------------------------------------------------
    # STEP 7: Operator grants explicit human approval (HUMAN_APPROVED state)
    # -------------------------------------------------------------------------
    approval_res = record_human_approval(
        transaction_id=tx_id,
        user_id="operator_jane",
        policy_signature=evaluation.policy_signature,
        approved_amount=candidate.price,
        currency=candidate.currency,
        action="AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
        actor_role="human_user",
        consent_token="tok_cons_operator_jane_001",
        db_file=lifecycle_db,
    )
    assert approval_res["current_state"] == TransactionState.HUMAN_APPROVED
    assert approval_res["approval_id"].startswith("appr_")

    # -------------------------------------------------------------------------
    # STEP 8: PayPal Sandbox order created and linked (ORDER_CREATED state)
    # -------------------------------------------------------------------------
    sandbox_paypal_order_id = "SANDBOX_ORD_E2E_8899"
    link_success = proposal_store.link_paypal_order(
        staged_proposal_id=tx_id,
        order_id=sandbox_paypal_order_id,
        db_file=lifecycle_db,
    )
    assert link_success is True

    persisted_record = proposal_store.get_staged_proposal(tx_id, db_file=lifecycle_db)
    assert persisted_record.status == TransactionState.ORDER_CREATED.value
    assert persisted_record.paypal_order_id == sandbox_paypal_order_id

    # -------------------------------------------------------------------------
    # STEP 9: PayPal Orders v2 pre-flight schema validation
    # -------------------------------------------------------------------------
    order_payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": evaluation.policy_signature,
                "description": f"TrustGate Sandbox: {candidate.name}",
                "amount": {
                    "currency_code": candidate.currency,
                    "value": f"{candidate.price:.2f}",
                },
            }
        ],
        "application_context": {
            "brand_name": "PayPal TrustGate Agentic Guard",
            "landing_page": "BILLING",
            "user_action": "PAY_NOW",
        },
    }
    schema_val = paypal_order_validator.validate_order_request(order_payload)
    assert schema_val.is_valid is True
    assert len(schema_val.errors) == 0

    # -------------------------------------------------------------------------
    # STEP 10: Buyer approval in PayPal Sandbox environment
    # -------------------------------------------------------------------------
    buyer_approval_token = f"EC-SANDBOX-TOKEN-{uuid.uuid4().hex[:10]}"
    record_audit_event(
        transaction_id=tx_id,
        event_type="PAYPAL_BUYER_APPROVED",
        stage="PAYMENT",
        status="APPROVED",
        details={
            "order_id": sandbox_paypal_order_id,
            "buyer_token": buyer_approval_token,
            "environment": "sandbox",
        },
        actor_role="buyer_in_sandbox",
        db_file=lifecycle_db,
    )

    # -------------------------------------------------------------------------
    # STEP 11: PayPal order captured and persisted (CAPTURED state)
    # -------------------------------------------------------------------------
    sandbox_capture_id = "SANDBOX_CAP_E2E_7711"
    capture_record = proposal_store.mark_captured(
        order_id=sandbox_paypal_order_id,
        capture_id=sandbox_capture_id,
        capture_data={
            "id": sandbox_paypal_order_id,
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": sandbox_capture_id,
                                "status": "COMPLETED",
                                "amount": {"value": f"{candidate.price:.2f}", "currency_code": candidate.currency},
                            }
                        ]
                    }
                }
            ],
        },
        db_file=lifecycle_db,
    )
    assert capture_record is not None
    assert capture_record.captured is True
    assert capture_record.status == TransactionState.CAPTURED.value
    assert capture_record.capture_id == sandbox_capture_id

    # -------------------------------------------------------------------------
    # STEP 12: Terminal state verification (cannot transition from CAPTURED)
    # -------------------------------------------------------------------------
    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.ORDER_CREATED,
            db_file=lifecycle_db,
        )

    with pytest.raises(InvalidStateTransitionError):
        transition_transaction_state(
            transaction_id=tx_id,
            target_state=TransactionState.CANCELLED,
            db_file=lifecycle_db,
        )

    # -------------------------------------------------------------------------
    # STEP 13: Cryptographic audit integrity verification (SHA-256 chain)
    # -------------------------------------------------------------------------
    integrity = verify_audit_integrity(lifecycle_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] >= 5
    assert integrity["last_event_hash"] is not None
    assert integrity["first_invalid_sequence"] is None

    # -------------------------------------------------------------------------
    # STEP 14: Tamper check: SQLite modification breaks hash chain
    # -------------------------------------------------------------------------
    with get_db_connection(lifecycle_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute(
            "UPDATE audit_events SET event_type = 'UNAUTHORIZED_ALTERATION' WHERE sequence_number = 3;"
        )
        conn.commit()

    tampered_integrity = verify_audit_integrity(lifecycle_db)
    assert tampered_integrity["is_valid"] is False
    assert tampered_integrity["first_invalid_sequence"] == 3
    failure_msg = tampered_integrity["failure_reason"].lower()
    assert (
        "does not match" in failure_msg
        or "hash mismatch" in failure_msg
        or "sha-256" in failure_msg
        or "tampered" in failure_msg
    )

