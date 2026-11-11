# PayPal TrustGate
### A Human-Controlled AI Payment Security Layer for Agentic Commerce

> **Our Vision:** Let AI handle the intelligence of shopping, while humans retain control of the money.

---

### The Problem

As AI agents become capable of discovering products and initiating purchases, giving them unrestricted payment authority creates serious risks. Autonomous purchasing can lead to unauthorized transactions, policy violations, budget overruns, and a lack of accountability.

### Our Solution

PayPal TrustGate introduces a deterministic security and authorization layer between AI-powered product discovery and payment execution.

It allows AI to assist with purchasing decisions while ensuring that financial authorization remains strictly under human control.

### How It Works

1. **AI-Powered Discovery:** Uses AI and Channel3 to discover and evaluate marketplace products against the user's purchasing intent.
2. **Deterministic Policy Enforcement:** Validates purchase proposals against configured budgets, merchant restrictions, product conditions, and purchasing rules.
3. **Proposal Staging:** Records eligible purchases for human review rather than allowing immediate execution.
4. **Explicit Human Authorization:** Requires the user to review and approve the purchase before checkout.
5. **PayPal Sandbox Checkout:** Creates and captures PayPal Sandbox orders only after authorization and server-side policy revalidation.
6. **Cryptographic Audit Trail:** Records purchasing milestones in an append-only SHA-256 hash-chained ledger.

### What Makes TrustGate Different

TrustGate separates AI decision assistance from financial authority. The AI can discover, evaluate, and recommend purchases, but it cannot independently authorize or execute payments.

Every purchase follows a controlled lifecycle with deterministic policy enforcement, explicit human approval, and verifiable audit records.

---

## 🛡️ Core Security Invariant

```
┌─────────────────┐       ┌──────────────────────┐       ┌────────────────────────┐
│  User Natural   │ ───▶  │  AI Agent (Grok API) │ ───▶  │  TrustGate Policy     │
│  Language Order │       │  Product Proposals   │       │  Deterministic Engine  │
└─────────────────┘       └──────────────────────┘       └───────────┬────────────┘
                                                                     │
                                     ┌───────────────────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │  Rule Invariant Checks:         │
                    │  • TG-001: Spending Limit/Math  │
                    │  • TG-002: Currency Alignment   │
                    │  • TG-003: Product Condition    │
                    │  • TG-004: Merchant Trust       │
                    │  • TG-005: Add-On Protection    │
                    │  • TG-006: Data Integrity       │
                    │  • TG-007: ZERO AI Autonomy     │
                    └────────────────┬────────────────┘
                                     │ Passed
                                     ▼
                    ┌─────────────────────────────────┐
                    │  Mandatory User Approval Gate   │
                    │  (Human-in-the-Loop)            │
                    └────────────────┬────────────────┘
                                     │ Approved
                                     ▼
                    ┌─────────────────────────────────┐
                    │  PayPal Sandbox Checkout API    │
                    └─────────────────────────────────┘
```

1. **AI Proposes, Engine Disposes**: Grok/Groq decomposes natural language into structured purchase mandates. The AI operates in a strictly read-only, advisory capability.
2. **Product Discovery & Candidate Normalization**: Catalogs (local deterministic fixtures or DummyJSON external demonstration) are normalized and evaluated candidates are tagged as demo data.
3. **Deterministic Policy Evaluation**: Strict rules mathematically assert that price, merchant, currency, condition, and add-ons match the user's original mandate.
4. **Zero Autonomous Payment Rights**: No agent tool call or programmatic path exists for an AI model to trigger transactions directly. Non-compliant candidates cannot even be selected.
5. **Mandatory Human-in-the-Loop**: Candidate approval by policy does NOT execute or authorize payment. Every purchase requires explicit user confirmation before handoff to PayPal Sandbox.

---

## 🛠️ Technology and Integrations

- **AI-Powered Product Discovery & Evaluation**: Groq / OpenAI-compatible API (`openai/gpt-oss-120b`) for natural language mandate decomposition and candidate matching
- **Channel3 Marketplace Integration**: Live multi-merchant catalog discovery across Amazon and verified merchant networks
- **Deterministic Purchasing Policy Engine**: Mathematical enforcement of 7 core security invariants (`TG-001` through `TG-007`) with zero autonomous payment authority
- **FastAPI Backend**: High-performance asynchronous Python 3.10+ backend with Pydantic v2 schema validation
- **React Frontend**: React 18, Vite, TypeScript, Tailwind CSS, and Framer Motion
- **SQLite Transaction & Audit Persistence**: Persistent ACID database with WAL mode (`backend/data/trustgate.db`)
- **PayPal Orders v2 Sandbox Integration**: Standard PayPal REST API v2 with server-side pricing derivation and client-side SDK approval handoff
- **Cryptographic Audit Integrity**: Append-only SHA-256 hash chaining and tamper-evident HMAC policy signatures

---

## 📂 Project Structure

```
paypal-trustgate/
├── frontend/                     # React + Vite + TypeScript frontend
│   ├── public/                   # Static assets & branding
│   ├── src/
│   │   ├── components/           # UI components (Navbar, StatusCard, PolicyVisualizer, etc.)
│   │   ├── pages/                # Page views (Dashboard)
│   │   ├── features/             # Domain logic (purchasing hooks & state)
│   │   ├── lib/                  # Utilities and API clients
│   │   ├── types/                # TypeScript interfaces & domain models
│   │   ├── App.tsx               # Root component with layout
│   │   ├── main.tsx              # Application entrypoint
│   │   └── index.css             # Tailwind base & custom styles
│   ├── index.html                # HTML entrypoint
│   ├── vite.config.ts            # Vite build configuration
│   ├── tsconfig.json             # TypeScript configuration
│   ├── tailwind.config.js        # Fintech dark navy & emerald theme
│   ├── postcss.config.js         # PostCSS configuration
│   ├── .env.example              # Frontend environment template
│   └── package.json              # Frontend dependencies and scripts
├── backend/                      # FastAPI Python backend
│   ├── app/
│   │   ├── api/                  # API routers (v1 endpoints: agent, policy, health)
│   │   │   ├── v1/
│   │   │   │   ├── agent.py      # Grok agent proposal endpoint
│   │   │   │   ├── policies.py   # Deterministic policy evaluation endpoint
│   │   │   │   └── health.py     # System health and status
│   │   │   └── routes.py         # Consolidated API router
│   │   ├── core/                 # Core configs, invariants, and security settings
│   │   │   ├── config.py         # Pydantic BaseSettings
│   │   │   └── security.py       # Core policy invariants
│   │   ├── models/               # Domain Pydantic models
│   │   │   ├── purchase.py       # Purchase request & validation models
│   │   │   └── policy.py         # Policy rules and violation schemas
│   │   ├── services/             # Modular integrations
│   │   │   ├── grok_service.py   # Grok API client (OpenAI-compatible)
│   │   │   ├── policy_engine.py  # Deterministic verification engine
│   │   │   ├── paypal_service.py # PayPal sandbox integration
│   │   │   └── supabase_service.py # Supabase persistence & audit trail
│   │   └── main.py               # FastAPI entrypoint with CORS & middleware
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example              # Backend environment template
│   └── .gitignore
├── .gitignore                    # Monorepo gitignore
└── README.md                     # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Node.js**: v18+ and `npm` (or `pnpm` / `yarn`)
- **Python**: 3.10 or higher
- Optional: PayPal Developer Sandbox account, xAI Grok API key, Supabase account

---

### 2. Backend Setup (FastAPI)

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your Grok, PayPal, and Supabase credentials
   ```

5. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   The backend API will be available at `http://localhost:8000`.
   Interactive Swagger documentation is available at `http://localhost:8000/docs`.

6. Run the automated test suite:
   ```bash
   pytest
   # Or run specific test modules:
   pytest tests/test_product_discovery_regression.py
   pytest tests/test_purchase_journey_hardening.py
   pytest tests/test_security_negative.py
   pytest tests/test_audit_synchronization.py
   pytest tests/test_audit_persistence.py
   pytest tests/test_full_purchase_lifecycle.py
   pytest tests/test_policy_engine.py
   pytest tests/test_state_machine.py
   pytest tests/test_channel3_service.py
   pytest tests/test_intent_interpreter.py
   pytest tests/test_paypal_order_validator.py
   ```

---

### 💳 PayPal Sandbox Checkout Architecture & Security Invariants

TrustGate implements the official PayPal Sandbox REST Orders v2 API with strict human-in-the-loop controls:

1. **AI Zero Authorization Invariant**: Autonomous AI agents can never create or capture orders. The payment authorizer must be an explicit human buyer in PayPal Sandbox.
2. **Server-Side Price Derivation**: The backend never trusts prices, currency, or approval statuses sent from the frontend. All transaction parameters are strictly derived from trusted server-side state (`proposal_store`).
3. **Mandate Revalidation Gate**: The policy engine re-verifies the candidate against the user's purchase mandate immediately before creating the PayPal Sandbox order.
4. **Internal Proposal & PayPal Order Linkage**: Orders are stored and linked server-side. Captures are accepted only for orders created by TrustGate that map to an approved proposal.
5. **Idempotency & Duplicate Protection**: Orders and captures utilize unique idempotency keys (`PayPal-Request-Id`) and check server state to safely handle repeated capture requests without duplicate charges.
6. **Transparent Sandbox Disclosure**: Demo catalog items are explicitly disclosed as simulated fixtures. Receipts clearly state that Sandbox test transactions do not transfer real currency.

---

### 🏛️ Trust & Audit Layer Architecture

TrustGate provides an immutable, transparent, and restart-resilient audit layer:

1. **Persistent ACID Data Layer (`backend/data/trustgate.db`)**:
   - Replaces ephemeral in-memory storage with SQLite WAL mode.
   - Persists purchase mandates, candidate proposals, deterministic policy evaluations, staged transactions, explicit human approvals, and PayPal Sandbox captures across application restarts.
2. **6-Stage Transaction Lifecycle Timeline**:
   - `Stage 1: Natural Language Mandate`: Extracted budget caps, allowed conditions, merchant trust, and add-on rules.
   - `Stage 2: Proposal Discovery`: Candidate product details, price, merchant, condition, and authentic vs demo data source.
   - `Stage 3: Deterministic Policy Check`: Comprehensive breakdown of all 7 guardrails (`TG-001` through `TG-007`) and SHA-256 HMAC policy signature.
   - `Stage 4: Explicit Human Authorization`: Operator identification, timestamp, and verification that no AI model signed off.
   - `Stage 5: PayPal Sandbox Checkout Order`: Server-created PayPal order ID, amount, currency, and sandbox parameters.
   - `Stage 6: Verified Receipt & Capture`: PayPal capture ID, timestamp, completed status, and cryptographic signature proof.
3. **Dedicated Audit API Endpoints**:
   - `GET /api/v1/audit/events`: Filtered stream of immutable lifecycle events.
   - `GET /api/v1/audit/timeline/{transaction_id}`: Reconstructed 6-stage lifecycle for any transaction.
   - `GET /api/v1/audit/transactions`: List of all persisted transactions for interactive UI switching.
   - `GET /api/v1/audit/summary`: Database telemetry, total events, approved/blocked counts, and engine status.
4. **Honest Security & Storage Disclosures**:
   - SQLite disk persistence and SHA-256 HMAC signatures are clearly disclosed without pretending to be a blockchain or multi-party distributed cryptographic ledger.

---

### 🛒 Amazon Marketplace Architecture & Licensing Notice

TrustGate integrates with Amazon using the official **Amazon Creators API** (successor to PA-API 5.0) via a decoupled provider adapter architecture:

- **Zero Scraping & Zero Infiltration**: TrustGate strictly refuses to parse Amazon HTML, scrape product listings, or bypass bot detection mechanisms.
- **Access State Transparency**: Missing or unapproved Amazon API credentials are treated as explicit configuration/access states (`Not Configured`, `Credentials Missing`, `Access Pending`, `Connected`, `Error`), never as an empty successful search, and never filled with synthetic Amazon items.
- **Licensing Compliance**: All Amazon product content, pricing, and availability are subject to Amazon's Associates Program Operating Agreement and Creators API License Terms. Intended use must be checked against Amazon's current API license and any required written approval.
- **Deterministic Policy Separation**: Product catalog results are never sent to Groq or any LLM. The deterministic TrustGate policy engine evaluates candidate items against mathematical invariants.
- **Demo Isolation**: TrustGate Demo Catalog fixtures run in a separate adapter and are never mixed into Amazon results. Demo candidates are barred from real payment execution.

---

### 3. Frontend Setup (React + Vite)

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Ensure VITE_API_BASE_URL points to http://localhost:8000
   ```

4. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The frontend application will be available at `http://localhost:5173`.

---

## 🔒 Security Principles

1. **Defense-in-Depth for Agentic Commerce**: Even if an LLM is prompt-injected or hallucinates a transaction instruction, the deterministic policy engine runs outside the LLM context and strictly evaluates against mathematical bounds.
2. **No Secret Exposure**: All PayPal credentials, Grok API keys, and Supabase service keys remain exclusively on the backend.
3. **No Phantom State**: TrustGate never creates fake "PAID" receipts. Payment statuses transition strictly through verified state machines.
4. **Transparent Audit Trails**: Every proposal, rule check, and user consent token is logged immutably.

---

## 🌟 Impact and Vision

TrustGate aims to make agentic commerce safer and more accountable by introducing human-controlled financial authorization, transparent purchasing decisions, and tamper-evident transaction records.

> **Our Vision:** Let AI handle the intelligence of shopping, while humans retain control of the money.


