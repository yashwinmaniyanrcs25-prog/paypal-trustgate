"""Unit tests for the Groq-powered Natural Language Purchase Intent Interpreter."""

import json
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.intent_interpreter_service import intent_interpreter_service
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.services.policy_engine import policy_engine

client = TestClient(app)

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# Type alias used for all class-level mocking of Pydantic BaseSettings methods.
# patch.object(settings, ...) fails on Pydantic v2 instances because they block
# arbitrary attribute assignment. patch.object(type(settings), ...) patches at the
# class level, which Pydantic permits and which all existing singleton references pick up.
_SettingsClass = type(settings)

SAMPLE_VALID_GROQ_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "max_amount": 60000.0,
                        "currency": "INR",
                        "allowed_conditions": ["new"],
                        "require_merchant_verification": True,
                        "allow_add_ons": False,
                        "user_restrictions": ["laptop only", "no refurbished", "no accessories"],
                        "needs_clarification": False,
                        "clarification_prompt": None,
                        "extracted_intent_summary": "New laptop under INR 60,000 from verified seller only. No refurbished or accessories.",
                    }
                )
            }
        }
    ]
}

SAMPLE_AMBIGUOUS_GROQ_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "max_amount": None,
                        "currency": "USD",
                        "allowed_conditions": ["new"],
                        "require_merchant_verification": True,
                        "allow_add_ons": False,
                        "user_restrictions": ["laptop only"],
                        "needs_clarification": True,
                        "clarification_prompt": "A maximum budget limit is required to create a safe purchase mandate. Please specify your maximum spending limit and currency.",
                        "extracted_intent_summary": "Looking for a laptop with no budget constraint.",
                    }
                )
            }
        }
    ]
}


@pytest.mark.asyncio
async def test_valid_groq_intent_interpretation():
    """Valid natural language prompt correctly maps to PurchaseMandate via Groq."""
    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(SAMPLE_VALID_GROQ_RESPONSE).encode(),
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch.object(_SettingsClass, "get_ai_base_url", autospec=True, return_value="https://api.groq.com/openai/v1"):
                with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                    prompt = "I need a new laptop under ₹60,000. Only buy from a verified seller. No refurbished products and no accessories."
                    res = await intent_interpreter_service.interpret_intent(prompt)

                    assert res.success is True
                    assert res.status == "SUCCESS"
                    assert res.needs_clarification is False
                    assert res.mandate is not None
                    assert res.mandate.max_amount == 60000.0
                    assert res.mandate.currency == "INR"
                    assert res.mandate.allowed_conditions == ["new"]
                    assert res.mandate.require_merchant_verification is True
                    assert res.mandate.allow_add_ons is False
                    assert "laptop only" in res.mandate.user_restrictions


@pytest.mark.asyncio
async def test_groq_request_payload_uses_configured_model():
    """Verify that the HTTP request sent to Groq includes the configured model identifier (openai/gpt-oss-120b)."""
    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(SAMPLE_VALID_GROQ_RESPONSE).encode(),
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
                prompt = "I need a new laptop under ₹60,000."
                res = await intent_interpreter_service.interpret_intent(prompt)

                assert res.success is True
                mock_post.assert_called_once()
                call_kwargs = mock_post.call_args.kwargs
                assert "json" in call_kwargs
                assert call_kwargs["json"]["model"] == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_missing_budget_requires_clarification():
    """Ambiguous or missing budget prompts trigger a clarification requirement instead of guessing."""
    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(SAMPLE_AMBIGUOUS_GROQ_RESPONSE).encode(),
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                prompt = "Looking for a high-performance laptop."
                res = await intent_interpreter_service.interpret_intent(prompt)

                assert res.success is True
                assert res.status == "NEEDS_CLARIFICATION"
                assert res.needs_clarification is True
                assert res.mandate is None
                assert "budget" in res.clarification_prompt.lower()


@pytest.mark.asyncio
async def test_api_key_missing_never_fabricates_output():
    """Missing API key returns PROVIDER_UNCONFIGURED and never silently invents output."""
    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value=""):
        res = await intent_interpreter_service.interpret_intent("Buy a laptop under $1000")

        assert res.success is False
        assert res.status == "PROVIDER_UNCONFIGURED"
        assert res.mandate is None
        assert "AI_API_KEY" in res.error_message


@pytest.mark.asyncio
async def test_model_unconfigured_or_placeholder():
    """Unconfigured model name returns clear configuration error without silent guessing."""
    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value=""):
            res = await intent_interpreter_service.interpret_intent("Buy a laptop under $1000")

            assert res.success is False
            assert res.status == "PROVIDER_UNCONFIGURED"
            assert "AI_MODEL" in res.error_message
            assert "groq.com/docs/models" in res.error_message


@pytest.mark.asyncio
async def test_groq_provider_timeout_error():
    """Provider timeout handled gracefully without crashing."""
    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timed out")):
                res = await intent_interpreter_service.interpret_intent("Buy a mouse under $50")

                assert res.success is False
                assert res.status == "PROVIDER_ERROR"
                assert "timed out" in res.error_message.lower()


@pytest.mark.asyncio
async def test_groq_provider_404_model_not_found():
    """Groq 404 model error gives clean sanitized message without exposing secrets."""
    mock_response = httpx.Response(
        status_code=404,
        content=json.dumps({"error": {"message": "Model not found"}}).encode(),
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="non-existent-model"):
            with patch("httpx.AsyncClient.post", side_effect=httpx.HTTPStatusError("404", request=mock_response.request, response=mock_response)):
                res = await intent_interpreter_service.interpret_intent("Buy a mouse")

                assert res.success is False
                assert res.status == "PROVIDER_ERROR"
                assert "404" in res.error_message
                assert "gsk_" not in res.error_message  # Never leak key


@pytest.mark.asyncio
async def test_malformed_json_from_groq():
    """Malformed non-JSON provider output handled gracefully."""
    mock_response = httpx.Response(
        status_code=200,
        content=b"I am an AI, here is your mandate: {not valid json",
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                res = await intent_interpreter_service.interpret_intent("Buy a keyboard")

                assert res.success is False
                assert res.status == "VALIDATION_ERROR"
                assert "non-json" in res.error_message.lower()


def test_api_endpoint_intent_interpret():
    """FastAPI POST /api/v1/intent/interpret endpoint returns valid HTTP response."""
    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(SAMPLE_VALID_GROQ_RESPONSE).encode(),
        request=httpx.Request("POST", GROQ_ENDPOINT),
    )

    with patch.object(_SettingsClass, "get_ai_api_key", autospec=True, return_value="gsk_test_key_12345"):
        with patch.object(_SettingsClass, "get_ai_model", autospec=True, return_value="openai/gpt-oss-120b"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                response = client.post(
                    "/api/v1/intent/interpret",
                    json={"prompt": "I need a new laptop under ₹60,000. Verified seller only."},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["status"] == "SUCCESS"
                assert data["mandate"]["max_amount"] == 60000.0
                assert data["mandate"]["currency"] == "INR"


def test_user_edited_mandate_evaluates_in_policy_engine():
    """User can edit the Groq-interpreted mandate and evaluate it with the deterministic policy engine."""
    # 1. Groq originally interpreted laptop under INR 60,000
    ai_mandate = PurchaseMandate(
        max_amount=60000.0,
        currency="INR",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
    )

    # 2. User edits mandate: increases budget cap to INR 65,000
    user_confirmed_mandate = ai_mandate.model_copy(update={"max_amount": 65000.0})

    # 3. Candidate transaction: Laptop for INR 62,000 (would fail under 60k, passes under user confirmed 65k)
    transaction = ProposedTransaction(
        product_name="Lenovo IdeaPad Slim 3 15-inch",
        product_description="Intel Core i5 12th Gen, 16GB RAM, 512GB SSD",
        product_price=58000.0,
        shipping_cost=0.0,
        tax=4000.0,
        additional_charges=0.0,
        final_total=62000.0,
        currency="INR",
        merchant_name="Lenovo Official India Direct",
        merchant_verified=True,
        product_condition="new",
        add_ons=[],
    )

    # 4. Evaluate in deterministic policy engine
    evaluation = policy_engine.evaluate_mandate(user_confirmed_mandate, transaction)

    assert evaluation.approved is True
    assert evaluation.status == "APPROVED"
    assert evaluation.mandate_summary["max_amount"] == 65000.0
    assert evaluation.mandate_summary["currency"] == "INR"
    assert evaluation.transaction_summary["final_total"] == 62000.0
