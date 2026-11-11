# PayPal TrustGate — Automated Testing & Verification Guide

This document describes the test architecture, database isolation guarantees, security negative test suite, and execution procedures for the **PayPal TrustGate** project.

---

## 1. Test Architecture Overview

TrustGate utilizes a dual-tier testing methodology:
1. **Backend Integration & Policy Test Suite (Pytest)**:
   - Tests deterministic rule evaluations (TG-001 through TG-007).
   - Validates the strict 8-state transaction lifecycle state machine.
   - Enforces pre-flight PayPal Orders v2 schema compliance.
   - Executes mandatory security attack scenarios (TEST 1 – TEST 8).
   - Simulates the full 14-step purchase lifecycle from natural language intent to settled capture.
2. **Frontend End-to-End Test Suite (Playwright)**:
   - Validates all 7 top-level navigation views and sub-tabs.
   - Confirms user experience around candidate discovery, policy badge rendering, and human operator sign-off.
   - Verifies the non-bypassable human approval gate prior to PayPal Sandbox checkout handoff.

---

## 2. Test Database Isolation

All automated tests use isolated temporary SQLite databases dynamically provisioned via pytest's `tmp_path` fixture.

- **Isolation Guarantee**: Tests instantiate temporary databases such as `tmp_path / "test_lifecycle.db"` or `tmp_path / "test_security_negative.db"`.
- **Zero Pollution**: Tests **never** mutate, overwrite, or drop the development database located at `backend/data/trustgate.db`.
- **Append-Only Trigger Verification**: Each isolated test database compiles the exact production SQLite triggers (`trg_audit_no_update`, `trg_audit_no_delete`) to enforce mathematical append-only guarantees.

---

## 3. Backend Test Suite Execution

### Running All Backend Tests
From the project root:
```powershell
pytest backend/tests/ -v
```

### Running Targeted Test Modules
```powershell
# 1. Deterministic Policy Engine (TG-001 to TG-007)
pytest backend/tests/test_policy_engine.py -v

# 2. Strict Transaction State Machine & SQLite Persistence
pytest backend/tests/test_state_machine.py -v

# 3. Mandatory Security Negative Attack Scenarios (TEST 1 - TEST 8)
pytest backend/tests/test_security_negative.py -v

# 4. 14-Step Complete Purchase Lifecycle Verification
pytest backend/tests/test_full_purchase_lifecycle.py -v

# 5. Channel3 Universal Multi-Merchant Product Graph Service
pytest backend/tests/test_channel3_service.py -v

# 6. Groq Natural Language Purchase Intent Interpreter
pytest backend/tests/test_intent_interpreter.py -v

# 7. PayPal Orders v2 Schema Pre-flight Validator
pytest backend/tests/test_paypal_order_validator.py -v

# 8. Product Discovery & Pricing Engine Regression Suite (Zero/Missing Price Filtering)
pytest backend/tests/test_product_discovery_regression.py -v

# 9. Purchase Journey Hardening & State Locking Suite (Phase 4.2)
pytest backend/tests/test_purchase_journey_hardening.py -v

# 10. Audit Log & Ledger Synchronization Suite (Phase 4.3)
pytest backend/tests/test_audit_synchronization.py -v

# 11. Persistent SQLite Audit Storage & Timeline Suite
pytest backend/tests/test_audit_persistence.py -v
```

---

## 4. Mandatory Security Negative Tests (TEST 1 - TEST 8)

The test file `backend/tests/test_security_negative.py` implements 8 attack and boundary scenarios:

| Test ID | Scenario | Attack Vector | Expected Enforcement |
| :--- | :--- | :--- | :--- |
| **TEST 1** | Unapproved Checkout | Proposal in `STAGED` state attempts `create_sandbox_order` | `PaymentExecutionBlockedError` (HTTP 403 Forbidden). State remains `STAGED`. |
| **TEST 2** | Policy Budget Breach | Candidate final total exceeds mandate maximum | Blocked by **TG-001**. Policy engine returns `approved=False`. |
| **TEST 3** | Merchant Restriction | Seller is unverified or on blacklisted vendor list | Blocked by **TG-004**. Item rejected. |
| **TEST 4** | Client Price Manipulation | Frontend sends manipulated lower final total | Blocked by **TG-006** / math integrity check (sum of components mismatch). |
| **TEST 5** | Rejected Proposal Checkout | Proposal in terminal `HUMAN_REJECTED` attempts checkout | `InvalidStateTransitionError` / `PaymentExecutionBlockedError`. |
| **TEST 6** | Duplicate Capture Replay | Second capture attempt on already `CAPTURED` order | Idempotent response returns existing receipt; transition rejected. |
| **TEST 7** | Autonomous AI Authorization | `caller_role="ai_agent"` attempts order creation | Blocked by **TG-007**. Direct AI payment authorization strictly barred. |
| **TEST 8** | Cryptographic Tamper Detection | Raw SQLite update directly alters historical event details | `verify_audit_integrity` flags broken SHA-256 chain and reports first invalid sequence. |

---

## 5. Playwright Frontend E2E Test Suite

### Installation & Prerequisites
From the `frontend/` directory:
```powershell
cd frontend
npm install
npx playwright install --with-deps chromium
```

### Running Playwright Tests
```powershell
# Run all end-to-end browser tests headlessly
npm run test:e2e

# Run with interactive UI mode
npx playwright test --ui

# Run a specific spec
npx playwright test e2e/navigation.spec.ts
npx playwright test e2e/approval.spec.ts

# View HTML Test Execution Report
npx playwright show-report
```

### E2E Test Specifications Coverage:
1. `frontend/e2e/dashboard.spec.ts`: Executive trust telemetry, 4 core status cards, "ZERO AUTH" badge, quick action links.
2. `frontend/e2e/navigation.spec.ts`: Seamless switching across all 7 top-level navigation views.
3. `frontend/e2e/discovery.spec.ts`: Multi-marketplace candidate discovery, Channel3 & Demo mode switching, candidate card evaluations.
4. `frontend/e2e/proposal-staging.spec.ts`: AI Intent Mandate Composer, prompt presets, Policy Rule Matrix (TG-001 - TG-007).
5. `frontend/e2e/approval.spec.ts`: Approval Center queue, operator ID, PIN input, explicit non-AI confirmation checkbox, rejection flow.
6. `frontend/e2e/transactions.spec.ts`: Persisted transaction ledger, status pills (`STAGED`, `HUMAN_APPROVED`, `CAPTURED`), inspection modal.
7. `frontend/e2e/audit.spec.ts`: Cryptographic hash chain banner, unbroken chain status, event sequence inspection.
8. `frontend/e2e/security-boundaries.spec.ts`: Non-autonomous AI constraints, zero-auth indicators, approval gate barrier.

---

## 6. Live API Verification (Optional / Standalone)

For verifying live external network services with actual credentials configured in `backend/.env`:

```powershell
# Verify Live Channel3 Multi-Merchant Product Graph
python backend/test_channel3_live.py

# Verify APIMatic PayPal Pre-flight Schema Validator
python backend/test_apimatic_live.py
```

