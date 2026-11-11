"""Phase 4.3: Audit Log & Ledger Synchronization Test Suite.

Verifies:
1. Canonical audit event retrieval from SQLite ledger.
2. Chronological ordering (DESC and ASC) and sequence monotonicity.
3. Pagination (limit and offset) and total matching counts.
4. Multi-parameter filtering (by transaction_id, event_type, stage, status).
5. Single event lookup by event_id (200 OK and 404 Not Found).
6. Cryptographic SHA-256 hash-chain verification on clean ledger.
7. Mathematical detection of tampering / sequence violation.
8. Append-only trigger enforcement blocking UPDATE and DELETE.
9. Empty audit ledger handling.
10. Invalid filter and pagination parameter handling (422 validation).
"""

import json
import sqlite3
import pytest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import (
    init_db,
    get_db_connection,
    record_audit_event,
    record_human_approval,
    verify_audit_integrity,
    get_audit_events,
    count_audit_events,
    get_audit_event_by_id,
)
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store

client = TestClient(app)


@pytest.fixture
def isolated_db(tmp_path):
    """Provides a fresh isolated database for audit synchronization tests."""
    db_file = tmp_path / "test_audit_sync.db"
    init_db(db_file)
    return db_file


def _stage_helper(db_file: Path, idx: int) -> str:
    """Helper to stage a genuine proposal in the isolated database."""
    staged_id = f"stg_sync_{idx}_{uuid.uuid4().hex[:6]}"
    mandate = PurchaseMandate(
        max_amount=100.0 + idx * 10,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )
    product = DiscoveredProduct(
        product_id=f"prod_sync_{idx}",
        name=f"Sync Item {idx}",
        description="Test sync item",
        category="Electronics",
        price=50.0 + idx * 5,
        currency="USD",
        condition="new",
        merchant_name="Official Merchant",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="catalog",
        is_demo_data=True,
        demo_notice="Test item",
    )
    tx = ProposedTransaction(
        product_name=product.name,
        product_price=product.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=product.price,
        currency="USD",
        merchant_name=product.merchant_name,
        merchant_verified=True,
        product_condition=product.condition,
        add_ons=[],
    )
    eval_result = policy_engine.evaluate_mandate(mandate, tx, caller_role="human_user")
    proposal_store.save_staged_proposal(
        staged_proposal_id=staged_id,
        mandate=mandate,
        candidate=product,
        policy_evaluation=eval_result,
        user_id=f"operator_{idx}",
        db_file=db_file,
    )
    return staged_id


# -----------------------------------------------------------------------------
# 1. Audit Event Retrieval & Chronological Ordering
# -----------------------------------------------------------------------------

def test_audit_events_pagination_and_ordering(isolated_db):
    """Verifies that audit events are retrieved with correct ordering, pagination, and counts."""
    # Create 4 staged events
    tx_ids = [_stage_helper(isolated_db, i) for i in range(1, 5)]

    # 1. Descending Order (Default: Newest First)
    desc_events = get_audit_events(limit=2, offset=0, order_by="DESC", db_file=isolated_db)
    assert len(desc_events) == 2
    assert desc_events[0]["sequence_number"] > desc_events[1]["sequence_number"]

    # Offset pagination
    page_2 = get_audit_events(limit=2, offset=2, order_by="DESC", db_file=isolated_db)
    assert len(page_2) == 2
    assert desc_events[1]["sequence_number"] > page_2[0]["sequence_number"]

    # 2. Ascending Order (Oldest First)
    asc_events = get_audit_events(limit=2, offset=0, order_by="ASC", db_file=isolated_db)
    assert len(asc_events) == 2
    assert asc_events[0]["sequence_number"] < asc_events[1]["sequence_number"]
    assert asc_events[0]["sequence_number"] == 1

    # Total count
    total = count_audit_events(db_file=isolated_db)
    assert total == 4


# -----------------------------------------------------------------------------
# 2. Multi-Parameter Filtering
# -----------------------------------------------------------------------------

def test_audit_events_filtering(isolated_db):
    """Verifies filtering by transaction_id, event_type, stage, and status."""
    tx1 = _stage_helper(isolated_db, 1)
    tx2 = _stage_helper(isolated_db, 2)

    # Approve tx1 to create an APPROVAL stage event
    record_human_approval(
        transaction_id=tx1,
        user_id="operator_alice",
        policy_signature="sig_test_sync",
        approved_amount=55.0,
        currency="USD",
        db_file=isolated_db,
    )

    # Filter by transaction_id
    tx1_events = get_audit_events(transaction_id=tx1, db_file=isolated_db)
    assert len(tx1_events) == 2
    assert all(e["transaction_id"] == tx1 for e in tx1_events)

    # Filter by stage
    approval_events = get_audit_events(stage="APPROVAL", db_file=isolated_db)
    assert len(approval_events) == 1
    assert approval_events[0]["event_type"] == "HUMAN_APPROVAL_GRANTED"

    # Filter by event_type
    staged_events = get_audit_events(event_type="PROPOSAL_STAGED", db_file=isolated_db)
    assert len(staged_events) == 2

    # Filter by status
    granted_events = get_audit_events(status="GRANTED", db_file=isolated_db)
    assert len(granted_events) == 1
    assert granted_events[0]["status"] == "GRANTED"


# -----------------------------------------------------------------------------
# 3. Single Event Retrieval
# -----------------------------------------------------------------------------

def test_get_single_audit_event_lookup(isolated_db):
    """Verifies looking up a single event by event_id."""
    tx = _stage_helper(isolated_db, 1)
    events = get_audit_events(transaction_id=tx, db_file=isolated_db)
    assert len(events) >= 1
    target_event_id = events[0]["event_id"]

    # Found
    retrieved = get_audit_event_by_id(target_event_id, db_file=isolated_db)
    assert retrieved is not None
    assert retrieved["event_id"] == target_event_id
    assert retrieved["transaction_id"] == tx
    assert retrieved["sequence_number"] == events[0]["sequence_number"]
    assert retrieved["event_hash"] == events[0]["event_hash"]

    # Not found
    missing = get_audit_event_by_id("evt_nonexistent_xyz", db_file=isolated_db)
    assert missing is None


# -----------------------------------------------------------------------------
# 4. Cryptographic Hash Chain Verification on Clean and Tampered Ledgers
# -----------------------------------------------------------------------------

def test_audit_integrity_clean_and_tampered(isolated_db):
    """Verifies that uncorrupted audit ledgers pass integrity check, and tampering is pinpointed."""
    tx1 = _stage_helper(isolated_db, 1)
    _stage_helper(isolated_db, 2)
    _stage_helper(isolated_db, 3)

    # 1. Clean verification
    clean_check = verify_audit_integrity(db_file=isolated_db)
    assert clean_check["is_valid"] is True
    assert clean_check["total_events"] == 3
    assert clean_check["first_invalid_sequence"] is None
    assert clean_check["failure_reason"] is None

    # 2. Tamper: Manually modify details payload of sequence 2 in isolated SQLite DB
    # Triggers trg_audit_no_update and trg_audit_no_delete protect the table.
    # In order to simulate an external tampering/corruption event (e.g. host-level tampering),
    # drop trg_audit_no_update in this isolated test database.
    with get_db_connection(isolated_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute(
            """
            UPDATE audit_events
            SET details = ?
            WHERE sequence_number = 2;
            """,
            (json.dumps({"tampered": True, "price": 0.01}),),
        )
        conn.commit()

    # 3. Verify tampering is caught
    tampered_check = verify_audit_integrity(db_file=isolated_db)
    assert tampered_check["is_valid"] is False
    assert tampered_check["first_invalid_sequence"] == 2
    assert "Tampered record detected at sequence 2" in tampered_check["failure_reason"]
    assert "Stored event_hash does not match recalculated canonical SHA-256 digest" in tampered_check["failure_reason"]


# -----------------------------------------------------------------------------
# 5. Production Append-Only Protection Enforcement (UPDATE & DELETE Rejection)
# -----------------------------------------------------------------------------

def test_audit_events_append_only_enforcement(isolated_db):
    """Verifies that normal database operations cannot UPDATE or DELETE existing audit events.

    Production triggers trg_audit_no_update and trg_audit_no_delete must reject
    modifications with an IntegrityError containing 'SECURITY VIOLATION'.
    """
    # 1. Stage an event to create an audit record
    tx_id = _stage_helper(isolated_db, 1)
    events_before = get_audit_events(transaction_id=tx_id, db_file=isolated_db)
    assert len(events_before) == 1
    seq_num = events_before[0]["sequence_number"]

    # 2. Verify triggers are present in SQLite schema
    with get_db_connection(isolated_db) as conn:
        triggers = {
            row["name"]: row["sql"]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_events';"
            ).fetchall()
        }
        assert "trg_audit_no_update" in triggers
        assert "trg_audit_no_delete" in triggers

        # 3. Attempt UPDATE -> must be blocked by trg_audit_no_update
        with pytest.raises(sqlite3.IntegrityError, match="SECURITY VIOLATION: audit_events table is append-only. Modifying records is prohibited."):
            conn.execute(
                "UPDATE audit_events SET details = ? WHERE sequence_number = ?;",
                (json.dumps({"unauthorized": True}), seq_num),
            )

        # 4. Attempt DELETE -> must be blocked by trg_audit_no_delete
        with pytest.raises(sqlite3.IntegrityError, match="SECURITY VIOLATION: audit_events table is append-only. Deleting records is prohibited."):
            conn.execute(
                "DELETE FROM audit_events WHERE sequence_number = ?;",
                (seq_num,),
            )

    # 5. Confirm that the record remains completely intact and unaltered
    events_after = get_audit_events(transaction_id=tx_id, db_file=isolated_db)
    assert len(events_after) == 1
    assert events_after[0]["sequence_number"] == seq_num
    assert events_after[0]["details"] == events_before[0]["details"]
    assert events_after[0]["event_hash"] == events_before[0]["event_hash"]


# -----------------------------------------------------------------------------
# 6. Empty Audit Ledger Handling
# -----------------------------------------------------------------------------

def test_empty_audit_ledger_handling(isolated_db):
    """Verifies that an empty database is safely handled without errors."""
    events = get_audit_events(db_file=isolated_db)
    assert events == []

    total = count_audit_events(db_file=isolated_db)
    assert total == 0

    integrity = verify_audit_integrity(db_file=isolated_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] == 0
    assert integrity["first_invalid_sequence"] is None


# -----------------------------------------------------------------------------
# 7. API Validation and Parameter Bounds
# -----------------------------------------------------------------------------

def test_api_audit_events_endpoint_validation():
    """Verifies that FastAPI query parameters enforce valid boundaries."""
    # Limit too large (>200) -> 422
    res_large = client.get("/api/v1/audit/events?limit=250")
    assert res_large.status_code == 422

    # Negative limit (<1) -> 422
    res_neg_limit = client.get("/api/v1/audit/events?limit=0")
    assert res_neg_limit.status_code == 422

    # Negative offset (<0) -> 422
    res_neg_offset = client.get("/api/v1/audit/events?offset=-5")
    assert res_neg_offset.status_code == 422

    # Invalid order parameter -> 422
    res_inv_order = client.get("/api/v1/audit/events?order=random")
    assert res_inv_order.status_code == 422

    # Single event 404 for nonexistent ID
    res_not_found = client.get("/api/v1/audit/events/evt_does_not_exist_999")
    assert res_not_found.status_code == 404

