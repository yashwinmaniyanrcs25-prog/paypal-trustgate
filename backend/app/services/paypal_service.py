"""PayPal Sandbox Integration Service for TrustGate.

Implements the official PayPal Sandbox REST API v2 for Orders creation and capture.
Strictly restricted to Sandbox testing; live payment processing is forbidden.

CRITICAL SECURITY INVARIANTS:
1. Never trusts price, currency, or approval status from frontend.
2. Derives all transaction parameters strictly from trusted server-side state (proposal_store).
3. Revalidates the candidate against the confirmed purchase mandate immediately before creating the order.
4. Enforces human-in-the-loop: AI agents have zero authorization or capture privileges.
5. Idempotent order creation and capture protection against duplicate attempts.
6. Server-side verification of PayPal order status and capture receipts.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.security import enforce_human_approval_invariant, PaymentExecutionBlockedError
from app.models.lifecycle import TransactionState
from app.models.payment import (
    PaymentConfigResponse,
    CreateOrderResponse,
    CaptureOrderResponse,
    PaymentStatusResponse,
)
from app.models.policy import ProposedTransaction
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.db.database import get_db_connection, record_human_approval, record_audit_event, get_human_approval

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
DEFAULT_TIMEOUT = 12.0


class PayPalSandboxService:
    """Service to create, authorize, and capture orders in PayPal Sandbox."""

    def __init__(self):
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def base_url(self) -> str:
        return SANDBOX_BASE_URL

    @property
    def is_configured(self) -> bool:
        return settings.is_paypal_configured()

    def get_config(self) -> PaymentConfigResponse:
        """Returns safe public config for frontend PayPal JS SDK."""
        configured = self.is_configured
        client_id = settings.get_paypal_client_id() if configured else None
        return PaymentConfigResponse(
            configured=configured,
            client_id=client_id,
            mode="sandbox",
            currency=settings.PAYPAL_CURRENCY,
            base_url=self.base_url,
            merchant_name="PayPal TrustGate Sandbox",
            is_sandbox=True,
            notice="Sandbox test environment only. Demonstration checkout. No real financial charges occur.",
        )

    def get_sandbox_status(self) -> Dict[str, Any]:
        """Telemetry check for health endpoint."""
        return {
            "mode": "sandbox",
            "currency": settings.PAYPAL_CURRENCY,
            "configured": self.is_configured,
            "target_api": self.base_url,
            "payment_execution_enabled": self.is_configured,
            "policy_guardrail_active": True,
        }

    async def verify_sandbox_auth(self) -> Dict[str, Any]:
        """Tests PayPal Sandbox OAuth 2.0 authentication without exposing credentials or creating orders."""
        if not self.is_configured:
            return {
                "authenticated": False,
                "status": "NOT_CONFIGURED",
                "configured": False,
                "mode": "sandbox",
                "target_api": self.base_url,
                "error": "PayPal credentials missing or using placeholders in backend/.env",
            }

        client_id = settings.PAYPAL_CLIENT_ID.strip()
        client_secret = settings.PAYPAL_CLIENT_SECRET.strip()

        token_url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                res = await client.post(
                    token_url,
                    data=data,
                    headers=headers,
                    auth=(client_id, client_secret),
                )
                if res.status_code == 200:
                    token_data = res.json()
                    self._cached_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    self._token_expires_at = time.time() + float(expires_in)
                    return {
                        "authenticated": True,
                        "status": "SUCCESS",
                        "http_status": 200,
                        "target_api": self.base_url,
                        "mode": "sandbox",
                        "is_sandbox": True,
                        "live_mode_blocked": True,
                        "token_type": token_data.get("token_type", "Bearer"),
                        "expires_in": expires_in,
                        "app_id": token_data.get("app_id"),
                        "scope": token_data.get("scope"),
                        "message": "PayPal Sandbox OAuth authentication succeeded. Valid bearer access token obtained.",
                    }
                else:
                    err_body = res.json() if res.text.startswith("{") else {}
                    err_msg = err_body.get("error_description", res.text)
                    return {
                        "authenticated": False,
                        "status": "FAILED",
                        "http_status": res.status_code,
                        "target_api": self.base_url,
                        "mode": "sandbox",
                        "is_sandbox": True,
                        "live_mode_blocked": True,
                        "error": err_body.get("error", "authentication_error"),
                        "error_description": err_msg,
                    }
        except httpx.TimeoutException:
            return {
                "authenticated": False,
                "status": "TIMEOUT",
                "target_api": self.base_url,
                "mode": "sandbox",
                "error": "PayPal Sandbox OAuth endpoint timed out.",
            }
        except Exception as exc:
            return {
                "authenticated": False,
                "status": "ERROR",
                "target_api": self.base_url,
                "mode": "sandbox",
                "error": str(exc),
            }

    async def get_access_token(self) -> str:
        """Obtains OAuth 2.0 Bearer access token using server-side client credentials."""
        if not self.is_configured:
            raise ValueError(
                "PayPal Sandbox credentials missing. Configure PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env."
            )

        # Return cached token if valid
        now = time.time()
        if self._cached_token and now < (self._token_expires_at - 60):
            return self._cached_token

        client_id = settings.PAYPAL_CLIENT_ID.strip()
        client_secret = settings.PAYPAL_CLIENT_SECRET.strip()

        token_url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                res = await client.post(
                    token_url,
                    data=data,
                    headers=headers,
                    auth=(client_id, client_secret),
                )
                if res.status_code != 200:
                    logger.error(f"PayPal OAuth failed with status {res.status_code}: {res.text}")
                    raise ValueError(f"PayPal Sandbox authentication failed (HTTP {res.status_code}).")

                token_data = res.json()
                self._cached_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self._token_expires_at = now + float(expires_in)
                return self._cached_token

        except httpx.TimeoutException:
            logger.error("PayPal OAuth endpoint timed out.")
            raise TimeoutError("PayPal Sandbox authentication endpoint timed out.")
        except Exception as exc:
            logger.error(f"PayPal OAuth connection error: {exc}")
            raise

    async def create_sandbox_order(
        self,
        staged_proposal_id: str,
        user_id: str = "user_demo",
        caller_role: str = "human_user",
        db_file: Optional[Path] = None,
    ) -> CreateOrderResponse:
        """Creates an order in PayPal Sandbox strictly derived from server-side state.

        SECURITY INVARIANTS:
        1. AI agents cannot initiate orders.
        2. Retrieves the candidate and mandate from trusted server memory.
        3. Revalidates deterministic policy before order creation.
        4. Storing linkage between internal proposal ID and PayPal order ID.
        """
        # Invariant 1: Caller cannot be an AI agent
        enforce_human_approval_invariant(
            human_approved=True,
            caller_role=caller_role,
        )

        target_db = db_file or proposal_store.get_db_file(staged_proposal_id)

        # Invariant 2: Retrieve candidate strictly from server state
        record = proposal_store.get_staged_proposal(staged_proposal_id, db_file=target_db)
        if not record:
            raise ValueError(
                f"Staged proposal '{staged_proposal_id}' not found. "
                "Transactions must be discovered and staged through TrustGate."
            )

        candidate = record.candidate
        mandate = record.mandate

        # Idempotency check: if PayPal order was already created, return it safely
        if record.paypal_order_id:
            if record.captured:
                raise ValueError(
                    f"Proposal '{staged_proposal_id}' has already been paid and captured."
                )
            return CreateOrderResponse(
                order_id=record.paypal_order_id,
                staged_proposal_id=staged_proposal_id,
                status="CREATED",
                amount=candidate.price,
                currency=candidate.currency,
                is_sandbox=True,
                is_demo_data=candidate.is_demo_data,
                message="Retrieved existing uncaptured PayPal Sandbox order.",
            )

        # Invariant: Must be in HUMAN_APPROVED state or ORDER_CREATION_FAILED (retry)
        if record.status not in (TransactionState.HUMAN_APPROVED.value, TransactionState.ORDER_CREATION_FAILED.value):
            if record.status == TransactionState.STAGED.value:
                raise PaymentExecutionBlockedError(
                    f"Proposal '{staged_proposal_id}' cannot create order: Explicit human approval is required before order creation."
                )
            raise PaymentExecutionBlockedError(
                f"Cannot create PayPal Sandbox order for proposal '{staged_proposal_id}' in state '{record.status}'."
            )

        # Invariant: Must verify explicit human approval record exists in persistent storage
        approval = get_human_approval(staged_proposal_id, db_file=target_db)
        if not approval:
            raise PaymentExecutionBlockedError(
                f"Proposal '{staged_proposal_id}' lacks verified human authorization record in database."
            )

        # Invariant: Must verify proposal corresponds to a genuine staged proposal
        prop_suffix = staged_proposal_id[4:] if staged_proposal_id.startswith("stg_") else staged_proposal_id
        target_proposal_id = f"prop_{prop_suffix}"
        with get_db_connection(target_db) as conn:
            prop_row = conn.execute(
                """
                SELECT proposal_id, is_demo_data FROM proposals
                WHERE proposal_id = ?
                   OR mandate_id = (SELECT mandate_id FROM staged_proposals WHERE staged_proposal_id = ?)
                ORDER BY CASE WHEN proposal_id = ? THEN 0 ELSE 1 END, created_at DESC;
                """,
                (target_proposal_id, staged_proposal_id, target_proposal_id),
            ).fetchone()
            if not prop_row:
                raise PaymentExecutionBlockedError(
                    f"Cannot create PayPal Sandbox order: Proposal '{staged_proposal_id}' is not a genuine staged purchase proposal."
                )
            if prop_row["is_demo_data"] or candidate.is_demo_data:
                raise PaymentExecutionBlockedError(
                    f"Cannot create PayPal Sandbox order: Proposal '{staged_proposal_id}' is a demonstration fixture and is not a genuine staged purchase proposal. Real marketplace purchase proposal required."
                )

        # Re-derive proposed transaction from trusted candidate
        if candidate.price is None or candidate.price <= 0:
            raise PaymentExecutionBlockedError(
                f"Cannot create PayPal Sandbox order: Proposal '{staged_proposal_id}' candidate has invalid non-positive price ({candidate.price})."
            )

        derived_tx = ProposedTransaction(
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

        # Invariant 3: Revalidate candidate against confirmed mandate immediately prior to PayPal call
        reval = policy_engine.evaluate_mandate(
            mandate=mandate,
            transaction=derived_tx,
            caller_role="human_user",
        )
        if not reval.approved:
            violations_str = "; ".join(v.message for v in reval.violations)
            raise PaymentExecutionBlockedError(
                f"Policy revalidation failed immediately prior to order creation: {violations_str}"
            )

        # Obtain OAuth token
        token = await self.get_access_token()

        # PayPal Orders v2 payload
        order_url = f"{self.base_url}/v2/checkout/orders"
        idempotency_key = f"tg_order_{staged_proposal_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": idempotency_key,
        }

        order_payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reval.policy_signature,
                    "description": f"TrustGate Sandbox: {candidate.name[:120]}",
                    "amount": {
                        "currency_code": candidate.currency.upper(),
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

        # Pre-flight TrustGate Orders v2 Schema Validation Guardrail
        from app.services.paypal_order_validator import paypal_order_validator
        contract_validation = paypal_order_validator.validate_order_request(order_payload)
        if not contract_validation.is_valid:
            violations_detail = "; ".join(contract_validation.errors)
            logger.error(f"TrustGate order schema validation failed: {violations_detail}")
            proposal_store.mark_order_creation_failed(
                staged_proposal_id, f"Order Schema Violation: {violations_detail}"
            )
            raise PaymentExecutionBlockedError(
                f"Order Schema Violation: Order creation blocked by pre-flight schema guardrail. {violations_detail}"
            )

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                res = await client.post(order_url, json=order_payload, headers=headers)
                if res.status_code not in (200, 201):
                    logger.error(f"PayPal create order failed (HTTP {res.status_code}): {res.text}")
                    proposal_store.mark_order_creation_failed(staged_proposal_id, f"HTTP {res.status_code}: {res.text}")
                    raise ValueError(f"Failed to create PayPal Sandbox order (HTTP {res.status_code}).")

                order_data = res.json()
                paypal_order_id = order_data["id"]

                # Invariant 4: Link internal proposal to PayPal order ID in server state
                proposal_store.link_paypal_order(staged_proposal_id, paypal_order_id)

                return CreateOrderResponse(
                    order_id=paypal_order_id,
                    staged_proposal_id=staged_proposal_id,
                    status=order_data.get("status", "CREATED"),
                    amount=candidate.price,
                    currency=candidate.currency,
                    is_sandbox=True,
                    is_demo_data=candidate.is_demo_data,
                    message="PayPal Sandbox order successfully created. Ready for buyer approval.",
                )

        except httpx.TimeoutException:
            logger.error("PayPal create order timed out.")
            proposal_store.mark_order_creation_failed(
                staged_proposal_id,
                "PayPal Sandbox API timed out during order creation.",
            )
            raise TimeoutError("PayPal Sandbox API timed out during order creation.")
        except Exception as exc:
            logger.error(f"PayPal create order error: {exc}")
            try:
                proposal_store.mark_order_creation_failed(staged_proposal_id, str(exc))
            except Exception:
                pass
            raise

    async def capture_sandbox_order(
        self,
        order_id: str,
        user_id: str = "user_demo",
        caller_role: str = "human_user",
        db_file: Optional[Path] = None,
    ) -> CaptureOrderResponse:
        """Captures a PayPal Sandbox order only after explicit buyer approval.

        SECURITY INVARIANTS:
        1. AI cannot trigger capture.
        2. Verifies order_id was created by this TrustGate backend and links to an approved proposal.
        3. Idempotent: Repeated capture attempts return existing verified receipt safely.
        4. Validates server-side capture status from PayPal Sandbox.
        """
        # Invariant 1: Caller cannot be an AI agent
        enforce_human_approval_invariant(
            human_approved=True,
            caller_role=caller_role,
        )

        staged_id = proposal_store._order_map.get(order_id, "")
        target_db = db_file or (proposal_store.get_db_file(staged_id) if staged_id else None)

        # Invariant 2: Verify order_id maps to a valid internal proposal record
        record = proposal_store.get_by_paypal_order_id(order_id, db_file=target_db)
        if not record:
            raise PaymentExecutionBlockedError(
                f"Untrusted order ID '{order_id}'. Order was not created or approved by TrustGate."
            )

        # Invariant 3: Idempotent capture handling
        if record.captured and record.capture_id:
            logger.info(f"Order '{order_id}' was already captured; returning idempotent receipt.")
            return CaptureOrderResponse(
                order_id=order_id,
                capture_id=record.capture_id,
                staged_proposal_id=record.staged_proposal_id,
                status="COMPLETED",
                amount=record.candidate.price,
                currency=record.candidate.currency,
                product_name=record.candidate.name,
                merchant_name=record.candidate.merchant_name,
                captured_at=record.created_at,
                policy_decision="APPROVED",
                policy_signature=record.policy_evaluation.policy_signature,
                is_sandbox=True,
                is_demo_data=record.candidate.is_demo_data,
                receipt_notice="PayPal Sandbox transaction previously captured. Idempotent receipt provided.",
            )

        # Invariant 4: State machine enforcement - must be ORDER_CREATED or CAPTURE_FAILED (retry)
        if record.status not in (TransactionState.ORDER_CREATED.value, TransactionState.CAPTURE_FAILED.value):
            raise PaymentExecutionBlockedError(
                f"Cannot capture PayPal Sandbox order '{order_id}': proposal is in state '{record.status}'."
            )

        # Invariant 5: Human approval must exist in persistent database
        approval = get_human_approval(record.staged_proposal_id, db_file=target_db)
        if not approval:
            raise PaymentExecutionBlockedError(
                f"Cannot capture order '{order_id}': Missing verified human authorization record."
            )

        # Obtain OAuth token
        token = await self.get_access_token()

        capture_url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
        idempotency_key = f"tg_cap_{order_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": idempotency_key,
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                res = await client.post(capture_url, headers=headers)
                if res.status_code not in (200, 201):
                    logger.error(f"PayPal capture failed (HTTP {res.status_code}): {res.text}")
                    error_detail = res.json().get("message", res.text) if res.text.startswith("{") else res.text
                    proposal_store.mark_capture_failed(record.staged_proposal_id, error_detail)
                    raise ValueError(f"PayPal Sandbox capture failed: {error_detail}")

                capture_data = res.json()

                # Pre-flight TrustGate Capture Response Validation
                from app.services.paypal_order_validator import paypal_order_validator
                cap_validation = paypal_order_validator.validate_capture_response(capture_data)
                if not cap_validation.is_valid:
                    logger.warning("Capture response validation warnings: %s", cap_validation.errors)

                order_status = capture_data.get("status")

                if order_status != "COMPLETED":
                    err_msg = f"Order status '{order_status}' is not COMPLETED. Capture could not be finalized."
                    proposal_store.mark_capture_failed(record.staged_proposal_id, err_msg)
                    raise ValueError(err_msg)

                # Extract capture ID and timestamps
                purchase_units = capture_data.get("purchase_units", [])
                captures = (
                    purchase_units[0].get("payments", {}).get("captures", [])
                    if purchase_units
                    else []
                )
                capture_id = captures[0].get("id") if captures else f"cap_{order_id[:8]}"
                captured_at = (
                    captures[0].get("create_time")
                    if captures
                    else datetime.now(timezone.utc).isoformat()
                )

                # Mark order captured in trusted server state
                proposal_store.mark_captured(order_id, capture_id, capture_data)

                demo_msg = (
                    "PayPal Sandbox transaction captured successfully. Simulated demo item. No real funds transferred."
                    if record.candidate.is_demo_data
                    else "PayPal Sandbox transaction captured successfully. Sandbox environment only."
                )

                return CaptureOrderResponse(
                    order_id=order_id,
                    capture_id=capture_id,
                    staged_proposal_id=record.staged_proposal_id,
                    status="COMPLETED",
                    amount=record.candidate.price,
                    currency=record.candidate.currency,
                    product_name=record.candidate.name,
                    merchant_name=record.candidate.merchant_name,
                    captured_at=captured_at,
                    policy_decision="APPROVED",
                    policy_signature=record.policy_evaluation.policy_signature,
                    is_sandbox=True,
                    is_demo_data=record.candidate.is_demo_data,
                    receipt_notice=demo_msg,
                )

        except httpx.TimeoutException:
            logger.error("PayPal capture request timed out.")
            proposal_store.mark_capture_failed(
                record.staged_proposal_id,
                "PayPal Sandbox API timed out during capture.",
            )
            raise TimeoutError("PayPal Sandbox API timed out during capture.")
        except Exception as exc:
            logger.error(f"PayPal capture error: {exc}")
            try:
                proposal_store.mark_capture_failed(record.staged_proposal_id, str(exc))
            except Exception:
                pass
            raise

    async def get_order_status(self, order_id: str) -> PaymentStatusResponse:
        """Returns safe status for a PayPal Sandbox order."""
        record = proposal_store.get_by_paypal_order_id(order_id)
        if not record:
            return PaymentStatusResponse(
                order_id=order_id,
                staged_proposal_id=None,
                status="NOT_FOUND",
                captured=False,
                is_sandbox=True,
                is_demo_data=True,
            )

        status_str = "COMPLETED" if record.captured else "CREATED"

        # Attempt to query PayPal Sandbox for live status if configured
        if self.is_configured:
            try:
                token = await self.get_access_token()
                url = f"{self.base_url}/v2/checkout/orders/{order_id}"
                headers = {"Authorization": f"Bearer {token}"}
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    res = await client.get(url, headers=headers)
                    if res.status_code == 200:
                        status_str = res.json().get("status", status_str)
            except Exception as err:
                logger.warning(f"Could not refresh order status from PayPal: {err}")

        return PaymentStatusResponse(
            order_id=order_id,
            staged_proposal_id=record.staged_proposal_id,
            status=status_str,
            amount=record.candidate.price,
            currency=record.candidate.currency,
            captured=record.captured,
            capture_id=record.capture_id,
            is_sandbox=True,
            is_demo_data=record.candidate.is_demo_data,
        )


paypal_service = PayPalSandboxService()
