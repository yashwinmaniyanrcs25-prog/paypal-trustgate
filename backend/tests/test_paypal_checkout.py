"""Unit tests for PayPal Sandbox Checkout with Explicit Human Approval."""

import pytest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import PaymentExecutionBlockedError
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.proposal_store import proposal_store
from app.services.paypal_service import paypal_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_proposal_store():
    """Ensure clean server-side state for each test."""
    proposal_store.clear()
    paypal_service._cached_token = None
    paypal_service._token_expires_at = 0.0
    yield
    proposal_store.clear()


@pytest.fixture
def compliant_mandate():
    return PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["mechanical keyboard"],
    )


@pytest.fixture
def compliant_candidate():
    return DiscoveredProduct(
        product_id="cand_test_keyboard",
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


@pytest.fixture
def staged_compliant_record(compliant_mandate, compliant_candidate):
    """Stages a compliant candidate into server-side state."""
    tx = ProposedTransaction(
        product_name=compliant_candidate.name,
        product_description=compliant_candidate.description,
        product_price=compliant_candidate.price,
        shipping_cost=0.0,
        tax=0.0,
        additional_charges=0.0,
        final_total=compliant_candidate.price,
        currency=compliant_candidate.currency,
        merchant_name=compliant_candidate.merchant_name,
        merchant_verified=compliant_candidate.merchant_verified,
        product_condition=compliant_candidate.condition,
        add_ons=[],
    )
    eval_resp = policy_engine.evaluate_mandate(compliant_mandate, tx, caller_role="human_user")
    return proposal_store.save_staged_proposal(
        staged_proposal_id="stg_test_compliant_001",
        mandate=compliant_mandate,
        candidate=compliant_candidate,
        policy_evaluation=eval_resp,
        user_id="user_test",
    )


def test_sandbox_credentials_missing():
    """When Sandbox credentials are not configured, config returns configured=False and create-order returns 503."""
    with patch.object(settings, "PAYPAL_CLIENT_ID", ""), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", ""):

        # GET /api/v1/payments/config
        res = client.get("/api/v1/payments/config")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["client_id"] is None
        assert data["mode"] == "sandbox"
        assert data["is_sandbox"] is True

        # POST /api/v1/payments/create-order fails safely with 503
        post_res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": "stg_dummy", "user_id": "user_demo"},
        )
        assert post_res.status_code == 503
        assert "PayPal Sandbox is not configured" in post_res.json()["detail"]


@pytest.mark.asyncio
async def test_paypal_oauth_token_request():
    """OAuth token request fetches Bearer token and caches it safely."""
    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json = lambda: {
        "access_token": "ACCESS_TOKEN_MOCK_XYZ",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch("httpx.AsyncClient.post", return_value=mock_token_resp):

        token = await paypal_service.get_access_token()
        assert token == "ACCESS_TOKEN_MOCK_XYZ"
        # Second call returns cached token without calling API again
        cached = await paypal_service.get_access_token()
        assert cached == "ACCESS_TOKEN_MOCK_XYZ"


@pytest.mark.asyncio
async def test_order_creation_success(staged_compliant_record):
    """Order is created in PayPal Sandbox and mapped to internal proposal after explicit human approval."""
    # Explicit human approval must happen first
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)

    mock_order_resp = AsyncMock()
    mock_order_resp.status_code = 201
    mock_order_resp.json = lambda: {
        "id": "SANDBOX_ORDER_998877",
        "status": "CREATED",
        "links": [{"href": "https://sandbox.paypal.com/checkout", "rel": "approve"}],
    }

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch.object(paypal_service, "get_access_token", return_value="MOCK_TOKEN"), \
         patch("httpx.AsyncClient.post", return_value=mock_order_resp):

        res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_compliant_record.staged_proposal_id},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["order_id"] == "SANDBOX_ORDER_998877"
        assert data["staged_proposal_id"] == staged_compliant_record.staged_proposal_id
        assert data["amount"] == 112.50
        assert data["currency"] == "USD"
        assert data["is_sandbox"] is True
        assert data["is_demo_data"] == staged_compliant_record.candidate.is_demo_data

        # Server-side mapping must be established
        mapped = proposal_store.get_by_paypal_order_id("SANDBOX_ORDER_998877")
        assert mapped is not None
        assert mapped.staged_proposal_id == staged_compliant_record.staged_proposal_id


def test_create_order_without_prior_human_approval_is_blocked(staged_compliant_record):
    """Calling create-order on a proposal in STAGED status without prior human approval is strictly blocked."""
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_compliant_record.staged_proposal_id},
        )
        assert res.status_code == 403
        assert "Explicit human approval is required before order creation" in res.json()["detail"]


def test_blocked_candidate_cannot_create_order(compliant_mandate):
    """If a candidate in proposal_store violates mandate, order creation must be blocked."""
    # Staging an overbudget item
    overbudget_candidate = DiscoveredProduct(
        product_id="cand_overbudget",
        name="Overbudget Laptop",
        price=999.00,  # exceeds $150 limit
        currency="USD",
        condition="new",
        merchant_name="Official Store",
        merchant_verified=True,
        data_source="channel3_api",
        is_demo_data=False,
    )
    tx = ProposedTransaction(
        product_name=overbudget_candidate.name,
        product_price=overbudget_candidate.price,
        final_total=overbudget_candidate.price,
        currency="USD",
        merchant_name="Official Store",
        merchant_verified=True,
        product_condition="new",
    )
    eval_resp = policy_engine.evaluate_mandate(compliant_mandate, tx, caller_role="human_user")

    # Save to store directly to simulate tampering or stale state
    staged = proposal_store.save_staged_proposal(
        staged_proposal_id="stg_overbudget_002",
        mandate=compliant_mandate,
        candidate=overbudget_candidate,
        policy_evaluation=eval_resp,
    )
    proposal_store.record_approval(staged.staged_proposal_id)

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged.staged_proposal_id},
        )
        assert res.status_code == 403
        assert "Policy revalidation failed" in res.json()["detail"]


def test_candidate_price_cannot_be_manipulated_by_frontend(staged_compliant_record):
    """Frontend cannot override price or currency; backend derives it strictly from stored record."""
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)
    mock_order_resp = AsyncMock()
    mock_order_resp.status_code = 201
    mock_order_resp.json = lambda: {"id": "ORDER_TAMPER_TEST", "status": "CREATED"}

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch.object(paypal_service, "get_access_token", return_value="MOCK_TOKEN"), \
         patch("httpx.AsyncClient.post", return_value=mock_order_resp):

        # Client attempts to pass manipulated price/currency in JSON payload
        res = client.post(
            "/api/v1/payments/create-order",
            json={
                "staged_proposal_id": staged_compliant_record.staged_proposal_id,
                "amount": 0.01,  # Fake 1 cent injection
                "currency": "EUR",  # Fake currency injection
            },
        )
        assert res.status_code == 200
        data = res.json()
        # Price must strictly remain 112.50 USD as derived from server state!
        assert data["amount"] == 112.50
        assert data["currency"] == "USD"


def test_capture_requires_uncompromised_order_linkage():
    """Attempting to capture an order not created by TrustGate must be rejected with 403."""
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"):

        res = client.post(
            "/api/v1/payments/capture-order",
            json={"order_id": "ROGUE_UNTRACKED_PAYPAL_ORDER_ID"},
        )
        assert res.status_code == 403
        assert "Untrusted order ID" in res.json()["detail"]


@pytest.mark.asyncio
async def test_capture_response_validation_success(staged_compliant_record):
    """Capture order succeeds only when PayPal Sandbox returns COMPLETED status."""
    order_id = "SANDBOX_ORDER_CAPTURE_TEST"
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)
    proposal_store.link_paypal_order(staged_compliant_record.staged_proposal_id, order_id)

    mock_capture_resp = AsyncMock()
    mock_capture_resp.status_code = 201
    mock_capture_resp.json = lambda: {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [
            {
                "reference_id": staged_compliant_record.policy_evaluation.policy_signature,
                "payments": {
                    "captures": [
                        {
                            "id": "CAP_SUCCESS_999",
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": "112.50"},
                            "create_time": "2026-11-09T18:00:00Z",
                        }
                    ]
                },
            }
        ],
    }

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch.object(paypal_service, "get_access_token", return_value="MOCK_TOKEN"), \
         patch("httpx.AsyncClient.post", return_value=mock_capture_resp):

        res = client.post(
            "/api/v1/payments/capture-order",
            json={"order_id": order_id},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["capture_id"] == "CAP_SUCCESS_999"
        assert data["order_id"] == order_id
        assert data["amount"] == 112.50
        assert data["currency"] == "USD"
        assert data["is_sandbox"] is True
        assert data["is_demo_data"] == staged_compliant_record.candidate.is_demo_data
        assert "Sandbox" in data["receipt_notice"]


@pytest.mark.asyncio
async def test_duplicate_capture_protection_idempotency(staged_compliant_record):
    """Subsequent capture calls on an already-captured order safely return existing receipt without re-calling PayPal."""
    order_id = "ORDER_IDEMPOTENT_TEST"
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)
    proposal_store.link_paypal_order(staged_compliant_record.staged_proposal_id, order_id)
    proposal_store.mark_captured(order_id, "PREVIOUS_CAPTURE_ID_111")

    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch("httpx.AsyncClient.post") as mock_post:

        res = client.post(
            "/api/v1/payments/capture-order",
            json={"order_id": order_id},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["capture_id"] == "PREVIOUS_CAPTURE_ID_111"
        assert data["status"] == "COMPLETED"
        # Crucial check: PayPal API was not called a second time!
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_paypal_provider_errors_and_timeouts(staged_compliant_record):
    """Network timeouts to PayPal Sandbox API are caught safely as 504 Gateway Timeout."""
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)
    with patch.object(settings, "PAYPAL_CLIENT_ID", "test_client_id"), \
         patch.object(settings, "PAYPAL_CLIENT_SECRET", "test_client_secret"), \
         patch.object(paypal_service, "get_access_token", return_value="MOCK_TOKEN"), \
         patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):

        res = client.post(
            "/api/v1/payments/create-order",
            json={"staged_proposal_id": staged_compliant_record.staged_proposal_id},
        )
        assert res.status_code == 504
        assert "timed out" in res.json()["detail"].lower()


def test_payment_status_endpoint(staged_compliant_record):
    """GET /api/v1/payments/orders/{order_id} returns safe payment telemetry."""
    order_id = "ORDER_STATUS_TEST"
    proposal_store.record_approval(staged_compliant_record.staged_proposal_id)
    proposal_store.link_paypal_order(staged_compliant_record.staged_proposal_id, order_id)

    with patch.object(settings, "PAYPAL_CLIENT_ID", ""):
        res = client.get(f"/api/v1/payments/orders/{order_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["order_id"] == order_id
        assert data["status"] == "CREATED"
        assert data["captured"] is False
        assert data["amount"] == 112.50

