"""Unit tests for PayPal Sandbox OAuth verification endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.paypal_service import paypal_service

client = TestClient(app)


def test_verify_auth_endpoint_is_sandbox():
    """Verify that the auth endpoint strictly tests against Sandbox."""
    res = client.get("/api/v1/payments/verify-auth")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "sandbox"
    assert data["target_api"] == "https://api-m.sandbox.paypal.com"
    assert data.get("is_sandbox") is True
    assert data.get("live_mode_blocked") is True


def test_config_endpoint_never_exposes_secret():
    """Verify public config returns client_id if configured, but NEVER secret."""
    res = client.get("/api/v1/payments/config")
    assert res.status_code == 200
    data = res.json()
    assert "client_secret" not in data
    assert "secret" not in data
    assert data["mode"] == "sandbox"
    assert data["is_sandbox"] is True
    assert data["base_url"] == "https://api-m.sandbox.paypal.com"

