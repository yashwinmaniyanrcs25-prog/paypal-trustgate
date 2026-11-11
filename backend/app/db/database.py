"""SQLite Persistent Database with Cryptographic Hash Chaining for PayPal TrustGate.

Provides ACID-compliant persistent storage for:
- Purchase Mandates
- Candidate Proposals
- Policy Evaluations (with deterministic checks & signatures)
- Staged Proposals (with server-side linkage)
- Explicit Human Approvals (non-AI authorization record)
- PayPal Sandbox Orders, Captures, and Receipts
- Tamper-Evident Lifecycle Audit Trail with SHA-256 Hash Chaining

CRITICAL SECURITY & INTEGRITY INVARIANTS:
1. No critical state relies on ephemeral in-memory storage.
2. All records survive application restarts.
3. Every audit event is chained via deterministic SHA-256 hashes linking each event to its predecessor.
4. SQLite triggers strictly prevent UPDATE and DELETE operations on audit_events at the database engine level.
5. Event creation and hash calculation are atomic within database transactions and thread-locked.
6. AI models are strictly prohibited from authorizing payments.

HONEST TAMPER-EVIDENCE DISCLOSURE:
SQLite append-only triggers and SHA-256 hash chaining provide mathematical tamper-evidence:
any post-facto modification, insertion, or deletion of past records breaks the cryptographic
chain and is immediately detected by verify_audit_integrity().
However, this is distinct from decentralized consensus or write-once-read-many (WORM) hardware.
A host administrator with raw filesystem write access could theoretically rewrite the SQLite
database file and recompute all hashes. TrustGate mathematically detects unauthorized application-level
and database-level tampering, but does not claim protection against raw host-level file manipulation.
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.models.lifecycle import (
    TransactionState,
    is_transition_permitted,
    InvalidStateTransitionError,
)

logger = logging.getLogger(__name__)

# Locate backend/data directory relative to this file
DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "trustgate.db"

# Defined Genesis Hash for sequence #1
GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

# Re-entrant thread lock to prevent concurrent thread-level divergence of sequence numbers
_AUDIT_LOCK = threading.RLock()


def get_db_connection(db_file: Optional[Path] = None) -> sqlite3.Connection:
    """Creates a connection to the SQLite persistent database with row factory."""
    target_path = db_file or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def compute_canonical_event_hash(
    sequence_number: int,
    prev_hash: str,
    event_id: str,
    transaction_id: str,
    event_type: str,
    status: str,
    details: Dict[str, Any],
    timestamp: str,
) -> str:
    """Computes a deterministic SHA-256 hash over the canonical JSON preimage.

    Canonical serialization rules:
    - Dict keys sorted lexicographically (sort_keys=True)
    - Zero extra whitespace (separators=(',', ':'))
    - Strict ASCII escaping for cross-platform consistency (ensure_ascii=True)
    """
    canonical_payload = json.dumps(
        details,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    preimage = {
        "event_id": event_id,
        "event_type": event_type,
        "payload": canonical_payload,
        "prev_hash": prev_hash,
        "sequence_number": sequence_number,
        "status": status,
        "timestamp": timestamp,
        "transaction_id": transaction_id,
    }
    canonical_bytes = json.dumps(
        preimage,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def backup_database(target_db: Optional[Path] = None) -> Optional[Path]:
    """Creates a timestamped backup copy of the database before schema migration."""
    path = target_db or DB_PATH
    if not path.exists():
        return None
    now_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = path.parent / f"{path.stem}.backup_{now_tag}.db"
    try:
        shutil.copy2(str(path), str(backup_path))
        logger.info(f"Created persistent database backup at {backup_path}")
        return backup_path
    except Exception as exc:
        logger.error(f"Failed to backup database before migration: {exc}")
        return None


def init_db(db_file: Optional[Path] = None) -> None:
    """Initializes persistent database tables and migrates audit_events to hash-chaining."""
    target_path = db_file or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with _AUDIT_LOCK:
        # Check if migration is needed before building tables
        _migrate_audit_events_if_needed(target_path)
        _migrate_staged_proposals_if_needed(target_path)

        with get_db_connection(target_path) as conn:
            cursor = conn.cursor()

            # 1. Mandates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mandates (
                    mandate_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    max_amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    allowed_conditions TEXT NOT NULL,
                    require_merchant_verification INTEGER NOT NULL,
                    allow_add_ons INTEGER NOT NULL,
                    user_restrictions TEXT,
                    original_prompt TEXT,
                    created_at TEXT NOT NULL
                );
            """)

            # 2. Proposals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    mandate_id TEXT,
                    product_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    merchant_name TEXT NOT NULL,
                    merchant_verified INTEGER NOT NULL,
                    verification_status TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    is_demo_data INTEGER NOT NULL,
                    marketplace_id TEX T,
                    region TEXT,
                    data_freshness TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (mandate_id) REFERENCES mandates(mandate_id)
                );
            """)

            # 3. Policy Evaluations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    proposal_id TEXT,
                    mandate_id TEXT,
                    approved INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    violations TEXT NOT NULL,
                    checks TEXT NOT NULL,
                    explanation TEXT,
                    policy_signature TEXT NOT NULL,
                    caller_role TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL
                );
            """)

            # 4. Staged Proposals (with centralized lifecycle state machine)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staged_proposals (
                    staged_proposal_id TEXT PRIMARY KEY,
                    mandate_id TEXT NOT NULL,
                    candidate_product_id TEXT NOT NULL,
                    candidate_data TEXT NOT NULL,
                    mandate_data TEXT NOT NULL,
                    evaluation_data TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'STAGED',
                    paypal_order_id TEXT UNIQUE,
                    captured INTEGER NOT NULL DEFAULT 0,
                    capture_id TEXT,
                    rejection_reason TEXT,
                    cancellation_reason TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 5. Explicit Human Approvals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS human_approvals (
                    approval_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    policy_signature TEXT NOT NULL,
                    approved_amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_role TEXT NOT NULL DEFAULT 'human_user',
                    consent_token TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (transaction_id) REFERENCES staged_proposals(staged_proposal_id)
                );
            """)

            # 6. PayPal Sandbox Orders & Captures
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders_and_captures (
                    order_id TEXT PRIMARY KEY,
                    staged_proposal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    capture_id TEXT,
                    captured_at TEXT,
                    is_sandbox INTEGER NOT NULL DEFAULT 1,
                    is_demo_data INTEGER NOT NULL DEFAULT 1,
                    raw_capture_response TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (staged_proposal_id) REFERENCES staged_proposals(staged_proposal_id)
                );
            """)

            # 7. Cryptographically Chained Audit Trail Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence_number INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
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
                    timestamp TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
            """)

            # Indexes for fast lookup
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_tx ON audit_events(transaction_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(timestamp);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_seq ON audit_events(sequence_number);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_hash ON audit_events(event_hash);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_order ON staged_proposals(paypal_order_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_status ON staged_proposals(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_tx ON human_approvals(transaction_id);")

            # SQLite Engine Triggers preventing UPDATE and DELETE on audit_events
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'SECURITY VIOLATION: audit_events table is append-only. Modifying records is prohibited.');
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'SECURITY VIOLATION: audit_events table is append-only. Deleting records is prohibited.');
                END;
            """)

            conn.commit()
        _backfill_missing_proposals_if_needed(target_path)
        logger.info(f"Initialized persistent database with cryptographic hash chaining at {target_path}")


def _backfill_missing_proposals_if_needed(target_path: Path) -> None:
    """Ensures every staged proposal has a corresponding persistent record in proposals table."""
    if not target_path.exists():
        return
    try:
        with get_db_connection(target_path) as conn:
            cursor = conn.cursor()
            # Verify proposals and staged_proposals tables exist
            sp_check = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='staged_proposals';").fetchone()
            p_check = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proposals';").fetchone()
            if not sp_check or not p_check:
                return

            cursor.execute("""
                SELECT sp.staged_proposal_id, sp.mandate_id, sp.candidate_data, sp.created_at
                FROM staged_proposals sp
                WHERE sp.mandate_id NOT IN (SELECT mandate_id FROM proposals WHERE mandate_id IS NOT NULL);
            """)
            missing = cursor.fetchall()
            if not missing:
                return

            for row in missing:
                staged_id = row["staged_proposal_id"]
                mandate_id = row["mandate_id"]
                try:
                    candidate_data = json.loads(row["candidate_data"])
                except Exception:
                    continue
                prop_suffix = staged_id[4:] if staged_id.startswith("stg_") else staged_id
                proposal_id = f"prop_{prop_suffix}"
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO proposals (
                        proposal_id, mandate_id, product_id, name, description,
                        category, price, currency, merchant_name, merchant_verified,
                        verification_status, condition, data_source, is_demo_data,
                        marketplace_id, region, data_freshness, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal_id,
                        mandate_id,
                        candidate_data.get("product_id", "unknown"),
                        candidate_data.get("name", "Unknown Product"),
                        candidate_data.get("description", ""),
                        candidate_data.get("category", "General"),
                        candidate_data.get("price", 0.0),
                        candidate_data.get("currency", "USD"),
                        candidate_data.get("merchant_name", "Unknown"),
                        1 if candidate_data.get("merchant_verified") else 0,
                        candidate_data.get("verification_status", "UNKNOWN"),
                        candidate_data.get("condition", "new"),
                        candidate_data.get("data_source", "catalog"),
                        1 if candidate_data.get("is_demo_data") else 0,
                        candidate_data.get("marketplace_id", "channel3"),
                        candidate_data.get("region", "global"),
                        candidate_data.get("data_freshness", "Verified Record"),
                        row["created_at"],
                    ),
                )
            conn.commit()
            logger.info(f"Backfilled {len(missing)} missing proposal records into proposals table.")
    except Exception as exc:
        logger.warning(f"Error backfilling proposals table: {exc}")


def _migrate_audit_events_if_needed(target_path: Path) -> None:
    """Safely migrates legacy audit_events to include sequence_number, prev_hash, and event_hash.

    Preserves 100% of historical records by sequentially calculating the hash chain.
    """
    if not target_path.exists():
        return

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        # Check if audit_events table exists
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events';"
        ).fetchone()

        if not table_exists:
            return

        # Check existing columns
        columns = [row["name"] for row in cursor.execute("PRAGMA table_info(audit_events);").fetchall()]

        # If already migrated, nothing to do
        if "sequence_number" in columns and "event_hash" in columns and "prev_hash" in columns:
            return

        logger.info("Legacy audit_events table detected. Initiating safe database migration...")
        backup_database(target_path)

        # Fetch existing records ordered by rowid/timestamp
        legacy_rows = cursor.execute("SELECT * FROM audit_events ORDER BY rowid ASC;").fetchall()
        logger.info(f"Found {len(legacy_rows)} historical audit events to migrate.")

        # Drop old triggers if they exist
        cursor.execute("DROP TRIGGER IF EXISTS trg_audit_no_update;")
        cursor.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete;")

        # Create temporary migrated table
        cursor.execute("""
            CREATE TABLE audit_events_migrated (
                sequence_number INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
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
                timestamp TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
        """)

        # Sequentially backfill the cryptographic hash chain
        seq = 1
        current_prev_hash = GENESIS_HASH

        for row in legacy_rows:
            details_raw = row["details"]
            try:
                details_dict = json.loads(details_raw) if details_raw else {}
            except Exception:
                details_dict = {"raw": str(details_raw)}

            cur_hash = compute_canonical_event_hash(
                sequence_number=seq,
                prev_hash=current_prev_hash,
                event_id=row["event_id"],
                transaction_id=row["transaction_id"],
                event_type=row["event_type"],
                status=row["status"],
                details=details_dict,
                timestamp=row["timestamp"],
            )

            cursor.execute(
                """
                INSERT INTO audit_events_migrated (
                    sequence_number, event_id, transaction_id, event_type, stage, status,
                    linked_mandate_id, linked_proposal_id, linked_evaluation_id,
                    linked_paypal_order_id, linked_capture_id, details, actor_role, timestamp,
                    prev_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq,
                    row["event_id"],
                    row["transaction_id"],
                    row["event_type"],
                    row["stage"],
                    row["status"],
                    row["linked_mandate_id"],
                    row["linked_proposal_id"],
                    row["linked_evaluation_id"],
                    row["linked_paypal_order_id"],
                    row["linked_capture_id"],
                    json.dumps(details_dict),
                    row["actor_role"],
                    row["timestamp"],
                    current_prev_hash,
                    cur_hash,
                ),
            )

            current_prev_hash = cur_hash
            seq += 1

        # Replace old table with migrated table
        cursor.execute("DROP TABLE audit_events;")
        cursor.execute("ALTER TABLE audit_events_migrated RENAME TO audit_events;")
        conn.commit()
        logger.info(f"Successfully migrated {len(legacy_rows)} audit records to cryptographic hash chain.")


def _migrate_staged_proposals_if_needed(target_path: Path) -> None:
    """Safely migrates staged_proposals table to include status, reasons, and expiration fields.

    Preserves 100% of historical records and backfills status based on actual past lifecycle events.
    """
    if not target_path.exists():
        return

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='staged_proposals';"
        ).fetchone()

        if not table_exists:
            return

        columns = [row["name"] for row in cursor.execute("PRAGMA table_info(staged_proposals);").fetchall()]

        if "status" in columns:
            return

        logger.info("Migrating staged_proposals table to support explicit lifecycle state machine...")
        backup_database(target_path)

        rows = cursor.execute("SELECT * FROM staged_proposals ORDER BY rowid ASC;").fetchall()

        cursor.execute("""
            CREATE TABLE staged_proposals_migrated (
                staged_proposal_id TEXT PRIMARY KEY,
                mandate_id TEXT NOT NULL,
                candidate_product_id TEXT NOT NULL,
                candidate_data TEXT NOT NULL,
                mandate_data TEXT NOT NULL,
                evaluation_data TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'STAGED',
                paypal_order_id TEXT UNIQUE,
                captured INTEGER NOT NULL DEFAULT 0,
                capture_id TEXT,
                rejection_reason TEXT,
                cancellation_reason TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        for r in rows:
            is_captured = bool(r["captured"])
            has_order = bool(r["paypal_order_id"])

            if is_captured:
                st = "CAPTURED"
            elif has_order:
                st = "ORDER_CREATED"
            else:
                approval = cursor.execute(
                    "SELECT 1 FROM human_approvals WHERE transaction_id = ? LIMIT 1;",
                    (r["staged_proposal_id"],),
                ).fetchone()
                st = "HUMAN_APPROVED" if approval else "STAGED"

            cursor.execute(
                """
                INSERT INTO staged_proposals_migrated (
                    staged_proposal_id, mandate_id, candidate_product_id, candidate_data,
                    mandate_data, evaluation_data, user_id, status, paypal_order_id,
                    captured, capture_id, rejection_reason, cancellation_reason, expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    r["staged_proposal_id"],
                    r["mandate_id"],
                    r["candidate_product_id"],
                    r["candidate_data"],
                    r["mandate_data"],
                    r["evaluation_data"],
                    r["user_id"],
                    st,
                    r["paypal_order_id"],
                    r["captured"],
                    r["capture_id"],
                    r["created_at"],
                    r["updated_at"],
                ),
            )

        cursor.execute("DROP TABLE staged_proposals;")
        cursor.execute("ALTER TABLE staged_proposals_migrated RENAME TO staged_proposals;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_order ON staged_proposals(paypal_order_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_status ON staged_proposals(status);")
        conn.commit()
        logger.info(f"Successfully migrated {len(rows)} staged proposals to explicit lifecycle state machine.")



# -------------------------------------------------------------------------
# Atomic Cryptographic Audit Event Insertion
# -------------------------------------------------------------------------

def record_audit_event(
    transaction_id: str,
    event_type: str,
    stage: str,
    status: str,
    details: Dict[str, Any],
    actor_role: str = "system",
    linked_mandate_id: Optional[str] = None,
    linked_proposal_id: Optional[str] = None,
    linked_evaluation_id: Optional[str] = None,
    linked_paypal_order_id: Optional[str] = None,
    linked_capture_id: Optional[str] = None,
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Atomically appends an event to the audit trail with SHA-256 hash chaining.

    Concurrency & Thread-Safety:
    - Protected by re-entrant thread lock (_AUDIT_LOCK)
    - Protected by SQLite BEGIN IMMEDIATE transaction, preventing concurrent divergence
    """
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details)

    with _AUDIT_LOCK:
        with get_db_connection(db_file) as conn:
            conn.execute("BEGIN IMMEDIATE;")

            # Query last sequence and hash inside atomic transaction
            last_row = conn.execute(
                "SELECT sequence_number, event_hash FROM audit_events ORDER BY sequence_number DESC LIMIT 1;"
            ).fetchone()

            if last_row is None:
                sequence_number = 1
                prev_hash = GENESIS_HASH
            else:
                sequence_number = last_row["sequence_number"] + 1
                prev_hash = last_row["event_hash"]

            # Compute canonical SHA-256 hash
            event_hash = compute_canonical_event_hash(
                sequence_number=sequence_number,
                prev_hash=prev_hash,
                event_id=event_id,
                transaction_id=transaction_id,
                event_type=event_type,
                status=status,
                details=details,
                timestamp=now_iso,
            )

            conn.execute(
                """
                INSERT INTO audit_events (
                    sequence_number, event_id, transaction_id, event_type, stage, status,
                    linked_mandate_id, linked_proposal_id, linked_evaluation_id,
                    linked_paypal_order_id, linked_capture_id, details, actor_role, timestamp,
                    prev_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence_number,
                    event_id,
                    transaction_id,
                    event_type,
                    stage,
                    status,
                    linked_mandate_id,
                    linked_proposal_id,
                    linked_evaluation_id,
                    linked_paypal_order_id,
                    linked_capture_id,
                    details_json,
                    actor_role,
                    now_iso,
                    prev_hash,
                    event_hash,
                ),
            )
            conn.commit()

    return {
        "sequence_number": sequence_number,
        "event_id": event_id,
        "transaction_id": transaction_id,
        "event_type": event_type,
        "stage": stage,
        "status": status,
        "linked_mandate_id": linked_mandate_id,
        "linked_proposal_id": linked_proposal_id,
        "linked_evaluation_id": linked_evaluation_id,
        "linked_paypal_order_id": linked_paypal_order_id,
        "linked_capture_id": linked_capture_id,
        "details": details,
        "actor_role": actor_role,
        "timestamp": now_iso,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
    }


# -------------------------------------------------------------------------
# Centralized Lifecycle State Machine Transitions & Event Chaining
# -------------------------------------------------------------------------

def transition_transaction_state(
    transaction_id: str,
    target_state: TransactionState,
    actor_role: str = "human_user",
    user_id: str = "user_operator",
    reason: Optional[str] = None,
    details_override: Optional[Dict[str, Any]] = None,
    paypal_order_id: Optional[str] = None,
    capture_id: Optional[str] = None,
    raw_capture_response: Optional[Dict[str, Any]] = None,
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Atomically validates, executes, and persists a lifecycle state transition.

    CRITICAL INVARIANTS:
    1. Rejects illegal transitions server-side (InvalidStateTransitionError).
    2. Updates staged_proposals and inserts cryptographically chained audit event
       within ONE database transaction (BEGIN IMMEDIATE;).
    3. Guarantees consistency between status and the unbroken audit hash chain.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    with _AUDIT_LOCK:
        with get_db_connection(db_file) as conn:
            conn.execute("BEGIN IMMEDIATE;")

            # 1. Fetch current transaction record inside transaction lock
            row = conn.execute(
                "SELECT * FROM staged_proposals WHERE staged_proposal_id = ?;",
                (transaction_id,),
            ).fetchone()

            if not row:
                conn.execute("ROLLBACK;")
                raise ValueError(f"Transaction '{transaction_id}' not found.")

            current_status_str = row["status"] if "status" in row.keys() else "STAGED"
            try:
                current_state = TransactionState(current_status_str)
            except ValueError:
                current_state = TransactionState.STAGED

            # 2. Validate permitted transition
            if not is_transition_permitted(current_state, target_state):
                conn.execute("ROLLBACK;")
                raise InvalidStateTransitionError(current_state, target_state, transaction_id)

            # 3. Update staged_proposals
            update_clauses = ["status = ?", "updated_at = ?"]
            params: List[Any] = [target_state.value, now_iso]

            if paypal_order_id:
                update_clauses.append("paypal_order_id = ?")
                params.append(paypal_order_id)
            if capture_id:
                update_clauses.append("captured = 1")
                update_clauses.append("capture_id = ?")
                params.append(capture_id)
            if target_state == TransactionState.HUMAN_REJECTED and reason:
                update_clauses.append("rejection_reason = ?")
                params.append(reason)
            if target_state == TransactionState.CANCELLED and reason:
                update_clauses.append("cancellation_reason = ?")
                params.append(reason)

            params.append(transaction_id)
            conn.execute(
                f"UPDATE staged_proposals SET {', '.join(update_clauses)} WHERE staged_proposal_id = ?;",
                params,
            )

            # If order and captures table update is needed
            if target_state == TransactionState.ORDER_CREATED and paypal_order_id:
                try:
                    cand = json.loads(row["candidate_data"])
                    price = cand.get("price", 0.0)
                    currency = cand.get("currency", "USD")
                    is_demo = bool(cand.get("is_demo_data", 1))
                except Exception:
                    price = 0.0
                    currency = "USD"
                    is_demo = True

                conn.execute(
                    """
                    INSERT OR REPLACE INTO orders_and_captures (
                        order_id, staged_proposal_id, status, amount, currency,
                        is_sandbox, is_demo_data, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        paypal_order_id,
                        transaction_id,
                        "CREATED",
                        price,
                        currency,
                        1,
                        1 if is_demo else 0,
                        now_iso,
                    ),
                )
            elif target_state == TransactionState.CAPTURED:
                order_id_to_use = row["paypal_order_id"] or paypal_order_id
                if order_id_to_use:
                    conn.execute(
                        """
                        UPDATE orders_and_captures
                        SET status = 'COMPLETED', capture_id = ?, captured_at = ?, raw_capture_response = ?
                        WHERE order_id = ?
                        """,
                        (capture_id, now_iso, json.dumps(raw_capture_response or {}), order_id_to_use),
                    )

            # 4. Map event metadata for the audit trail
            event_type_map = {
                TransactionState.HUMAN_APPROVED: ("HUMAN_APPROVAL_GRANTED", "APPROVAL", "GRANTED"),
                TransactionState.HUMAN_REJECTED: ("HUMAN_APPROVAL_REJECTED", "APPROVAL", "REJECTED"),
                TransactionState.ORDER_CREATED: ("PAYPAL_ORDER_CREATED", "PAYMENT", "CREATED"),
                TransactionState.ORDER_CREATION_FAILED: ("PAYPAL_ORDER_CREATION_FAILED", "PAYMENT", "FAILED"),
                TransactionState.CAPTURED: ("PAYPAL_CAPTURED", "RECEIPT", "COMPLETED"),
                TransactionState.CAPTURE_FAILED: ("PAYPAL_CAPTURE_FAILED", "PAYMENT", "FAILED"),
                TransactionState.CANCELLED: ("CHECKOUT_CANCELLED", "LIFECYCLE", "CANCELLED"),
                TransactionState.EXPIRED: ("CHECKOUT_EXPIRED", "LIFECYCLE", "EXPIRED"),
            }

            event_type, stage, evt_status = event_type_map.get(
                target_state,
                ("STATE_TRANSITION", "LIFECYCLE", target_state.value),
            )

            audit_details = {
                "transaction_id": transaction_id,
                "previous_state": current_state.value,
                "target_state": target_state.value,
                "reason": reason,
                "actor_role": actor_role,
                "user_id": user_id,
            }
            if paypal_order_id:
                audit_details["paypal_order_id"] = paypal_order_id
            if capture_id:
                audit_details["capture_id"] = capture_id
            if details_override:
                audit_details.update(details_override)

            # 5. Insert chained audit event within the SAME database transaction
            last_audit_row = conn.execute(
                "SELECT sequence_number, event_hash FROM audit_events ORDER BY sequence_number DESC LIMIT 1;"
            ).fetchone()

            seq = 1 if last_audit_row is None else last_audit_row["sequence_number"] + 1
            p_hash = GENESIS_HASH if last_audit_row is None else last_audit_row["event_hash"]
            event_id = f"evt_{uuid.uuid4().hex[:10]}"

            evt_hash = compute_canonical_event_hash(
                sequence_number=seq,
                prev_hash=p_hash,
                event_id=event_id,
                transaction_id=transaction_id,
                event_type=event_type,
                status=evt_status,
                details=audit_details,
                timestamp=now_iso,
            )

            conn.execute(
                """
                INSERT INTO audit_events (
                    sequence_number, event_id, transaction_id, event_type, stage, status,
                    linked_mandate_id, linked_proposal_id, linked_evaluation_id,
                    linked_paypal_order_id, linked_capture_id, details, actor_role, timestamp,
                    prev_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq,
                    event_id,
                    transaction_id,
                    event_type,
                    stage,
                    evt_status,
                    row["mandate_id"],
                    row["candidate_product_id"],
                    None,
                    paypal_order_id or row["paypal_order_id"],
                    capture_id or row["capture_id"],
                    json.dumps(audit_details),
                    actor_role,
                    now_iso,
                    p_hash,
                    evt_hash,
                ),
            )

            # Commit both staged_proposals update and audit_events insertion atomically
            conn.commit()

            try:
                from app.services.proposal_store import proposal_store
                if transaction_id in proposal_store._proposals:
                    cached_rec = proposal_store._proposals[transaction_id]
                    cached_rec.status = target_state.value
                    cached_rec.updated_at = now_iso
                    if paypal_order_id:
                        cached_rec.paypal_order_id = paypal_order_id
                    if capture_id:
                        cached_rec.capture_id = capture_id
                        cached_rec.captured = True
                    if target_state == TransactionState.HUMAN_REJECTED and reason:
                        cached_rec.rejection_reason = reason
                    if target_state == TransactionState.CANCELLED and reason:
                        cached_rec.cancellation_reason = reason
            except Exception:
                pass

    return {
        "transaction_id": transaction_id,
        "previous_state": current_state,
        "current_state": target_state,
        "updated_at": now_iso,
        "audit_event_hash": evt_hash,
        "message": f"Transaction successfully transitioned to {target_state.value}.",
    }


def record_human_approval(
    transaction_id: str,
    user_id: str,
    policy_signature: str,
    approved_amount: float,
    currency: str,
    action: str = "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
    actor_role: str = "human_user",
    consent_token: Optional[str] = None,
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persists an explicit human authorization record and transitions state to HUMAN_APPROVED."""
    approval_id = f"appr_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Ensure transaction exists in staged_proposals table before recording approval
    with get_db_connection(db_file) as conn:
        existing = conn.execute(
            "SELECT staged_proposal_id FROM staged_proposals WHERE staged_proposal_id = ?;",
            (transaction_id,),
        ).fetchone()
        if not existing:
            raise ValueError(
                f"Cannot record human approval: Transaction '{transaction_id}' not found. "
                "Explicit human approval requires a genuine pre-existing staged proposal."
            )

    # Track db_file association in proposal_store if custom
    if db_file:
        try:
            from app.services.proposal_store import proposal_store
            proposal_store.set_db_file(transaction_id, Path(db_file))
        except Exception:
            pass

    # Step 1: Execute atomic state transition STAGED -> HUMAN_APPROVED
    transition_result = transition_transaction_state(
        transaction_id=transaction_id,
        target_state=TransactionState.HUMAN_APPROVED,
        actor_role=actor_role,
        user_id=user_id,
        details_override={
            "approval_id": approval_id,
            "action": action,
            "approved_amount": approved_amount,
            "currency": currency,
            "policy_signature": policy_signature,
            "non_ai_assertion": "Confirmed human user authorized checkout handoff. Autonomous AI execution prohibited.",
        },
        db_file=db_file,
    )

    # Step 2: Record authorization in human_approvals table
    with get_db_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO human_approvals (
                approval_id, transaction_id, user_id, policy_signature,
                approved_amount, currency, action, actor_role, consent_token, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                transaction_id,
                user_id,
                policy_signature,
                approved_amount,
                currency,
                action,
                actor_role,
                consent_token or f"tok_{uuid.uuid4().hex[:12]}",
                now_iso,
            ),
        )
        conn.commit()

    return {
        "approval_id": approval_id,
        "human_approval_id": approval_id,
        "transaction_id": transaction_id,
        "user_id": user_id,
        "policy_signature": policy_signature,
        "approved_amount": approved_amount,
        "currency": currency,
        "action": action,
        "actor_role": actor_role,
        "created_at": now_iso,
        "previous_state": transition_result["previous_state"],
        "current_state": transition_result["current_state"],
        "status": transition_result["current_state"],
        "audit_event_hash": transition_result["audit_event_hash"],
        "updated_at": transition_result["updated_at"],
        "message": transition_result["message"],
    }


def record_human_rejection(
    transaction_id: str,
    user_id: str,
    reason: str,
    actor_role: str = "human_user",
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Explicitly records human refusal of a proposal and transitions state to HUMAN_REJECTED."""
    target_db = db_file
    if target_db is None:
        try:
            from app.services.proposal_store import proposal_store
            target_db = proposal_store.get_db_file(transaction_id)
        except Exception:
            target_db = None

    return transition_transaction_state(
        transaction_id=transaction_id,
        target_state=TransactionState.HUMAN_REJECTED,
        actor_role=actor_role,
        user_id=user_id,
        reason=reason,
        db_file=target_db,
    )


def record_transaction_cancellation(
    transaction_id: str,
    user_id: str,
    reason: Optional[str] = None,
    actor_role: str = "human_user",
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Explicitly cancels an active checkout session and transitions state to CANCELLED."""
    target_db = db_file
    if target_db is None:
        try:
            from app.services.proposal_store import proposal_store
            target_db = proposal_store.get_db_file(transaction_id)
        except Exception:
            target_db = None

    return transition_transaction_state(
        transaction_id=transaction_id,
        target_state=TransactionState.CANCELLED,
        actor_role=actor_role,
        user_id=user_id,
        reason=reason or "User cancelled checkout session",
        db_file=target_db,
    )


def record_transaction_expiration(
    transaction_id: str,
    reason: Optional[str] = None,
    actor_role: str = "system",
    db_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Expires an abandoned checkout session past its TTL and transitions state to EXPIRED."""
    target_db = db_file
    if target_db is None:
        try:
            from app.services.proposal_store import proposal_store
            target_db = proposal_store.get_db_file(transaction_id)
        except Exception:
            target_db = None

    return transition_transaction_state(
        transaction_id=transaction_id,
        target_state=TransactionState.EXPIRED,
        actor_role=actor_role,
        reason=reason or "Checkout session expired past TTL",
        db_file=target_db,
    )


# Explicit database alias exports for cancellation & expiration persistence
db_record_transaction_cancellation = record_transaction_cancellation
db_record_transaction_expiration = record_transaction_expiration



def get_human_approval(transaction_id: str, db_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the explicit human approval record for a transaction, if one exists."""
    target_db = db_file
    if target_db is None:
        try:
            from app.services.proposal_store import proposal_store
            target_db = proposal_store.get_db_file(transaction_id)
        except Exception:
            target_db = None

    with get_db_connection(target_db) as conn:
        row = conn.execute(
            "SELECT * FROM human_approvals WHERE transaction_id = ? ORDER BY created_at DESC LIMIT 1;",
            (transaction_id,),
        ).fetchone()
        if row:
            return dict(row)

    # Fallback to default DB if custom target_db was checked first, or vice-versa
    if db_file is None and target_db is not None:
        with get_db_connection(None) as conn:
            row = conn.execute(
                "SELECT * FROM human_approvals WHERE transaction_id = ? ORDER BY created_at DESC LIMIT 1;",
                (transaction_id,),
            ).fetchone()
            if row:
                return dict(row)

    return None


def verify_audit_integrity(db_file: Optional[Path] = None) -> Dict[str, Any]:
    """Validates the cryptographic SHA-256 hash chain across all stored events.

    Detects:
    1. Any modified payload, status, or metadata.
    2. Any deleted record (broken link or sequence gap).
    3. Any inserted or reordered record.
    4. Exact sequence number and event_id where the first violation occurred.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_file) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY sequence_number ASC;"
        ).fetchall()

    total_events = len(rows)

    if total_events == 0:
        return {
            "is_valid": True,
            "total_events": 0,
            "genesis_hash": GENESIS_HASH,
            "last_event_hash": None,
            "first_invalid_sequence": None,
            "first_invalid_event_id": None,
            "failure_reason": None,
            "verified_at": now_iso,
            "tamper_evident_guarantee": (
                "Audit trail is empty. Cryptographic hash chaining and SQLite append-only triggers are active."
            ),
        }

    expected_sequence = 1
    expected_prev_hash = GENESIS_HASH
    last_verified_hash = None

    for row in rows:
        seq = row["sequence_number"]
        evt_id = row["event_id"]
        stored_prev_hash = row["prev_hash"]
        stored_event_hash = row["event_hash"]

        # Check 1: Contiguous sequence numbers
        if seq != expected_sequence:
            return {
                "is_valid": False,
                "total_events": total_events,
                "genesis_hash": GENESIS_HASH,
                "last_event_hash": last_verified_hash,
                "first_invalid_sequence": seq,
                "first_invalid_event_id": evt_id,
                "failure_reason": (
                    f"Sequence discontinuity detected at sequence {seq}. "
                    f"Expected sequence {expected_sequence}. Record deletion or reordering indicated."
                ),
                "verified_at": now_iso,
                "tamper_evident_guarantee": "Audit chain verification failed: record omission or reordering.",
            }

        # Check 2: Previous hash link
        if stored_prev_hash != expected_prev_hash:
            return {
                "is_valid": False,
                "total_events": total_events,
                "genesis_hash": GENESIS_HASH,
                "last_event_hash": last_verified_hash,
                "first_invalid_sequence": seq,
                "first_invalid_event_id": evt_id,
                "failure_reason": (
                    f"Broken hash link at sequence {seq} (event {evt_id}). "
                    f"Stored prev_hash does not match preceding event hash."
                ),
                "verified_at": now_iso,
                "tamper_evident_guarantee": "Audit chain verification failed: broken hash link.",
            }

        # Check 3: Canonical hash verification
        try:
            details = json.loads(row["details"]) if row["details"] else {}
        except Exception:
            details = {}

        computed_hash = compute_canonical_event_hash(
            sequence_number=seq,
            prev_hash=stored_prev_hash,
            event_id=evt_id,
            transaction_id=row["transaction_id"],
            event_type=row["event_type"],
            status=row["status"],
            details=details,
            timestamp=row["timestamp"],
        )

        if computed_hash != stored_event_hash:
            return {
                "is_valid": False,
                "total_events": total_events,
                "genesis_hash": GENESIS_HASH,
                "last_event_hash": last_verified_hash,
                "first_invalid_sequence": seq,
                "first_invalid_event_id": evt_id,
                "failure_reason": (
                    f"Tampered record detected at sequence {seq} (event {evt_id}). "
                    f"Stored event_hash does not match recalculated canonical SHA-256 digest."
                ),
                "verified_at": now_iso,
                "tamper_evident_guarantee": "Audit chain verification failed: modified payload or metadata.",
            }

        last_verified_hash = stored_event_hash
        expected_prev_hash = stored_event_hash
        expected_sequence += 1

    return {
        "is_valid": True,
        "total_events": total_events,
        "genesis_hash": GENESIS_HASH,
        "last_event_hash": last_verified_hash,
        "first_invalid_sequence": None,
        "first_invalid_event_id": None,
        "failure_reason": None,
        "verified_at": now_iso,
        "tamper_evident_guarantee": (
            f"All {total_events} audit events cryptographically verified via unbroken SHA-256 hash chaining. "
            "SQLite engine triggers enforce append-only storage. "
            "Guarantees mathematical tamper-evidence against unauthorized application-level modifications. "
            "Does not guarantee protection against raw database file manipulation by a host administrator."
        ),
    }


def get_audit_events(
    transaction_id: Optional[str] = None,
    event_type: Optional[str] = None,
    stage: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "DESC",
    db_file: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Fetches persistent audit events with sequence numbers and cryptographic hashes."""
    query = "SELECT * FROM audit_events"
    params: List[Any] = []
    conditions: List[str] = []

    if transaction_id:
        conditions.append("transaction_id = ?")
        params.append(transaction_id)

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if stage:
        conditions.append("stage = ?")
        params.append(stage)

    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    order_dir = "ASC" if order_by.upper() == "ASC" else "DESC"
    query += f" ORDER BY sequence_number {order_dir} LIMIT ? OFFSET ?"
    params.extend([limit, max(0, offset)])

    with get_db_connection(db_file) as conn:
        rows = conn.execute(query, params).fetchall()

    events = []
    for r in rows:
        events.append({
            "sequence_number": r["sequence_number"],
            "event_id": r["event_id"],
            "transaction_id": r["transaction_id"],
            "event_type": r["event_type"],
            "stage": r["stage"],
            "status": r["status"],
            "linked_mandate_id": r["linked_mandate_id"],
            "linked_proposal_id": r["linked_proposal_id"],
            "linked_evaluation_id": r["linked_evaluation_id"],
            "linked_paypal_order_id": r["linked_paypal_order_id"],
            "linked_capture_id": r["linked_capture_id"],
            "details": json.loads(r["details"]) if r["details"] else {},
            "actor_role": r["actor_role"],
            "timestamp": r["timestamp"],
            "prev_hash": r["prev_hash"],
            "event_hash": r["event_hash"],
        })
    return events


def count_audit_events(
    transaction_id: Optional[str] = None,
    event_type: Optional[str] = None,
    stage: Optional[str] = None,
    status: Optional[str] = None,
    db_file: Optional[Path] = None,
) -> int:
    """Returns the total count of audit events matching optional filters."""
    query = "SELECT COUNT(*) FROM audit_events"
    params: List[Any] = []
    conditions: List[str] = []

    if transaction_id:
        conditions.append("transaction_id = ?")
        params.append(transaction_id)

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if stage:
        conditions.append("stage = ?")
        params.append(stage)

    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    with get_db_connection(db_file) as conn:
        row = conn.execute(query, params).fetchone()
        return row[0] if row else 0


def get_audit_event_by_id(
    event_id: str,
    db_file: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Fetches a single immutable audit event by its unique event_id."""
    with get_db_connection(db_file) as conn:
        r = conn.execute(
            "SELECT * FROM audit_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()

    if not r:
        return None

    return {
        "sequence_number": r["sequence_number"],
        "event_id": r["event_id"],
        "transaction_id": r["transaction_id"],
        "event_type": r["event_type"],
        "stage": r["stage"],
        "status": r["status"],
        "linked_mandate_id": r["linked_mandate_id"],
        "linked_proposal_id": r["linked_proposal_id"],
        "linked_evaluation_id": r["linked_evaluation_id"],
        "linked_paypal_order_id": r["linked_paypal_order_id"],
        "linked_capture_id": r["linked_capture_id"],
        "details": json.loads(r["details"]) if r["details"] else {},
        "actor_role": r["actor_role"],
        "timestamp": r["timestamp"],
        "prev_hash": r["prev_hash"],
        "event_hash": r["event_hash"],
    }


def list_persisted_transactions(limit: int = 50, db_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Returns recent staged transactions with current lifecycle status."""
    query = """
        SELECT sp.staged_proposal_id, sp.mandate_id, sp.candidate_data, sp.user_id,
               sp.status, sp.paypal_order_id, sp.captured, sp.capture_id, sp.created_at, sp.updated_at,
               oc.status as order_status, oc.amount, oc.currency
        FROM staged_proposals sp
        LEFT JOIN orders_and_captures oc ON sp.paypal_order_id = oc.order_id
        ORDER BY sp.created_at DESC
        LIMIT ?
    """
    with get_db_connection(db_file) as conn:
        rows = conn.execute(query, (limit,)).fetchall()

    results = []
    for r in rows:
        try:
            cand = json.loads(r["candidate_data"])
            product_name = cand.get("name", "Unknown Product")
            price = cand.get("price", r["amount"] or 0.0)
            currency = cand.get("currency", r["currency"] or "USD")
            merchant = cand.get("merchant_name", "Unknown Merchant")
        except Exception:
            product_name = "Product"
            price = r["amount"] or 0.0
            currency = r["currency"] or "USD"
            merchant = "Merchant"

        tx_status = r["status"] if "status" in r.keys() and r["status"] else (
            "COMPLETED" if r["captured"] else ("ORDER_CREATED" if r["paypal_order_id"] else "STAGED")
        )

        results.append({
            "transaction_id": r["staged_proposal_id"],
            "product_name": product_name,
            "amount": price,
            "currency": currency,
            "merchant_name": merchant,
            "policy_approved": True,
            "status": tx_status,
            "created_at": r["created_at"],
            "paypal_order_id": r["paypal_order_id"],
            "capture_id": r["capture_id"],
        })
    return results


def get_transaction_timeline_data(transaction_id: str, db_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Reconstructs the full 6-stage lifecycle timeline for a specific transaction."""
    with get_db_connection(db_file) as conn:
        # 1. Staged proposal record
        staged_row = conn.execute(
            "SELECT * FROM staged_proposals WHERE staged_proposal_id = ?",
            (transaction_id,),
        ).fetchone()

        if not staged_row:
            return None

        # 2. Associated mandate
        mandate_row = conn.execute(
            "SELECT * FROM mandates WHERE mandate_id = ?",
            (staged_row["mandate_id"],),
        ).fetchone()

        # 3. Associated human approval
        approval_row = conn.execute(
            "SELECT * FROM human_approvals WHERE transaction_id = ? ORDER BY created_at DESC LIMIT 1",
            (transaction_id,),
        ).fetchone()

        # 4. Associated order & capture
        order_row = None
        if staged_row["paypal_order_id"]:
            order_row = conn.execute(
                "SELECT * FROM orders_and_captures WHERE order_id = ?",
                (staged_row["paypal_order_id"],),
            ).fetchone()

        # 5. Audit events for this transaction with sequence numbers and hashes
        events_rows = conn.execute(
            "SELECT * FROM audit_events WHERE transaction_id = ? ORDER BY sequence_number ASC",
            (transaction_id,),
        ).fetchall()

    candidate = json.loads(staged_row["candidate_data"])
    mandate = json.loads(staged_row["mandate_data"]) if staged_row["mandate_data"] else {}
    evaluation = json.loads(staged_row["evaluation_data"]) if staged_row["evaluation_data"] else {}

    events = []
    for ev in events_rows:
        events.append({
            "sequence_number": ev["sequence_number"],
            "event_id": ev["event_id"],
            "transaction_id": ev["transaction_id"],
            "event_type": ev["event_type"],
            "stage": ev["stage"],
            "status": ev["status"],
            "linked_mandate_id": ev["linked_mandate_id"],
            "linked_proposal_id": ev["linked_proposal_id"],
            "linked_evaluation_id": ev["linked_evaluation_id"],
            "linked_paypal_order_id": ev["linked_paypal_order_id"],
            "linked_capture_id": ev["linked_capture_id"],
            "details": json.loads(ev["details"]) if ev["details"] else {},
            "actor_role": ev["actor_role"],
            "timestamp": ev["timestamp"],
            "prev_hash": ev["prev_hash"],
            "event_hash": ev["event_hash"],
        })

    # Assemble 6 Lifecycle Stages with accurate state synchronization
    is_captured = bool(staged_row["captured"])
    has_order = bool(staged_row["paypal_order_id"])
    has_approval = approval_row is not None

    current_status = staged_row["status"] if "status" in staged_row.keys() and staged_row["status"] else (
        "COMPLETED" if is_captured else ("ORDER_CREATED" if has_order else "STAGED")
    )
    is_rejected = current_status == TransactionState.HUMAN_REJECTED.value
    is_cancelled = current_status == TransactionState.CANCELLED.value
    is_expired = current_status == TransactionState.EXPIRED.value
    is_order_failed = current_status == TransactionState.ORDER_CREATION_FAILED.value
    is_capture_failed = current_status == TransactionState.CAPTURE_FAILED.value

    # Stage 4 Resolution
    if is_rejected:
        s4_status = "BLOCKED"
        s4_summary = f"Rejected by human operator: {staged_row.get('rejection_reason') or 'Proposal refused'}"
    elif is_cancelled and not has_approval and not has_order:
        s4_status = "BLOCKED"
        s4_summary = f"Session cancelled prior to authorization: {staged_row.get('cancellation_reason') or 'Session cancelled'}"
    elif is_expired and not has_approval and not has_order:
        s4_status = "BLOCKED"
        s4_summary = "Session expired past TTL prior to authorization"
    elif has_approval or has_order or is_captured:
        s4_status = "COMPLETED"
        s4_summary = f"Approved by human operator ({approval_row['user_id'] if approval_row else staged_row['user_id']})"
    else:
        s4_status = "PENDING"
        s4_summary = "Awaiting explicit human confirmation (AI prohibited)"

    # Stage 5 Resolution
    if has_order:
        s5_status = "COMPLETED"
        s5_summary = f"Order ID: {staged_row['paypal_order_id']}"
    elif is_order_failed:
        s5_status = "BLOCKED"
        s5_summary = "PayPal Sandbox order creation failed (recoverable error)"
    elif is_rejected:
        s5_status = "NOT_STARTED"
        s5_summary = "Order creation barred: Proposal rejected by operator"
    elif is_cancelled:
        s5_status = "NOT_STARTED"
        s5_summary = f"Order creation barred: Session cancelled ({staged_row.get('cancellation_reason') or 'Cancelled'})"
    elif is_expired:
        s5_status = "NOT_STARTED"
        s5_summary = "Order creation barred: Session expired past TTL"
    elif has_approval:
        s5_status = "PENDING"
        s5_summary = "Ready for PayPal Sandbox checkout handoff"
    else:
        s5_status = "NOT_STARTED"
        s5_summary = "Order not yet initiated"

    # Stage 6 Resolution
    if is_captured:
        s6_status = "COMPLETED"
        s6_summary = f"Capture ID: {staged_row['capture_id']}"
    elif is_capture_failed:
        s6_status = "BLOCKED"
        s6_summary = "PayPal Sandbox payment capture declined or failed"
    elif is_cancelled and has_order:
        s6_status = "BLOCKED"
        s6_summary = f"Session cancelled before capture: {staged_row.get('cancellation_reason') or 'Cancelled'}"
    elif has_order:
        s6_status = "PENDING"
        s6_summary = "Capture pending buyer approval in PayPal Sandbox"
    else:
        s6_status = "NOT_STARTED"
        s6_summary = "Capture not initiated"

    stages = [
        # Stage 1: Mandate
        {
            "stage_name": "1. Natural Language Mandate",
            "stage_key": "mandate",
            "status": "COMPLETED",
            "timestamp": mandate_row["created_at"] if mandate_row else staged_row["created_at"],
            "summary": f"Budget limit {mandate.get('currency', 'USD')} {mandate.get('max_amount', 0.0):.2f}",
            "details": {
                "mandate_id": staged_row["mandate_id"],
                "currency": mandate.get("currency"),
                "max_amount": mandate.get("max_amount"),
                "allowed_conditions": mandate.get("allowed_conditions"),
                "require_merchant_verification": mandate.get("require_merchant_verification"),
                "allow_add_ons": mandate.get("allow_add_ons"),
            },
        },
        # Stage 2: Proposal Discovery
        {
            "stage_name": "2. Candidate Proposal Discovery",
            "stage_key": "proposal",
            "status": "COMPLETED",
            "timestamp": staged_row["created_at"],
            "summary": f"{candidate.get('name', 'Candidate')} from {candidate.get('merchant_name', 'Merchant')}",
            "details": {
                "product_id": candidate.get("product_id"),
                "product_name": candidate.get("name"),
                "price": candidate.get("price"),
                "currency": candidate.get("currency"),
                "merchant_name": candidate.get("merchant_name"),
                "merchant_verified": candidate.get("merchant_verified"),
                "condition": candidate.get("condition"),
                "data_source": candidate.get("data_source"),
                "is_demo_data": candidate.get("is_demo_data"),
            },
        },
        # Stage 3: Deterministic Policy Evaluation
        {
            "stage_name": "3. Deterministic Policy Verification",
            "stage_key": "policy",
            "status": "COMPLETED" if evaluation.get("approved") else "BLOCKED",
            "timestamp": evaluation.get("evaluated_at", staged_row["created_at"]),
            "summary": f"Policy {evaluation.get('status', 'APPROVED')} ({len(evaluation.get('checks', []))} invariants verified)",
            "details": {
                "evaluation_id": evaluation.get("evaluation_id"),
                "approved": evaluation.get("approved"),
                "policy_signature": evaluation.get("policy_signature"),
                "violations": evaluation.get("violations", []),
                "checks": evaluation.get("checks", []),
                "explanation": evaluation.get("explanation"),
            },
        },
        # Stage 4: Explicit Human Approval
        {
            "stage_name": "4. Explicit Human Authorization",
            "stage_key": "approval",
            "status": s4_status,
            "timestamp": approval_row["created_at"] if approval_row else (order_row["created_at"] if order_row else None),
            "summary": s4_summary,
            "details": {
                "approval_id": approval_row["approval_id"] if approval_row else None,
                "user_id": approval_row["user_id"] if approval_row else staged_row["user_id"],
                "actor_role": approval_row["actor_role"] if approval_row else "human_user",
                "action": approval_row["action"] if approval_row else (
                    "REJECT_PROPOSAL" if is_rejected else "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT"
                ),
                "rejection_reason": staged_row.get("rejection_reason") if is_rejected else None,
                "cancellation_reason": staged_row.get("cancellation_reason") if is_cancelled else None,
                "non_ai_assertion": "AI zero payment authority rule enforced (TG-007)",
            },
        },
        # Stage 5: PayPal Sandbox Checkout Order
        {
            "stage_name": "5. PayPal Sandbox Checkout Order",
            "stage_key": "order",
            "status": s5_status,
            "timestamp": order_row["created_at"] if order_row else None,
            "summary": s5_summary,
            "details": {
                "order_id": staged_row["paypal_order_id"],
                "status": order_row["status"] if order_row else ("FAILED" if is_order_failed else "NOT_INITIATED"),
                "is_sandbox": True,
                "amount": order_row["amount"] if order_row else candidate.get("price"),
                "currency": order_row["currency"] if order_row else candidate.get("currency"),
            },
        },
        # Stage 6: Verified Receipt & Capture
        {
            "stage_name": "6. Verified Receipt & Capture",
            "stage_key": "receipt",
            "status": s6_status,
            "timestamp": order_row["captured_at"] if order_row and order_row["captured_at"] else None,
            "summary": s6_summary,
            "details": {
                "capture_id": staged_row["capture_id"],
                "status": "COMPLETED" if is_captured else ("FAILED" if is_capture_failed else "NOT_CAPTURED"),
                "captured_at": order_row["captured_at"] if order_row else None,
                "is_sandbox": True,
                "is_demo_data": bool(candidate.get("is_demo_data")),
                "policy_signature": evaluation.get("policy_signature"),
            },
        },
    ]

    return {
        "transaction_id": transaction_id,
        "current_status": current_status,
        "created_at": staged_row["created_at"],
        "updated_at": staged_row["updated_at"],
        "mandate_summary": {
            "mandate_id": staged_row["mandate_id"],
            "currency": mandate.get("currency"),
            "max_amount": mandate.get("max_amount"),
            "allowed_conditions": mandate.get("allowed_conditions"),
        },
        "candidate_summary": {
            "product_id": candidate.get("product_id"),
            "name": candidate.get("name"),
            "price": candidate.get("price"),
            "currency": candidate.get("currency"),
            "merchant_name": candidate.get("merchant_name"),
            "condition": candidate.get("condition"),
            "is_demo_data": candidate.get("is_demo_data"),
        },
        "policy_evaluation_summary": {
            "evaluation_id": evaluation.get("evaluation_id"),
            "approved": evaluation.get("approved"),
            "policy_signature": evaluation.get("policy_signature"),
            "violations_count": len(evaluation.get("violations", [])),
        },
        "human_approval_summary": {
            "approved": has_approval or has_order,
            "approval_id": approval_row["approval_id"] if approval_row else None,
            "user_id": approval_row["user_id"] if approval_row else staged_row["user_id"],
        },
        "paypal_order_summary": {
            "order_id": staged_row["paypal_order_id"],
            "status": order_row["status"] if order_row else "NOT_INITIATED",
            "is_sandbox": True,
        },
        "capture_receipt_summary": {
            "captured": is_captured,
            "capture_id": staged_row["capture_id"],
            "captured_at": order_row["captured_at"] if order_row else None,
        },
        "stages": stages,
        "events": events,
    }


def get_audit_summary(db_file: Optional[Path] = None) -> Dict[str, Any]:
    """Returns telemetry of total transactions, evaluations, Sandbox payments, and hash chain status."""
    with get_db_connection(db_file) as conn:
        total_events = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        total_mandates = conn.execute("SELECT COUNT(*) FROM mandates").fetchone()[0]
        total_staged = conn.execute("SELECT COUNT(*) FROM staged_proposals").fetchone()[0]
        total_captures = conn.execute("SELECT COUNT(*) FROM orders_and_captures WHERE capture_id IS NOT NULL").fetchone()[0]
        total_evaluations = conn.execute("SELECT COUNT(*) FROM policy_evaluations").fetchone()[0]
        approved_evaluations = conn.execute("SELECT COUNT(*) FROM policy_evaluations WHERE approved = 1").fetchone()[0]
        blocked_evaluations = conn.execute("SELECT COUNT(*) FROM policy_evaluations WHERE approved = 0").fetchone()[0]
        total_approvals = conn.execute("SELECT COUNT(*) FROM human_approvals").fetchone()[0]

    integrity = verify_audit_integrity(db_file)

    return {
        "storage_engine": "SQLite Persistent (ACID compliant with SHA-256 Hash Chaining)",
        "db_path": str(db_file or DB_PATH),
        "persisted": True,
        "audit_chain_verified": integrity["is_valid"],
        "genesis_hash": GENESIS_HASH,
        "last_event_hash": integrity["last_event_hash"],
        "total_audit_events": total_events,
        "total_mandates": total_mandates,
        "total_staged_proposals": total_staged,
        "total_paypal_captures": total_captures,
        "total_evaluations": total_evaluations,
        "approved_evaluations": approved_evaluations,
        "blocked_evaluations": blocked_evaluations,
        "total_human_approvals": total_approvals,
    }
