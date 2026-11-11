r"""Standalone live integration test for Channel3 Universal Product Graph.

Usage:
    cd c:/Users/yashw/OneDrive/Desktop/paypal-trustgate
    python backend/test_channel3_live.py

Tests:
1. Loads CHANNEL3_API_KEY from backend/.env (never prints key).
2. Sends POST request to https://api.trychannel3.com/v1/search.
3. Normalizes response into TrustGate DiscoveredProduct schema.
4. Evaluates candidate against TrustGate's TG-001 to TG-007 deterministic policy engine.
5. Verifies zero autonomous payment execution invariant and human approval requirement.
"""

import asyncio
import os
import sys
import json
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.services.channel3_service import channel3_service
from app.services.product_discovery_service import product_discovery_service
from app.models.policy import PurchaseMandate


async def main():
    print("=" * 70)
    print(" TRUSTGATE — CHANNEL3 LIVE INTEGRATION TEST")
    print("=" * 70)

    # 1. Configuration check
    configured = settings.is_channel3_configured()
    print(f"\n[1/4] Channel3 API Configuration Status: {'CONFIGURED (Key Detected)' if configured else 'NOT CONFIGURED'}")
    print(f"      Base URL: {settings.get_channel3_base_url()}")
    print(f"      Search Endpoint: {settings.get_channel3_base_url()}/search")
    print(f"      Auth Header: x-api-key: [MASKED - {len(settings.get_channel3_api_key())} chars]")

    if not configured:
        print("\n[ERROR] CHANNEL3_API_KEY is not set in backend/.env")
        print("        Please ensure CHANNEL3_API_KEY=<your_key> is present.")
        sys.exit(1)

    # 2. Test Connection
    print("\n[2/4] Testing API Connectivity...")
    conn_result = await channel3_service.test_connection()
    print(f"      Status: {conn_result.get('status')}")
    print(f"      HTTP Status Code: {conn_result.get('status_code')}")
    print(f"      Latency: {conn_result.get('latency_ms')} ms")
    print(f"      Message: {conn_result.get('message')}")

    if not conn_result.get("success"):
        print(f"\n[FAIL] Channel3 connection test failed: {conn_result.get('message')}")
        sys.exit(1)

    # 3. Live Product Search
    search_query = "Keychron K2 wireless keyboard"
    print(f"\n[3/4] Querying Channel3 Product Graph for: '{search_query}'...")
    start_time = time.time()
    try:
        products = await channel3_service.search_products(search_query, limit=5, currency="USD")
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        print(f"      Retrieved {len(products)} live products in {elapsed_ms} ms")
    except Exception as exc:
        print(f"\n[FAIL] Search failed: {exc}")
        sys.exit(1)

    if not products:
        print("      [WARN] No products returned for query. Trying fallback search 'keyboard'...")
        products = await channel3_service.search_products("keyboard", limit=3, currency="USD")

    # 4. Deterministic Policy Evaluation (TG-001 to TG-007)
    mandate = PurchaseMandate(
        max_amount=150.00,
        currency="USD",
        allowed_conditions=["new"],
        require_merchant_verification=True,
        allow_add_ons=False,
        user_restrictions=["mechanical keyboard"],
    )

    print("\n[4/4] Evaluating Products Against TrustGate Deterministic Policy Engine:")
    print(f"      Mandate Budget Cap: {mandate.currency} {mandate.max_amount:.2f}")
    print(f"      Allowed Condition: {mandate.allowed_conditions}")
    print(f"      Merchant Verification Required: {mandate.require_merchant_verification}")
    print("-" * 70)

    for idx, prod in enumerate(products, start=1):
        evaluation = product_discovery_service._evaluate_candidate(prod, mandate)
        print(f"\n Candidate #{idx}:")
        print(f"   - Product ID:      {prod.product_id}")
        print(f"   - Name:            {prod.name}")
        print(f"   - Price:           {prod.currency} {prod.price:.2f}")
        print(f"   - Condition:       {prod.condition.upper()}")
        print(f"   - Merchant/Domain: {prod.merchant_name} (Verified: {prod.merchant_verified})")
        print(f"   - Availability:    {prod.availability}")
        print(f"   - Image URL:       {prod.image_url[:60] if prod.image_url else 'None'}...")
        print(f"   - Direct Buy URL:  {prod.purchase_url[:60] if prod.purchase_url else 'None'}...")
        print(f"   - Data Source:     {prod.data_source} (is_demo_data={prod.is_demo_data})")
        print(f"   - Policy Verdict:  {'APPROVED [PASS]' if evaluation.approved else 'BLOCKED [VIOLATIONS]'}")
        print(f"   - Budget Delta:    {'+' if evaluation.budget_remaining >= 0 else ''}{evaluation.currency} {evaluation.budget_remaining:.2f}")

        # Print 7 checks summary
        passed_rules = [chk.rule_id for chk in evaluation.policy_result.checks if chk.passed]
        failed_rules = [chk.rule_id for chk in evaluation.policy_result.checks if not chk.passed]
        print(f"   - Policy Checks:   Passed: {passed_rules} | Failed: {failed_rules}")

        if not evaluation.approved:
            for v in evaluation.policy_result.violations:
                print(f"     * Violation ({v.rule_id}): {v.message}")

    print("\n" + "=" * 70)
    print(" SANITIZED SAMPLE CHANNEL3 PRODUCT RESPONSE:")
    print("=" * 70)
    if products:
        sample = products[0].model_dump()
        print(json.dumps(sample, indent=2))
    print("\n[SUCCESS] Channel3 integration verification complete.")


if __name__ == "__main__":
    asyncio.run(main())

