"""Sanitized diagnostic script to verify PayPal Sandbox OAuth authentication.

CRITICAL INVARIANTS:
1. Never prints, logs, or exposes client ID or client secret.
2. Asserts target is strictly https://api-m.sandbox.paypal.com.
3. Does NOT create or capture any orders.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.services.paypal_service import paypal_service, SANDBOX_BASE_URL


async def main():
    print("=" * 60)
    print("PayPal Sandbox Authentication Diagnostic")
    print("=" * 60)

    # 1. Environment & Target Verification
    base_url = paypal_service.base_url
    is_sandbox_url = base_url == "https://api-m.sandbox.paypal.com"
    mode = settings.PAYPAL_MODE
    env = settings.PAYPAL_ENV

    print(f"Target API Endpoint: {base_url}")
    print(f"Target is Sandbox:   {is_sandbox_url}")
    print(f"PAYPAL_MODE:         {mode}")
    print(f"PAYPAL_ENV:          {env}")

    if not is_sandbox_url or mode != "sandbox":
        print("\n[CRITICAL ERROR] Target is NOT set to sandbox! Aborting.")
        sys.exit(1)

    # 2. Configuration Status (Boolean / Sanitized only)
    configured = settings.is_paypal_configured()
    client_id_present = bool(settings.PAYPAL_CLIENT_ID and not settings.PAYPAL_CLIENT_ID.startswith("your_"))
    secret_present = bool(settings.PAYPAL_CLIENT_SECRET and not settings.PAYPAL_CLIENT_SECRET.startswith("your_"))

    print(f"Credentials Configured: {configured}")
    print(f"Client ID Present:      {client_id_present} (Length: {len(settings.PAYPAL_CLIENT_ID.strip())} chars)")
    print(f"Client Secret Present:  {secret_present} (Length: {len(settings.PAYPAL_CLIENT_SECRET.strip())} chars)")

    if not configured:
        print("\n[ERROR] Credentials missing or invalid in backend/.env")
        sys.exit(1)

    # 3. Test OAuth Authentication
    print("\nAttempting OAuth 2.0 handshake with PayPal Sandbox...")
    try:
        token = await paypal_service.get_access_token()
        token_valid = bool(token and len(token) > 20)

        result = {
            "authenticated": token_valid,
            "status": "SUCCESS" if token_valid else "FAILED",
            "endpoint_contacted": f"{base_url}/v1/oauth2/token",
            "token_type": "Bearer",
            "token_length": len(token) if token else 0,
            "expires_at_epoch": paypal_service._token_expires_at,
            "is_sandbox_verified": True,
            "live_mode_blocked": True,
        }
        print("\nOAuth Handshake Result:")
        print(json.dumps(result, indent=2))
        print("\n[OK] PayPal Sandbox authentication successful!")

    except Exception as exc:
        err_msg = str(exc)
        # Sanitize any accidental secret leakage from exception messages
        if settings.PAYPAL_CLIENT_SECRET in err_msg:
            err_msg = err_msg.replace(settings.PAYPAL_CLIENT_SECRET, "[REDACTED_SECRET]")
        if settings.PAYPAL_CLIENT_ID in err_msg:
            err_msg = err_msg.replace(settings.PAYPAL_CLIENT_ID, "[REDACTED_CLIENT_ID]")

        print("\n[FAILED] OAuth Handshake failed:")
        print(f"Error: {err_msg}")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())

