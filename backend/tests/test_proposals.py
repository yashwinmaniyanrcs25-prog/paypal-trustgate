"""Unit tests for Agentic Proposal Discovery, Policy Evaluation, and Selection."""

import pytest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.models.policy import PurchaseMandate
from app.models.proposal import DiscoveredProduct, ProposalSearchRequest
from app.services.product_discovery_service import product_discovery_service

client = TestClient(app)


@pytest.fixture
def standard_mandate():
    return PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["mechanical keyboard"],
    )


@pytest.mark.asyncio
async def test_demo_catalog_discovery_and_evaluation(standard_mandate):
    """Demo catalog mode must generate labeled fixtures with deterministic policy results."""
    response = await product_discovery_service.search_candidates(
        mandate=standard_mandate,
        query="mechanical keyboard",
        catalog_mode="demo",
    )

    assert response.is_demo_data is True
    assert response.catalog_mode == "demo"
    assert response.total_count == 6
    assert response.compliant_count >= 1
    assert response.blocked_count >= 1
    assert response.compliant_count + response.blocked_count == response.total_count

    # Candidate 1: Compliant
    c1 = response.candidates[0]
    assert c1.approved is True
    assert c1.status == "APPROVED"
    assert c1.can_select is True
    assert c1.selection_blocked_reason is None
    assert c1.budget_remaining >= 0
    assert c1.product.merchant_verified is True
    assert c1.product.condition == "new"

    # Candidate 2: Over budget (TG-001)
    c2 = response.candidates[1]
    assert c2.approved is False
    assert c2.status == "BLOCKED"
    assert c2.can_select is False
    assert any(v.rule_id == "TG-001" for v in c2.policy_result.violations)
    assert c2.budget_remaining < 0

    # Candidate 3: Unverified merchant (TG-004)
    c3 = response.candidates[2]
    assert c3.approved is False
    assert c3.status == "BLOCKED"
    assert c3.can_select is False
    assert any(v.rule_id == "TG-004" for v in c3.policy_result.violations)

    # Candidate 4: Prohibited condition (TG-003)
    c4 = response.candidates[3]
    assert c4.approved is False
    assert c4.status == "BLOCKED"
    assert c4.can_select is False
    assert any(v.rule_id == "TG-003" for v in c4.policy_result.violations)

    # Candidate 5: Unexpected charges & add-ons (TG-005)
    c5 = response.candidates[4]
    assert c5.approved is False
    assert c5.status == "BLOCKED"
    assert c5.can_select is False
    assert any(v.rule_id == "TG-005" for v in c5.policy_result.violations)

    # Candidate 6: Currency mismatch (TG-002)
    c6 = response.candidates[5]
    assert c6.approved is False
    assert c6.status == "BLOCKED"
    assert c6.can_select is False
    assert any(v.rule_id == "TG-002" for v in c6.policy_result.violations)


@pytest.mark.asyncio
async def test_dummyjson_catalog_external_discovery(standard_mandate):
    """External DummyJSON catalog items must be normalized and evaluated safely.

    DummyJSON items do not have merchant verification or explicit condition;
    per TrustGate policy invariants, unknown conditions cannot be assumed new
    and unknown merchants cannot be assumed verified.
    """
    mock_dummyjson_data = {
        "products": [
            {
                "id": 99,
                "title": "Ergonomic Mechanical Keyboard",
                "description": "Custom mechanical switches with programmable macro keys.",
                "category": "laptops",
                "price": 89.99,
                "brand": "KeyMaster",
                "thumbnail": "https://dummyjson.com/image.jpg",
                "images": ["https://dummyjson.com/image.jpg"],
            }
        ]
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: mock_dummyjson_data

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        response = await product_discovery_service.search_candidates(
            mandate=standard_mandate,
            query="keyboard",
            catalog_mode="external",
        )

    assert response.is_demo_data is True
    assert response.catalog_mode == "external"
    assert response.data_source == "dummyjson_api"
    assert len(response.candidates) == 1

    cand = response.candidates[0]
    assert cand.product.data_source == "dummyjson_api"
    assert cand.product.is_demo_data is True
    assert cand.product.merchant_verified is False
    assert cand.product.condition == "unknown"

    # Evaluated by TrustGate policy engine:
    # Because mandate requires verified merchant and new condition,
    # the candidate must be BLOCKED by deterministic rules TG-004 and TG-003.
    assert cand.approved is False
    assert cand.status == "BLOCKED"
    assert cand.can_select is False
    violation_rules = [v.rule_id for v in cand.policy_result.violations]
    assert "TG-004" in violation_rules or "TG-003" in violation_rules


@pytest.mark.asyncio
async def test_dummyjson_api_timeout_handled_safely(standard_mandate):
    """Network timeouts to DummyJSON must not crash the service; return safe fallback."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
        response = await product_discovery_service.search_candidates(
            mandate=standard_mandate,
            query="laptop",
            catalog_mode="external",
        )

    assert response.is_demo_data is True
    assert response.total_count == 0
    assert response.compliant_count == 0
    assert response.blocked_count == 0


def test_api_proposals_search_endpoint(standard_mandate):
    """POST /api/v1/proposals/search endpoint integration test."""
    payload = {
        "mandate": standard_mandate.model_dump(),
        "query": "laptop",
        "catalog_mode": "demo",
    }

    res = client.post("/api/v1/proposals/search", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_demo_data"] is True
    assert data["total_count"] == 6
    assert data["compliant_count"] == 1
    assert data["blocked_count"] == 5
    assert len(data["candidates"]) == 6


def test_api_proposals_stage_endpoint_success(standard_mandate):
    """Approved candidate can be staged for human review without payment execution."""
    compliant_product = DiscoveredProduct(
        product_id="cand_test_001",
        name="Test Approved Laptop",
        description="Meets all requirements",
        category="Computers",
        price=120.00,
        currency="USD",
        condition="new",
        merchant_name="Official Verified Store",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="local_demo_fixture",
        is_demo_data=True,
    )

    payload = {
        "mandate": standard_mandate.model_dump(),
        "candidate": compliant_product.model_dump(),
        "user_id": "tester_1",
    }

    res = client.post("/api/v1/proposals/stage", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["policy_approved"] is True
    assert data["requires_human_approval"] is True
    assert data["payment_executed"] is False
    assert "staged_proposal_id" in data


def test_api_proposals_stage_endpoint_blocked_rejected(standard_mandate):
    """Attempting to stage a blocked candidate must be rejected with HTTP 400."""
    blocked_product = DiscoveredProduct(
        product_id="cand_overbudget",
        name="Overbudget Laptop",
        description="Costs too much",
        category="Computers",
        price=999.00,  # exceeds mandate $150
        currency="USD",
        condition="new",
        merchant_name="Official Verified Store",
        merchant_verified=True,
        verification_status="VERIFIED",
        data_source="local_demo_fixture",
        is_demo_data=True,
    )

    payload = {
        "mandate": standard_mandate.model_dump(),
        "candidate": blocked_product.model_dump(),
        "user_id": "tester_1",
    }

    res = client.post("/api/v1/proposals/stage", json=payload)
    assert res.status_code == 400
    assert "Policy evaluation blocked this item" in res.json()["detail"]

