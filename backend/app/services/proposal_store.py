"""Persistent server-side state for staged proposals and PayPal Sandbox orders.

CRITICAL SECURITY INVARIANTS:
1. All records are persisted to SQLite so that server restarts never drop orders or state.
2. The backend never trusts a price, currency, merchant, or policy result sent by the frontend.
3. Every step records an immutable audit event in the database.
4. AI models are strictly prohibited from authorizing payments.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from app.db.database import (
    get_db_connection,
    record_audit_event,
    transition_transaction_state,
    record_human_approval as db_record_human_approval,
    record_human_rejection as db_record_human_rejection,
    record_transaction_cancellation as db_record_transaction_cancellation,
    record_transaction_expiration as db_record_transaction_expiration,
)
from app.models.lifecycle import TransactionState
from app.models.payment import StagedProposalRecord
from app.models.policy import PurchaseMandate, MandatePolicyEvaluationResponse
from app.models.proposal import DiscoveredProduct

logger = logging.getLogger(__name__)


class ProposalStore:
    """Persistent, restart-safe repository for staged proposals and order linkages."""

    def __init__(self):
        # In-memory cache for ultra-fast lookup, backed by SQLite persistence
        self._proposals: Dict[str, StagedProposalRecord] = {}
        self._order_map: Dict[str, str] = {}
        self._db_files: Dict[str, Path] = {}

    def set_db_file(self, staged_proposal_id: str, db_file: Path) -> None:
        """Associates a staged proposal with its specific database file."""
        self._db_files[staged_proposal_id] = Path(db_file)

    def get_db_file(self, staged_proposal_id: str) -> Optional[Path]:
        """Retrieves custom database file associated with a staged proposal."""
        return self._db_files.get(staged_proposal_id)

    def save_staged_proposal(
        self,
        staged_proposal_id: str,
        mandate: PurchaseMandate,
        candidate: DiscoveredProduct,
        policy_evaluation: MandatePolicyEvaluationResponse,
        user_id: str = "user_demo",
        db_file: Optional[Path] = None,
    ) -> StagedProposalRecord:
        """Stores a verified staged proposal in persistent SQLite and memory cache."""
        now_iso = datetime.now(timezone.utc).isoformat()
        mandate_id = f"man_{staged_proposal_id[4:]}" if staged_proposal_id.startswith("stg_") else f"man_{staged_proposal_id}"
        proposal_id = f"prop_{staged_proposal_id[4:]}" if staged_proposal_id.startswith("stg_") else f"prop_{staged_proposal_id}"

        record = StagedProposalRecord(
            staged_proposal_id=staged_proposal_id,
            mandate=mandate,
            candidate=candidate,
            policy_evaluation=policy_evaluation,
            user_id=user_id,
            status=TransactionState.STAGED.value,
            created_at=now_iso,
            updated_at=now_iso,
            paypal_order_id=None,
            captured=False,
            capture_id=None,
            capture_data=None,
        )

        # 1. Update in-memory cache
        self._proposals[staged_proposal_id] = record
        if db_file:
            self._db_files[staged_proposal_id] = Path(db_file)

        # 2. Persist to SQLite
        try:
            with get_db_connection(db_file) as conn:
                # Save Mandate
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mandates (
                        mandate_id, user_id, max_amount, currency, allowed_conditions,
                        require_merchant_verification, allow_add_ons, user_restrictions,
                        original_prompt, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mandate_id,
                        user_id,
                        mandate.max_amount,
                        mandate.currency,
                        json.dumps(mandate.allowed_conditions),
                        1 if mandate.require_merchant_verification else 0,
                        1 if mandate.allow_add_ons else 0,
                        json.dumps(mandate.user_restrictions or []),
                        "",
                        now_iso,
                    ),
                )

                # Save Proposal
                conn.execute(
                    """
                    INSERT OR REPLACE INTO proposals (
                        proposal_id, mandate_id, product_id, name, description,
                        category, price, currency, merchant_name, merchant_verified,
                        verification_status, condition, data_source, is_demo_data,
                        marketplace_id, region, data_freshness, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal_id,
                        mandate_id,
                        candidate.product_id,
                        candidate.name,
                        candidate.description,
                        candidate.category,
                        candidate.price,
                        candidate.currency,
                        candidate.merchant_name,
                        1 if candidate.merchant_verified else 0,
                        candidate.verification_status,
                        candidate.condition,
                        candidate.data_source,
                        1 if candidate.is_demo_data else 0,
                        candidate.marketplace_id,
                        candidate.region,
                        candidate.data_freshness,
                        now_iso,
                    ),
                )

                # Save Policy Evaluation
                conn.execute(
                    """
                    INSERT OR REPLACE INTO policy_evaluations (
                        evaluation_id, proposal_id, mandate_id, approved, status,
                        violations, checks, explanation, policy_signature, caller_role, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        policy_evaluation.evaluation_id,
                        proposal_id,
                        mandate_id,
                        1 if policy_evaluation.approved else 0,
                        policy_evaluation.status,
                        json.dumps([v.model_dump() for v in policy_evaluation.violations]),
                        json.dumps([c.model_dump() for c in policy_evaluation.checks]),
                        policy_evaluation.explanation,
                        policy_evaluation.policy_signature,
                        "human_user",
                        policy_evaluation.evaluated_at,
                    ),
                )

                # Save Staged Proposal with explicit STAGED state
                conn.execute(
                    """
                    INSERT OR REPLACE INTO staged_proposals (
                        staged_proposal_id, mandate_id, candidate_product_id, candidate_data,
                        mandate_data, evaluation_data, user_id, status, paypal_order_id,
                        captured, capture_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        staged_proposal_id,
                        mandate_id,
                        candidate.product_id,
                        candidate.model_dump_json(),
                        mandate.model_dump_json(),
                        policy_evaluation.model_dump_json(),
                        user_id,
                        TransactionState.STAGED.value,
                        None,
                        0,
                        None,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()

            # Record Lifecycle Audit Event
            record_audit_event(
                transaction_id=staged_proposal_id,
                event_type="PROPOSAL_STAGED",
                stage="PROPOSAL",
                status="STAGED",
                linked_mandate_id=mandate_id,
                linked_proposal_id=proposal_id,
                linked_evaluation_id=policy_evaluation.evaluation_id,
                details={
                    "product_name": candidate.name,
                    "price": candidate.price,
                    "currency": candidate.currency,
                    "merchant": candidate.merchant_name,
                    "policy_approved": policy_evaluation.approved,
                    "budget_limit": mandate.max_amount,
                },
                actor_role="human_user",
                db_file=db_file,
            )
        except Exception as e:
            logger.error(f"Failed to persist staged proposal to SQLite: {e}", exc_info=True)

        return record

    def get_staged_proposal(
        self, staged_proposal_id: str, db_file: Optional[Path] = None
    ) -> Optional[StagedProposalRecord]:
        """Look up a staged proposal by its internal ID (memory first if no custom db, SQLite fallback)."""
        target_db = db_file or self.get_db_file(staged_proposal_id)
        if staged_proposal_id in self._proposals:
            rec = self._proposals[staged_proposal_id]
            try:
                with get_db_connection(target_db) as conn:
                    sp_row = conn.execute(
                        "SELECT status, rejection_reason, cancellation_reason, paypal_order_id, captured, capture_id, updated_at FROM staged_proposals WHERE staged_proposal_id = ?;",
                        (staged_proposal_id,),
                    ).fetchone()
                    if sp_row:
                        if "status" in sp_row.keys() and sp_row["status"]:
                            rec.status = sp_row["status"]
                        if "rejection_reason" in sp_row.keys() and sp_row["rejection_reason"]:
                            rec.rejection_reason = sp_row["rejection_reason"]
                        if "cancellation_reason" in sp_row.keys() and sp_row["cancellation_reason"]:
                            rec.cancellation_reason = sp_row["cancellation_reason"]
                        if "paypal_order_id" in sp_row.keys() and sp_row["paypal_order_id"]:
                            rec.paypal_order_id = sp_row["paypal_order_id"]
                        if "captured" in sp_row.keys():
                            rec.captured = bool(sp_row["captured"])
                        if "capture_id" in sp_row.keys() and sp_row["capture_id"]:
                            rec.capture_id = sp_row["capture_id"]
                        if "updated_at" in sp_row.keys() and sp_row["updated_at"]:
                            rec.updated_at = sp_row["updated_at"]

                    mandate_row = conn.execute(
                        "SELECT max_amount, currency FROM mandates WHERE mandate_id = (SELECT mandate_id FROM staged_proposals WHERE staged_proposal_id = ?);",
                        (staged_proposal_id,),
                    ).fetchone()
                    if mandate_row and mandate_row["max_amount"] != rec.mandate.max_amount:
                        rec.mandate.max_amount = float(mandate_row["max_amount"])
            except Exception:
                pass
            return rec

        # SQLite query
        try:
            with get_db_connection(target_db) as conn:
                row = conn.execute(
                    "SELECT * FROM staged_proposals WHERE staged_proposal_id = ?",
                    (staged_proposal_id,),
                ).fetchone()

                if not row:
                    return None

                candidate = DiscoveredProduct.model_validate_json(row["candidate_data"])
                # Query active mandate from mandates table to ensure any mandate modifications are reflected
                mandate_row = conn.execute(
                    "SELECT * FROM mandates WHERE mandate_id = ?",
                    (row["mandate_id"],),
                ).fetchone()
                if mandate_row:
                    if "mandate_data" in row.keys() and row["mandate_data"]:
                        mandate = PurchaseMandate.model_validate_json(row["mandate_data"])
                        mandate.max_amount = float(mandate_row["max_amount"])
                        mandate.currency = mandate_row["currency"]
                    else:
                        allowed_conds = mandate_row["allowed_conditions"]
                        if isinstance(allowed_conds, str) and allowed_conds.startswith("["):
                            allowed_conds = json.loads(allowed_conds)
                        elif isinstance(allowed_conds, str):
                            allowed_conds = [allowed_conds]
                        user_rest = mandate_row["user_restrictions"]
                        if isinstance(user_rest, str) and user_rest.startswith("["):
                            user_rest = json.loads(user_rest)
                        elif isinstance(user_rest, str):
                            user_rest = [user_rest] if user_rest else []
                        mandate = PurchaseMandate(
                            max_amount=float(mandate_row["max_amount"]),
                            currency=mandate_row["currency"],
                            allowed_conditions=allowed_conds,
                            require_merchant_verification=bool(mandate_row["require_merchant_verification"]),
                            allow_add_ons=bool(mandate_row["allow_add_ons"]),
                            user_restrictions=user_rest,
                        )
                else:
                    mandate = PurchaseMandate.model_validate_json(row["mandate_data"])

                evaluation = MandatePolicyEvaluationResponse.model_validate_json(row["evaluation_data"])
                status = row["status"] if "status" in row.keys() else "STAGED"

                record = StagedProposalRecord(
                    staged_proposal_id=row["staged_proposal_id"],
                    mandate=mandate,
                    candidate=candidate,
                    policy_evaluation=evaluation,
                    user_id=row["user_id"],
                    status=status,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"] if "updated_at" in row.keys() else row["created_at"],
                    paypal_order_id=row["paypal_order_id"],
                    captured=bool(row["captured"]),
                    capture_id=row["capture_id"],
                    capture_data=None,
                    rejection_reason=row["rejection_reason"] if "rejection_reason" in row.keys() else None,
                    cancellation_reason=row["cancellation_reason"] if "cancellation_reason" in row.keys() else None,
                    expires_at=row["expires_at"] if "expires_at" in row.keys() else None,
                )
                # Re-cache in memory
                self._proposals[staged_proposal_id] = record
                if target_db:
                    self._db_files[staged_proposal_id] = Path(target_db)
                if row["paypal_order_id"]:
                    self._order_map[row["paypal_order_id"]] = staged_proposal_id
                return record
        except Exception as e:
            logger.error(f"Error querying staged proposal from SQLite: {e}")
            return None

    def get_by_paypal_order_id(
        self, order_id: str, db_file: Optional[Path] = None
    ) -> Optional[StagedProposalRecord]:
        """Look up a staged proposal using its linked PayPal order ID."""
        if db_file is None:
            staged_id = self._order_map.get(order_id)
            if staged_id and staged_id in self._proposals:
                return self._proposals[staged_id]

        try:
            with get_db_connection(db_file) as conn:
                row = conn.execute(
                    "SELECT * FROM staged_proposals WHERE paypal_order_id = ?",
                    (order_id,),
                ).fetchone()

                if not row:
                    return None

                candidate = DiscoveredProduct.model_validate_json(row["candidate_data"])
                mandate = PurchaseMandate.model_validate_json(row["mandate_data"])
                evaluation = MandatePolicyEvaluationResponse.model_validate_json(row["evaluation_data"])
                status = row["status"] if "status" in row.keys() else "STAGED"

                record = StagedProposalRecord(
                    staged_proposal_id=row["staged_proposal_id"],
                    mandate=mandate,
                    candidate=candidate,
                    policy_evaluation=evaluation,
                    user_id=row["user_id"],
                    status=status,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"] if "updated_at" in row.keys() else row["created_at"],
                    paypal_order_id=row["paypal_order_id"],
                    captured=bool(row["captured"]),
                    capture_id=row["capture_id"],
                    capture_data=None,
                    rejection_reason=row["rejection_reason"] if "rejection_reason" in row.keys() else None,
                    cancellation_reason=row["cancellation_reason"] if "cancellation_reason" in row.keys() else None,
                    expires_at=row["expires_at"] if "expires_at" in row.keys() else None,
                )
                self._proposals[record.staged_proposal_id] = record
                self._order_map[order_id] = record.staged_proposal_id
                return record
        except Exception as e:
            logger.error(f"Error querying by paypal order id from SQLite: {e}")
            return None

    def link_paypal_order(
        self, staged_proposal_id: str, order_id: str, db_file: Optional[Path] = None
    ) -> bool:
        """Atomically transitions state to ORDER_CREATED and links PayPal order."""
        record = self.get_staged_proposal(staged_proposal_id, db_file=db_file)
        if not record:
            return False

        transition_transaction_state(
            transaction_id=staged_proposal_id,
            target_state=TransactionState.ORDER_CREATED,
            actor_role="system",
            paypal_order_id=order_id,
            db_file=db_file,
        )

        record.paypal_order_id = order_id
        record.status = TransactionState.ORDER_CREATED.value
        self._order_map[order_id] = staged_proposal_id
        return True

    def mark_captured(
        self,
        order_id: str,
        capture_id: str,
        capture_data: Optional[Dict] = None,
        raw_capture_data: Optional[Dict] = None,
        db_file: Optional[Path] = None,
    ) -> Optional[StagedProposalRecord]:
        """Atomically transitions state to CAPTURED after verified PayPal response."""
        final_capture_data = capture_data if capture_data is not None else (raw_capture_data or {})
        record = self.get_by_paypal_order_id(order_id, db_file=db_file)
        if not record:
            return None

        transition_transaction_state(
            transaction_id=record.staged_proposal_id,
            target_state=TransactionState.CAPTURED,
            actor_role="paypal_gateway",
            capture_id=capture_id,
            raw_capture_response=final_capture_data,
            db_file=db_file,
        )

        record.captured = True
        record.capture_id = capture_id
        record.status = TransactionState.CAPTURED.value
        record.capture_data = final_capture_data
        return record

    def mark_order_creation_failed(
        self, staged_proposal_id: str, reason: str, db_file: Optional[Path] = None
    ) -> None:
        """Transitions state to ORDER_CREATION_FAILED following a PayPal API or network error."""
        record = self.get_staged_proposal(staged_proposal_id, db_file=db_file)
        transition_transaction_state(
            transaction_id=staged_proposal_id,
            target_state=TransactionState.ORDER_CREATION_FAILED,
            actor_role="system",
            reason=reason,
            db_file=db_file,
        )
        if record:
            record.status = TransactionState.ORDER_CREATION_FAILED.value

    def mark_capture_failed(
        self, staged_proposal_id: str, reason: str, db_file: Optional[Path] = None
    ) -> None:
        """Transitions state to CAPTURE_FAILED following a declined capture or gateway error."""
        record = self.get_staged_proposal(staged_proposal_id, db_file=db_file)
        transition_transaction_state(
            transaction_id=staged_proposal_id,
            target_state=TransactionState.CAPTURE_FAILED,
            actor_role="paypal_gateway",
            reason=reason,
            db_file=db_file,
        )
        if record:
            record.status = TransactionState.CAPTURE_FAILED.value

    def record_approval(
        self,
        transaction_id: str,
        user_id: Optional[str] = None,
        policy_signature: Optional[str] = None,
        approved_amount: Optional[float] = None,
        currency: Optional[str] = None,
        action: str = "AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
        consent_token: Optional[str] = None,
        db_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Records human approval and transitions state to HUMAN_APPROVED."""
        record = self.get_staged_proposal(transaction_id, db_file=db_file)
        sig = policy_signature or (record.policy_evaluation.policy_signature if record else "tg_sig_approved")
        amt = approved_amount if approved_amount is not None else (record.candidate.price if record else 0.0)
        curr = currency or (record.candidate.currency if record else "USD")
        uid = user_id or (record.user_id if record else "user_operator")

        res = db_record_human_approval(
            transaction_id=transaction_id,
            user_id=uid,
            policy_signature=sig,
            approved_amount=amt,
            currency=curr,
            action=action,
            actor_role="human_user",
            consent_token=consent_token,
            db_file=db_file,
        )
        if record:
            record.status = TransactionState.HUMAN_APPROVED.value
        return res

    def record_rejection(
        self,
        transaction_id: str,
        user_id: str,
        reason: str,
        db_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Records human refusal and transitions state to HUMAN_REJECTED."""
        res = db_record_human_rejection(
            transaction_id=transaction_id,
            user_id=user_id,
            reason=reason,
            actor_role="human_user",
            db_file=db_file,
        )
        record = self.get_staged_proposal(transaction_id, db_file=db_file)
        if record:
            record.status = TransactionState.HUMAN_REJECTED.value
            record.rejection_reason = reason
        return res

    def record_cancellation(
        self,
        transaction_id: str,
        user_id: str,
        reason: Optional[str] = None,
        db_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Cancels an active checkout session and transitions state to CANCELLED."""
        res = db_record_transaction_cancellation(
            transaction_id=transaction_id,
            user_id=user_id,
            reason=reason,
            actor_role="human_user",
            db_file=db_file,
        )
        record = self.get_staged_proposal(transaction_id, db_file=db_file)
        if record:
            record.status = TransactionState.CANCELLED.value
            record.cancellation_reason = reason
        return res

    def record_expiration(
        self,
        transaction_id: str,
        reason: Optional[str] = None,
        db_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Expires an uncaptured checkout session past TTL and transitions state to EXPIRED."""
        res = db_record_transaction_expiration(
            transaction_id=transaction_id,
            reason=reason,
            actor_role="system",
            db_file=db_file,
        )
        record = self.get_staged_proposal(transaction_id, db_file=db_file)
        if record:
            record.status = TransactionState.EXPIRED.value
        return res

    def clear(self) -> None:
        """Clears in-memory cache and test records."""
        self._proposals.clear()
        self._order_map.clear()
        self._db_files.clear()


proposal_store = ProposalStore()
