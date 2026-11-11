"""Supabase Service for audit logging and constraint storage.

Provides modular readiness for persisting user instructions, AI recommendations,
policy evaluation audit trails, and human authorization tokens in Supabase
while backing all records locally into ACID-compliant persistent SQLite.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import record_audit_event, get_audit_events

logger = logging.getLogger(__name__)


class SupabaseService:
    """Modular integration for Supabase storage and persistent audit logs."""

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
        # In-memory transient buffer for initial foundation phase
        self._audit_logs: List[Dict[str, Any]] = []

    def is_configured(self) -> bool:
        """Determines if Supabase credentials have been configured."""
        return bool(
            self.supabase_url
            and self.service_role_key
            and not self.supabase_url.startswith("https://your-")
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "target_url": self.supabase_url or "Not configured",
            "audit_table": "trustgate_audit_logs",
            "active_in_memory_buffer_count": len(self._audit_logs),
            "persisted_sqlite": True,
        }

    async def log_policy_evaluation(
        self,
        evaluation_id: str,
        user_id: str,
        passed: bool,
        total_cost: float,
        rules_checked: int,
        violations: List[str],
    ) -> Dict[str, Any]:
        """Appends an immutable policy evaluation record to memory and persistent SQLite."""
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "evaluation_id": evaluation_id,
            "user_id": user_id,
            "passed": passed,
            "total_cost": total_cost,
            "rules_checked": rules_checked,
            "violations": violations,
            "timestamp": now_iso,
            "source": "deterministic_policy_engine",
        }
        self._audit_logs.append(entry)

        # Persist to SQLite audit_events table
        try:
            record_audit_event(
                transaction_id=evaluation_id,
                event_type="POLICY_EVALUATION",
                stage="POLICY",
                status="PASSED" if passed else "VIOLATION",
                linked_evaluation_id=evaluation_id,
                details={
                    "user_id": user_id,
                    "passed": passed,
                    "total_cost": total_cost,
                    "rules_checked": rules_checked,
                    "violations": violations,
                },
                actor_role="deterministic_policy_engine",
            )
        except Exception as e:
            logger.error(f"Failed to record policy evaluation to SQLite audit trail: {e}")

        return entry

    async def get_recent_audit_logs(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retrieves the latest audit entries from SQLite (falling back to memory)."""
        try:
            db_events = get_audit_events(limit=limit)
            if db_events:
                formatted_logs = []
                for ev in db_events:
                    details = ev.get("details", {})
                    # If this was a policy evaluation event or proposal staged event, shape it for AuditLogItem
                    eval_id = ev.get("linked_evaluation_id") or ev.get("event_id")
                    cost = details.get("total_cost", details.get("price", 0.0))
                    passed = ev.get("status") in ("PASSED", "STAGED", "CREATED", "COMPLETED", "GRANTED")
                    violations = details.get("violations", [])

                    formatted_logs.append({
                        "evaluation_id": eval_id,
                        "user_id": details.get("user_id", "mandate_user"),
                        "passed": passed,
                        "total_cost": float(cost) if cost is not None else 0.0,
                        "rules_checked": details.get("rules_checked", 7),
                        "violations": violations if isinstance(violations, list) else [str(violations)],
                        "timestamp": ev.get("timestamp"),
                        "source": ev.get("actor_role", "system"),
                    })
                return formatted_logs
        except Exception as e:
            logger.error(f"Error reading persistent audit events from SQLite: {e}")

        return self._audit_logs[-limit:]


supabase_service = SupabaseService()
