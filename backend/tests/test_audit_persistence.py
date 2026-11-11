"""Unit tests for Trust & Audit Layer, Persistent SQLite Storage, and Transaction Lifecycle."""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import (
    init_db,
    get_db_connection,
    record_audit_event,
    record_human_approval,
    get_audit_events,
    get_audit_summary,
    get_transaction_timeline_data,
    list_persisted_transactions,
)
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before each test."""
    init_db()
    yield


@pytest.fixture
def sample_mandate():
    return PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["laptop only"],
    )


@pytest.fixture
def sample_candidate():
    return DiscoveredProduct(
        product_id="prod_audit_test_01",
        name="Ultra Laptop Pro 14",
        description="High performance notebook",
        category="Computers",
        price=129.99,
        currency="USD",
        condition="new",
        merchant_name="Trusted Tech Direct",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="demo_fixture",
        is_demo_data=True,
        marketplace_id="demo",
        region="us",
        data_freshness="fresh",
    )


def test_database_initialization_tables():
    """Verify that all persistent tables exist in SQLite."""
    with get_db_connection() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "mandates" in tables
        assert "proposals" in tables
        assert "policy_evaluations" in tables
        assert "staged_proposals" in tables
        assert "human_approvals" in tables
        assert "orders_and_captures" in tables
        assert "audit_events" in tables


def test_staged_proposal_persists_to_sqlite(sample_mandate, sample_candidate):
    """Saving a staged proposal must persist across in-memory cache eviction."""
    staged_id = "stg_audit_test_999"

    tx = ProposedTransaction(
        product_name=sample_candidate.name,
        product_price=sample_candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=sample_candidate.price,
        currency=sample_candidate.currency,
        merchant_name=sample_candidate.merchant_name,
        merchant_verified=sample_candidate.merchant_verified,
        product_condition=sample_candidate.condition,
        add_ons=[],
    )
    evaluation = policy_engine.evaluate_mandate(sample_mandate, tx, caller_role="human_user")

    # Save to store
    record = proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=sample_mandate,
        candidate=sample_candidate,
        policy_evaluation=evaluation,
        user_id="user_tester",
    )
    assert record.staged_proposal_id == staged_id

    # Clear in-memory cache to simulate server restart
    proposal_store.clear()
    assert staged_id not in proposal_store._proposals

    # Retrieve from disk via SQLite
    reloaded = proposal_store.get_staged_proposal(staged_id)
    assert reloaded is not None
    assert reloaded.staged_proposal_id == staged_id
    assert reloaded.candidate.name == "Ultra Laptop Pro 14"
    assert reloaded.mandate.max_amount == 150.00
    assert reloaded.policy_evaluation.approved is True
    assert reloaded.policy_evaluation.policy_signature.startswith("tg_sig_")


def test_record_human_approval_persistence(sample_mandate, sample_candidate):
    """Explicit human approval must be saved into human_approvals and audit_events."""
    tx_id = "stg_approval_test_01"

    tx = ProposedTransaction(
        product_name=sample_candidate.name,
        product_price=sample_candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=sample_candidate.price,
        currency=sample_candidate.currency,
        merchant_name=sample_candidate.merchant_name,
        merchant_verified=sample_candidate.merchant_verified,
        product_condition=sample_candidate.condition,
        add_ons=[],
    )
    evaluation = policy_engine.evaluate_mandate(sample_mandate, tx, caller_role="human_user")

    proposal_store.save_staged_proposal(
        staged_proposal_id=tx_id,
        mandate=sample_mandate,
        candidate=sample_candidate,
        policy_evaluation=evaluation,
        user_id="operator_alice",
    )

    approval = record_human_approval(
        transaction_id=tx_id,
        user_id="operator_alice",
        policy_signature="tg_sig_test_signature",
        approved_amount=89.99,
        currency="USD",
        action="AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
        actor_role="human_user",
    )

    assert approval["approval_id"].startswith("appr_")
    assert approval["transaction_id"] == tx_id
    assert approval["user_id"] == "operator_alice"
    assert approval["approved_amount"] == 89.99

    # Verify present in SQLite
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM human_approvals WHERE transaction_id = ?",
            (tx_id,),
        ).fetchone()
        assert row is not None
        assert row["user_id"] == "operator_alice"
        assert row["policy_signature"] == "tg_sig_test_signature"


def test_reconstruct_transaction_lifecycle_timeline(sample_mandate, sample_candidate):
    """Reconstructing the lifecycle timeline must output all 6 stages."""
    staged_id = "stg_timeline_test_100"

    tx = ProposedTransaction(
        product_name=sample_candidate.name,
        product_price=sample_candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=sample_candidate.price,
        currency=sample_candidate.currency,
        merchant_name=sample_candidate.merchant_name,
        merchant_verified=sample_candidate.merchant_verified,
        product_condition=sample_candidate.condition,
        add_ons=[],
    )
    evaluation = policy_engine.evaluate_mandate(sample_mandate, tx, caller_role="human_user")

    proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=sample_mandate,
        candidate=sample_candidate,
        policy_evaluation=evaluation,
        user_id="user_timeline_test",
    )

    # Record human approval
    record_human_approval(
        transaction_id=staged_id,
        user_id="user_timeline_test",
        policy_signature=evaluation.policy_signature,
        approved_amount=sample_candidate.price,
        currency=sample_candidate.currency,
    )

    # Link PayPal Sandbox order
    test_order_id = "PAYPAL-ORDER-TEST-1234"
    proposal_store.link_paypal_order(staged_id, test_order_id)

    # Fetch reconstructed timeline
    timeline = get_transaction_timeline_data(staged_id)
    assert timeline is not None
    assert timeline["transaction_id"] == staged_id
    assert timeline["current_status"] in ("ORDER_CREATED", "STAGED")

    # Check 6 stages
    stage_keys = [s["stage_key"] for s in timeline["stages"]]
    assert stage_keys == ["mandate", "proposal", "policy", "approval", "order", "receipt"]

    # Verify stage statuses
    mandate_stage = timeline["stages"][0]
    assert mandate_stage["status"] == "COMPLETED"

    policy_stage = timeline["stages"][2]
    assert policy_stage["status"] == "COMPLETED"
    assert policy_stage["details"]["policy_signature"].startswith("tg_sig_")

    approval_stage = timeline["stages"][3]
    assert approval_stage["status"] == "COMPLETED"
    assert approval_stage["details"]["actor_role"] == "human_user"

    order_stage = timeline["stages"][4]
    assert order_stage["status"] == "COMPLETED"
    assert order_stage["details"]["order_id"] == test_order_id


def test_api_audit_endpoints(sample_mandate, sample_candidate):
    """Test API endpoints /audit/events, /audit/timeline, /audit/transactions, and /audit/summary."""
    staged_id = "stg_api_audit_endpoint_test"

    tx = ProposedTransaction(
        product_name=sample_candidate.name,
        product_price=sample_candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=sample_candidate.price,
        currency=sample_candidate.currency,
        merchant_name=sample_candidate.merchant_name,
        merchant_verified=sample_candidate.merchant_verified,
        product_condition=sample_candidate.condition,
        add_ons=[],
    )
    evaluation = policy_engine.evaluate_mandate(sample_mandate, tx, caller_role="human_user")

    proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=sample_mandate,
        candidate=sample_candidate,
        policy_evaluation=evaluation,
        user_id="user_api_tester",
    )

    # 1. GET /api/v1/audit/events
    res_events = client.get("/api/v1/audit/events")
    assert res_events.status_code == 200
    events_data = res_events.json()
    assert "events" in events_data
    assert events_data["count"] >= 1

    # Filtered by transaction_id
    res_filtered = client.get(f"/api/v1/audit/events?transaction_id={staged_id}")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert any(e["transaction_id"] == staged_id for e in filtered_data["events"])

    # 2. GET /api/v1/audit/timeline/{transaction_id}
    res_timeline = client.get(f"/api/v1/audit/timeline/{staged_id}")
    assert res_timeline.status_code == 200
    tl = res_timeline.json()
    assert tl["transaction_id"] == staged_id
    assert len(tl["stages"]) == 6

    # 404 for non-existent transaction
    res_404 = client.get("/api/v1/audit/timeline/stg_does_not_exist")
    assert res_404.status_code == 404

    # 3. GET /api/v1/audit/transactions
    res_txs = client.get("/api/v1/audit/transactions")
    assert res_txs.status_code == 200
    txs_data = res_txs.json()
    assert "transactions" in txs_data
    assert any(t["transaction_id"] == staged_id for t in txs_data["transactions"])

    # 4. GET /api/v1/audit/summary
    res_sum = client.get("/api/v1/audit/summary")
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert sum_data["persisted"] is True
    assert "SQLite Persistent" in sum_data["storage_engine"]
    assert sum_data["total_audit_events"] > 0

