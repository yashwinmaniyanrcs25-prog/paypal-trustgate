"""Comprehensive Regression Test Suite for Genuine Staged Proposal Validation.

Validates the complete 10-point lifecycle requirement for PayPal TrustGate:
1. Genuine proposal is staged.
2. Proposal is persisted across SQLite tables (staged_proposals, proposals, mandates).
3. Same proposal is retrieved accurately by authoritative identifier.
4. Proposal is approved with explicit human authorization and consent token.
5. Same approved proposal reaches create-order.
6. PayPal Sandbox order creation succeeds with valid credentials (mocked external gateway).
7. Demo fixture proposal is strictly rejected (cannot create PayPal orders).
8. Unapproved proposal is rejected prior to human sign-off.
9. Stale or fabricated proposal IDs are rejected.
10. Tampered proposal data is rejected by pre-checkout policy revalidation.
"""

import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import PaymentExecutionBlockedError
from app.db.database import get_db_connection, init_db, record_human_approval, get_human_approval
from app.models.lifecycle import TransactionState
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.services.paypal_service import paypal_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def genuine_mandate():
    return PurchaseMandate(
        max_amount=200.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["Mechanical Keyboard", "US shipping only"],
    )


@pytest.fixture
def genuine_candidate():
    """A genuine marketplace candidate from Channel3 / live graph."""
    return DiscoveredProduct(
        product_id="ch3_genuine_k2_kbd",
        name="Keychron K2 Wireless Mechanical Keyboard",
        description="Authentic wireless mechanical keyboard with Gateron Brown switches.",
        category="Keyboards",
        price=89.99,
        currency="USD",
        condition="new",
        merchant_name="keychron.com",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="channel3_api",
        is_demo_data=False,
        demo_notice="",
        marketplace_id="channel3",
        region="global",
        data_freshness="Live Channel3 Universal Graph",
    )


@pytest.fixture
def demo_fixture_candidate():
    """A demonstration fixture candidate."""
    return DiscoveredProduct(
        product_id="cand_demo_laptop_001",
        name="Test Approved Laptop",
        description="Demonstration item for policy simulation only.",
        category="Computers",
        price=120.00,
        currency="USD",
        condition="new",
        merchant_name="Official Verified Store",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="local_demo_fixture",
        is_demo_data=True,
        demo_notice="Fictional demonstration data. Not real-world merchant or pricing information.",
        marketplace_id="demo",
        region="US",
        data_freshness="Simulated",
    )


def test_scenarios_1_to_6_genuine_lifecycle_staging_persistence_approval_checkout(
    genuine_mandate, genuine_candidate
):
    """Scenarios 1-6: Genuine proposal full lifecycle through staging, SQLite persistence,

    retrieval, human approval, and PayPal Sandbox order creation.
    """
    # 1. Genuine proposal is staged via POST /api/v1/proposals/stage
    stage_payload = {
        "mandate": genuine_mandate.model_dump(),
        "candidate": genuine_candidate.model_dump(),
        "user_id": "operator_test",
    }
    stage_res = client.post("/api/v1/proposals/stage", json=stage_payload)
    assert stage_res.status_code == 200, stage_res.text
    stage_data = stage_res.json()

    staged_id = stage_data["staged_proposal_id"]
    assert staged_id.startswith("stg_")
    assert stage_data["policy_approved"] is True
    assert stage_data["is_demo_data"] is False
    assert stage_data["payment_executed"] is False
    assert stage_data["requires_human_approval"] is True

    # 2. Proposal is persisted across SQLite tables
    with get_db_connection() as conn:
        sp_row = conn.execute(
            "SELECT * FROM staged_proposals WHERE staged_proposal_id = ?;",
            (staged_id,),
        ).fetchone()
        assert sp_row is not None
        assert sp_row["status"] == TransactionState.STAGED.value
        assert sp_row["candidate_product_id"] == genuine_candidate.product_id

        mandate_id = sp_row["mandate_id"]
        man_row = conn.execute(
            "SELECT * FROM mandates WHERE mandate_id = ?;",
            (mandate_id,),
        ).fetchone()
        assert man_row is not None
        assert man_row["max_amount"] == genuine_mandate.max_amount

        prop_row = conn.execute(
            "SELECT * FROM proposals WHERE mandate_id = ?;",
            (mandate_id,),
        ).fetchone()
        assert prop_row is not None
        assert prop_row["product_id"] == genuine_candidate.product_id
        assert prop_row["is_demo_data"] == 0

    # 3. Same proposal is retrieved by ID
    retrieved = proposal_store.get_staged_proposal(staged_id)
    assert retrieved is not None
    assert retrieved.staged_proposal_id == staged_id
    assert retrieved.candidate.name == genuine_candidate.name
    assert retrieved.candidate.price == 89.99
    assert retrieved.candidate.is_demo_data is False
    assert retrieved.status == TransactionState.STAGED.value

    # 4. Proposal is approved with explicit human authorization
    approve_payload = {
        "user_id": "operator_human_reviewer",
        "action": "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
        "consent_token": "consent_test_token_123",
        "rationale": "Verified purchase within budget constraints",
    }
    appr_res = client.post(f"/api/v1/payments/proposals/{staged_id}/approve", json=approve_payload)
    assert appr_res.status_code == 200, appr_res.text
    appr_data = appr_res.json()
    assert appr_data["current_state"] == TransactionState.HUMAN_APPROVED.value

    # Verify approval persistence in DB
    auth_rec = get_human_approval(staged_id)
    assert auth_rec is not None
    assert auth_rec["transaction_id"] == staged_id
    assert auth_rec["actor_role"] == "human_user"

    # 5. Same approved proposal reaches create-order
    # 6. PayPal Sandbox order creation succeeds with valid credentials (mocked gateway)
    fake_order_id = f"ORDER_{uuid.uuid4().hex[:14].upper()}"
    mock_order_response = {
        "id": fake_order_id,
        "status": "CREATED",
        "links": [
            {
                "href": f"https://www.sandbox.paypal.com/checkoutnow?token={fake_order_id}",
                "rel": "approve",
                "method": "GET",
            }
        ],
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 201
    mock_resp.json = lambda: mock_order_response

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_sandbox_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_sandbox_client_secret"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp), \
         patch.object(paypal_service, "get_access_token", new=AsyncMock(return_value="A21_fake_oauth_token")):

        order_res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_id, "user_id": "operator_human_reviewer"},
        )
        assert order_res.status_code == 200, order_res.text
        order_data = order_res.json()
        assert order_data["order_id"] == fake_order_id
        assert order_data["staged_proposal_id"] == staged_id
        assert order_data["status"] == "CREATED"
        assert order_data["is_sandbox"] is True
        assert order_data["is_demo_data"] is False
        assert order_data["amount"] == 89.99

    # Verify state transitioned to ORDER_CREATED
    post_order = proposal_store.get_staged_proposal(staged_id)
    assert post_order.status == TransactionState.ORDER_CREATED.value
    assert post_order.paypal_order_id == fake_order_id


def test_scenario_7_demo_fixture_proposal_is_rejected(genuine_mandate, demo_fixture_candidate):
    """Scenario 7: Demo fixture proposals can NEVER create PayPal orders.

    They must be cleanly rejected by genuine-proposal validation.
    """
    # 1. Stage a demo proposal
    stage_payload = {
        "mandate": genuine_mandate.model_dump(),
        "candidate": demo_fixture_candidate.model_dump(),
        "user_id": "tester_demo",
    }
    stage_res = client.post("/api/v1/proposals/stage", json=stage_payload)
    assert stage_res.status_code == 200
    staged_id = stage_res.json()["staged_proposal_id"]
    assert stage_res.json()["is_demo_data"] is True

    # 2. Human approval is recorded (simulating operator reviewing fixture)
    appr_res = client.post(
        f"/api/v1/payments/proposals/{staged_id}/approve",
        json={"user_id": "operator_human", "action": "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT"},
    )
    assert appr_res.status_code == 200

    # 3. Attempt create-order on demo proposal -> MUST BE REJECTED with HTTP 403
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_sandbox_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_sandbox_client_secret"):

        order_res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_id},
        )
        assert order_res.status_code == 403
        detail = order_res.json()["detail"]
        assert "demonstration fixture" in detail or "not a genuine staged purchase proposal" in detail
        assert staged_id in detail

    # Verify no PayPal order was linked and state remains HUMAN_APPROVED (not ORDER_CREATED)
    persisted = proposal_store.get_staged_proposal(staged_id)
    assert persisted.status == TransactionState.HUMAN_APPROVED.value
    assert persisted.paypal_order_id is None


def test_scenario_8_unapproved_proposal_is_rejected(genuine_mandate, genuine_candidate):
    """Scenario 8: A genuine proposal in STAGED state without prior human approval

    MUST be rejected by create-order (enforcing TG-007).
    """
    # Stage genuine proposal
    stage_res = client.post(
        "/api/v1/proposals/stage",
        json={"mandate": genuine_mandate.model_dump(), "candidate": genuine_candidate.model_dump()},
    )
    staged_id = stage_res.json()["staged_proposal_id"]

    # Attempt create-order without approving -> MUST BE REJECTED with HTTP 403
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        order_res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_id},
        )
        assert order_res.status_code == 403
        assert "Explicit human approval is required" in order_res.json()["detail"]


def test_scenario_9_stale_or_fabricated_proposal_ids_are_rejected(genuine_mandate):
    """Scenario 9: Stale, non-existent, or fabricated proposal IDs must be rejected."""
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        # 1. Non-existent ID (including the truncated prompt ID stg_f47b7b91)
        res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": "stg_f47b7b91_nonexistent"},
        )
        assert res.status_code in (400, 403)
        assert "not found" in res.json()["detail"].lower()

        # 2. Fabricated synthetic ID inserted directly into staged_proposals without proposals record
        synthetic_id = f"stg_synth_{uuid.uuid4().hex[:8]}"
        synth_cand = DiscoveredProduct(
            product_id="prod_fake_synth",
            name="Fake Product",
            price=50.0,
            currency="USD",
            condition="new",
            merchant_name="Fake Merchant",
            merchant_verified=True,
            verification_status="VERIFIED",
            data_source="channel3_api",
            is_demo_data=False,
        )
        synth_tx = ProposedTransaction(
            product_name=synth_cand.name,
            product_price=synth_cand.price,
            final_total=synth_cand.price,
            currency=synth_cand.currency,
            merchant_name=synth_cand.merchant_name,
            merchant_verified=True,
            product_condition=synth_cand.condition,
        )
        synth_eval = policy_engine.evaluate_mandate(genuine_mandate, synth_tx, caller_role="human_user")

        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO staged_proposals (
                    staged_proposal_id, mandate_id, candidate_product_id, candidate_data,
                    mandate_data, evaluation_data, user_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    synthetic_id,
                    f"man_{synthetic_id[4:]}",
                    synth_cand.product_id,
                    synth_cand.model_dump_json(),
                    genuine_mandate.model_dump_json(),
                    synth_eval.model_dump_json(),
                    "user_attacker",
                    TransactionState.STAGED.value,
                    "2026-11-11T00:00:00+00:00",
                    "2026-11-11T00:00:00+00:00",
                ),
            )
            conn.commit()

        # Add fake human approval
        record_human_approval(
            transaction_id=synthetic_id,
            user_id="user_attacker",
            policy_signature=synth_eval.policy_signature,
            approved_amount=50.0,
            currency="USD",
        )

        # create-order on fabricated record must fail because proposals table lacks genuine staging lineage
        res_synth = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": synthetic_id},
        )
        assert res_synth.status_code == 403
        assert "not a genuine staged purchase proposal" in res_synth.json()["detail"].lower()


def test_scenario_10_tampered_proposal_data_is_rejected(genuine_mandate, genuine_candidate):
    """Scenario 10: If a proposal's mandate or candidate data is tampered with after approval

    (e.g., mandate reduced below candidate price in the DB), policy revalidation detects it.
    """
    # 1. Stage and approve genuine proposal
    stage_res = client.post(
        "/api/v1/proposals/stage",
        json={"mandate": genuine_mandate.model_dump(), "candidate": genuine_candidate.model_dump()},
    )
    staged_id = stage_res.json()["staged_proposal_id"]

    client.post(
        f"/api/v1/payments/proposals/{staged_id}/approve",
        json={"user_id": "operator_human", "action": "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT"},
    )

    # 2. Tamper with mandate in SQLite: reduce max_amount from $200 to $50 (candidate is $89.99)
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE mandates SET max_amount = 50.00 WHERE mandate_id = (SELECT mandate_id FROM staged_proposals WHERE staged_proposal_id = ?);",
            (staged_id,),
        )
        conn.commit()

    # Clear memory cache so SQLite read occurs
    proposal_store._proposals.pop(staged_id, None)

    # 3. Attempt create-order -> Policy revalidation MUST detect budget breach and reject with HTTP 403
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        order_res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_id},
        )
        assert order_res.status_code == 403
        assert "Policy revalidation failed" in order_res.json()["detail"]
