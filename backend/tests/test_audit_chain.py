"""Automated test suite for Stage 1: Cryptographic Audit Chaining & SQLite Schema Hardening.

Covers:
1. Deterministic canonical JSON serialization and SHA-256 hash generation
2. Valid contiguous sequence numbers and unbroken prev_hash chaining from GENESIS_HASH
3. SQLite engine triggers preventing UPDATE and DELETE on audit_events
4. Detection of payload modifications (tamper-evidence)
5. Detection of broken previous hash links
6. Detection of deleted records (sequence gaps)
7. Detection of reordered events
8. High-concurrency multi-threaded insertions without sequence or hash divergence
9. Safe migration of legacy unchained records to cryptographic hash chain
10. End-to-end API verification via GET /api/v1/audit/integrity
"""

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import (
    GENESIS_HASH,
    compute_canonical_event_hash,
    get_db_connection,
    init_db,
    record_audit_event,
    record_human_approval,
    verify_audit_integrity,
    _migrate_audit_events_if_needed,
)

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Creates a temporary, isolated SQLite database for each test."""
    db_file = tmp_path / "test_trustgate_chain.db"
    init_db(db_file)
    return db_file


# -------------------------------------------------------------------------
# Test 1: Canonical JSON Serialization Determinism
# -------------------------------------------------------------------------

def test_canonical_json_serialization_determinism():
    """Verifies that dictionary key order or whitespace differences produce identical hashes."""
    details_variant_a = {
        "zeta": 100,
        "alpha": "value_a",
        "nested": {"beta": True, "gamma": 42.5},
    }
    details_variant_b = {
        "alpha": "value_a",
        "nested": {"gamma": 42.5, "beta": True},
        "zeta": 100,
    }

    hash_a = compute_canonical_event_hash(
        sequence_number=1,
        prev_hash=GENESIS_HASH,
        event_id="evt_canonical_01",
        transaction_id="tx_01",
        event_type="TEST_EVENT",
        status="SUCCESS",
        details=details_variant_a,
        timestamp="2026-11-09T12:00:00Z",
    )

    hash_b = compute_canonical_event_hash(
        sequence_number=1,
        prev_hash=GENESIS_HASH,
        event_id="evt_canonical_01",
        transaction_id="tx_01",
        event_type="TEST_EVENT",
        status="SUCCESS",
        details=details_variant_b,
        timestamp="2026-11-09T12:00:00Z",
    )

    assert hash_a == hash_b, "Canonical JSON hashing must be invariant to dictionary key order."
    assert len(hash_a) == 64, "SHA-256 hash digest must be exactly 64 hex characters."


# -------------------------------------------------------------------------
# Test 2: Genesis Hash and First Event Chaining
# -------------------------------------------------------------------------

def test_genesis_and_first_event_chaining(temp_db: Path):
    """Verifies that the very first event in an empty database links to GENESIS_HASH at sequence #1."""
    event = record_audit_event(
        transaction_id="tx_genesis_test",
        event_type="MANDATE_CREATED",
        stage="MANDATE",
        status="ACTIVE",
        details={"max_amount": 100.0, "currency": "USD"},
        db_file=temp_db,
    )

    assert event["sequence_number"] == 1
    assert event["prev_hash"] == GENESIS_HASH
    assert len(event["event_hash"]) == 64

    # Verify integrity of single-event chain
    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] == 1
    assert integrity["last_event_hash"] == event["event_hash"]
    assert integrity["first_invalid_sequence"] is None


# -------------------------------------------------------------------------
# Test 3: Multi-Event Sequential Hash Chaining
# -------------------------------------------------------------------------

def test_valid_sequential_hash_chain(temp_db: Path):
    """Verifies that multiple sequential events link deterministically from predecessors."""
    e1 = record_audit_event(
        transaction_id="tx_seq_test",
        event_type="MANDATE_CREATED",
        stage="MANDATE",
        status="ACTIVE",
        details={"step": 1},
        db_file=temp_db,
    )
    e2 = record_audit_event(
        transaction_id="tx_seq_test",
        event_type="PROPOSAL_STAGED",
        stage="PROPOSAL",
        status="STAGED",
        details={"step": 2},
        db_file=temp_db,
    )
    e3 = record_audit_event(
        transaction_id="tx_seq_test",
        event_type="POLICY_EVALUATION_PASSED",
        stage="POLICY",
        status="APPROVED",
        details={"step": 3},
        db_file=temp_db,
    )

    assert e1["sequence_number"] == 1
    assert e1["prev_hash"] == GENESIS_HASH

    assert e2["sequence_number"] == 2
    assert e2["prev_hash"] == e1["event_hash"]

    assert e3["sequence_number"] == 3
    assert e3["prev_hash"] == e2["event_hash"]

    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] == 3
    assert integrity["last_event_hash"] == e3["event_hash"]


# -------------------------------------------------------------------------
# Test 4: SQLite UPDATE Trigger Prevents Modifications
# -------------------------------------------------------------------------

def test_sqlite_update_trigger_blocks_tampering(temp_db: Path):
    """Verifies that SQLite engine trigger trg_audit_no_update blocks any UPDATE query."""
    record_audit_event(
        transaction_id="tx_update_test",
        event_type="MANDATE_CREATED",
        stage="MANDATE",
        status="ACTIVE",
        details={"allowed_amount": 50.0},
        db_file=temp_db,
    )

    with get_db_connection(temp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute("UPDATE audit_events SET status = 'TAMPERED' WHERE sequence_number = 1;")
        assert "SECURITY VIOLATION: audit_events table is append-only" in str(exc_info.value)


# -------------------------------------------------------------------------
# Test 5: SQLite DELETE Trigger Prevents Deletions
# -------------------------------------------------------------------------

def test_sqlite_delete_trigger_blocks_deletion(temp_db: Path):
    """Verifies that SQLite engine trigger trg_audit_no_delete blocks any DELETE query."""
    record_audit_event(
        transaction_id="tx_delete_test",
        event_type="MANDATE_CREATED",
        stage="MANDATE",
        status="ACTIVE",
        details={"allowed_amount": 50.0},
        db_file=temp_db,
    )

    with get_db_connection(temp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            conn.execute("DELETE FROM audit_events WHERE sequence_number = 1;")
        assert "SECURITY VIOLATION: audit_events table is append-only" in str(exc_info.value)


# -------------------------------------------------------------------------
# Test 6: Tamper Detection - Modified Payload
# -------------------------------------------------------------------------

def test_tamper_detection_modified_payload(temp_db: Path):
    """Verifies verify_audit_integrity() pinpoints modified payloads if triggers are dropped."""
    record_audit_event(
        transaction_id="tx_payload_tamper",
        event_type="EVENT_1",
        stage="STAGE_1",
        status="OK",
        details={"amount": 10.0},
        db_file=temp_db,
    )
    e2 = record_audit_event(
        transaction_id="tx_payload_tamper",
        event_type="EVENT_2",
        stage="STAGE_2",
        status="OK",
        details={"amount": 20.0},
        db_file=temp_db,
    )
    record_audit_event(
        transaction_id="tx_payload_tamper",
        event_type="EVENT_3",
        stage="STAGE_3",
        status="OK",
        details={"amount": 30.0},
        db_file=temp_db,
    )

    # Simulate hostile administrator modifying raw payload in sequence #2
    with get_db_connection(temp_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute(
            "UPDATE audit_events SET details = ? WHERE sequence_number = 2;",
            (json.dumps({"amount": 99999.0}),),
        )
        conn.commit()

    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is False
    assert integrity["first_invalid_sequence"] == 2
    assert integrity["first_invalid_event_id"] == e2["event_id"]
    assert "Tampered record detected at sequence 2" in integrity["failure_reason"]
    assert "canonical SHA-256 digest" in integrity["failure_reason"]


# -------------------------------------------------------------------------
# Test 7: Tamper Detection - Broken Previous Hash Link
# -------------------------------------------------------------------------

def test_tamper_detection_broken_prev_hash(temp_db: Path):
    """Verifies verify_audit_integrity() pinpoints broken prev_hash links."""
    record_audit_event(
        transaction_id="tx_link_tamper",
        event_type="EVENT_1",
        stage="STAGE_1",
        status="OK",
        details={},
        db_file=temp_db,
    )
    e2 = record_audit_event(
        transaction_id="tx_link_tamper",
        event_type="EVENT_2",
        stage="STAGE_2",
        status="OK",
        details={},
        db_file=temp_db,
    )

    # Corrupt prev_hash of sequence 2
    with get_db_connection(temp_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute(
            "UPDATE audit_events SET prev_hash = ? WHERE sequence_number = 2;",
            ("badhash00000000000000000000000000000000000000000000000000000000",),
        )
        conn.commit()

    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is False
    assert integrity["first_invalid_sequence"] == 2
    assert integrity["first_invalid_event_id"] == e2["event_id"]
    assert "Broken hash link at sequence 2" in integrity["failure_reason"]


# -------------------------------------------------------------------------
# Test 8: Tamper Detection - Deleted Record / Sequence Gap
# -------------------------------------------------------------------------

def test_tamper_detection_deleted_record_gap(temp_db: Path):
    """Verifies verify_audit_integrity() detects deleted records causing sequence gap."""
    record_audit_event(transaction_id="tx_del", event_type="E1", stage="S1", status="OK", details={}, db_file=temp_db)
    e2 = record_audit_event(transaction_id="tx_del", event_type="E2", stage="S2", status="OK", details={}, db_file=temp_db)
    e3 = record_audit_event(transaction_id="tx_del", event_type="E3", stage="S3", status="OK", details={}, db_file=temp_db)

    # Hostile administrator deletes sequence 2
    with get_db_connection(temp_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete;")
        conn.execute("DELETE FROM audit_events WHERE sequence_number = 2;")
        conn.commit()

    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is False
    assert integrity["first_invalid_sequence"] == 3
    assert integrity["first_invalid_event_id"] == e3["event_id"]
    assert "Sequence discontinuity detected at sequence 3" in integrity["failure_reason"]


# -------------------------------------------------------------------------
# Test 9: Tamper Detection - Reordered Records
# -------------------------------------------------------------------------

def test_tamper_detection_reordered_records(temp_db: Path):
    """Verifies verify_audit_integrity() detects sequence disruption when records are swapped."""
    record_audit_event(transaction_id="tx_reorder", event_type="E1", stage="S1", status="OK", details={}, db_file=temp_db)
    record_audit_event(transaction_id="tx_reorder", event_type="E2", stage="S2", status="OK", details={}, db_file=temp_db)

    # Swap sequence numbers
    with get_db_connection(temp_db) as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        conn.execute("UPDATE audit_events SET sequence_number = 999 WHERE sequence_number = 1;")
        conn.execute("UPDATE audit_events SET sequence_number = 1 WHERE sequence_number = 2;")
        conn.execute("UPDATE audit_events SET sequence_number = 2 WHERE sequence_number = 999;")
        conn.commit()

    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is False
    assert integrity["first_invalid_sequence"] == 1
    # Recalculated hash fails because sequence 1 now has sequence 2's data
    assert "Tampered record detected" in integrity["failure_reason"] or "Broken hash link" in integrity["failure_reason"]


# -------------------------------------------------------------------------
# Test 10: Concurrent Multi-Threaded Insertions
# -------------------------------------------------------------------------

def test_concurrent_insertions_thread_safety(temp_db: Path):
    """Verifies that high concurrency inserts never diverge sequence numbers or break hashes."""
    total_concurrent_events = 25

    def worker_insert(worker_id: int):
        return record_audit_event(
            transaction_id=f"tx_concurrent_{worker_id}",
            event_type="CONCURRENT_TASK",
            stage="TEST",
            status="SUCCESS",
            details={"worker_id": worker_id},
            db_file=temp_db,
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_insert, i) for i in range(total_concurrent_events)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == total_concurrent_events

    # Verify that sequence numbers are strictly 1 through total_concurrent_events
    seq_numbers = sorted([r["sequence_number"] for r in results])
    assert seq_numbers == list(range(1, total_concurrent_events + 1))

    # Verify the entire chain is cryptographically intact
    integrity = verify_audit_integrity(temp_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] == total_concurrent_events
    assert integrity["first_invalid_sequence"] is None


# -------------------------------------------------------------------------
# Test 11: Migration Backfills Historical Records Safely
# -------------------------------------------------------------------------

def test_migration_backfills_historical_records(tmp_path: Path):
    """Verifies that legacy unchained databases are safely migrated and backfilled."""
    legacy_db = tmp_path / "legacy_trustgate.db"

    # Create unhardened legacy audit table
    with sqlite3.connect(str(legacy_db)) as conn:
        conn.execute("""
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                linked_mandate_id TEXT,
                linked_proposal_id TEXT,
                linked_evaluation_id TEXT,
                linked_paypal_order_id TEXT,
                linked_capture_id TEXT,
                details TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)
        # Insert 3 legacy events
        conn.execute("""
            INSERT INTO audit_events VALUES
            ('evt_leg_1', 'tx_leg', 'MANDATE_CREATED', 'MANDATE', 'ACTIVE', NULL, NULL, NULL, NULL, NULL, '{"note": 1}', 'user', '2026-11-09T01:00:00Z'),
            ('evt_leg_2', 'tx_leg', 'PROPOSAL_STAGED', 'PROPOSAL', 'STAGED', NULL, NULL, NULL, NULL, NULL, '{"note": 2}', 'user', '2026-11-09T01:05:00Z'),
            ('evt_leg_3', 'tx_leg', 'ORDER_CREATED', 'ORDER', 'CREATED', NULL, NULL, NULL, 'order_123', NULL, '{"note": 3}', 'user', '2026-11-09T01:10:00Z');
        """)
        conn.commit()

    # Run migration
    init_db(legacy_db)

    # Verify all 3 records preserved and cryptographically chained
    integrity = verify_audit_integrity(legacy_db)
    assert integrity["is_valid"] is True
    assert integrity["total_events"] == 3

    with get_db_connection(legacy_db) as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY sequence_number ASC;").fetchall()
        assert len(rows) == 3
        assert rows[0]["sequence_number"] == 1
        assert rows[0]["prev_hash"] == GENESIS_HASH
        assert rows[1]["sequence_number"] == 2
        assert rows[1]["prev_hash"] == rows[0]["event_hash"]
        assert rows[2]["sequence_number"] == 3
        assert rows[2]["prev_hash"] == rows[1]["event_hash"]


# -------------------------------------------------------------------------
# Test 12: GET /api/v1/audit/integrity Endpoint
# -------------------------------------------------------------------------

def test_api_audit_integrity_endpoint():
    """Verifies that the /api/v1/audit/integrity endpoint returns HTTP 200 with validation."""
    response = client.get("/api/v1/audit/integrity")
    assert response.status_code == 200
    data = response.json()
    assert "is_valid" in data
    assert "total_events" in data
    assert "genesis_hash" in data
    assert data["genesis_hash"] == GENESIS_HASH
    assert "tamper_evident_guarantee" in data
    assert data["is_valid"] is True

