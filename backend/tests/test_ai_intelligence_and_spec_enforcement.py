"""Comprehensive Automated Test Suite for AI Intelligence, Product Discovery,
Hardware Specification Enforcement, Marketplace Security, and Payment Integrity.

Covers Scenarios A through L as mandated by the PayPal TrustGate Upgrade Specification:
- Scenario A: Compliant Laptop Purchase (16GB RAM, 512GB SSD, Intel Core i5, new, amazon.in, verified seller, <= 60000 INR)
- Scenario B: Insufficient Specifications (8GB RAM, 256GB SSD blocked under TG-003)
- Scenario C: Missing / Ambiguous Specifications (Fail-closed under TG-006)
- Scenario D: Wrong Marketplace / Origin Leak (Office Depot listing blocked under TG-004)
- Scenario E: Currency Mismatch & Verifiable Decimal Arithmetic (TG-002 & CurrencyService)
- Scenario F: Unavailable Product / Out-of-Stock (Blocked under TG-006)
- Scenario G: Wireless Mouse Under Laptop Mandate (Blocked under TG-003, 0 approved)
- Scenario H: Over-Budget Laptop (Blocked under TG-001)
- Scenario I: Marketplace Switching & Currency Isolation (amazon.in vs amazon.com)
- Scenario J: Search Query & State Synchronization (Input matches query, async-safe)
- Scenario K: Specification Normalization Layer (HP, Lenovo, Dell, Apple, ASUS extraction)
- Scenario L: End-to-End Security Pipeline (Zero AI Authority, Human Approval Gate, PayPal Sandbox)
"""

import uuid
import pytest
from decimal import Decimal

from app.core.security import PaymentExecutionBlockedError
from app.db.database import (
    init_db,
    record_human_approval,
    get_human_approval,
    verify_audit_integrity,
)
from app.models.lifecycle import TransactionState
from app.models.policy import PurchaseMandate, ProposedTransaction
from app.models.proposal import DiscoveredProduct
from app.services.policy_engine import policy_engine
from app.services.product_normalizer import product_normalizer
from app.services.currency_service import currency_service
from app.services.product_discovery_service import product_discovery_service
from app.services.intent_interpreter_service import intent_interpreter_service
from app.services.proposal_store import proposal_store
from app.services.paypal_service import paypal_service


# =============================================================================
# SCENARIO A: Compliant Laptop Purchase
# =============================================================================
class TestScenarioACompliantLaptop:
    """Scenario A: Compliant Laptop Purchase under Amazon India INR mandate."""

    def test_compliant_laptop_passes_all_invariants(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            user_restrictions=["new laptop only"],
            category="laptop",
            min_ram_gb=16,
            min_storage_gb=512,
            storage_type="SSD",
            processor_requirement="Intel Core i5 or better",
            marketplace="amazon.in",
            in_stock_required=True,
        )

        transaction = ProposedTransaction(
            product_name="Lenovo IdeaPad Slim 3 15.6-inch Laptop (Intel Core i5-1235U, 16GB RAM, 512GB SSD)",
            product_description="Brand new Lenovo laptop sold by official store.",
            category="laptop",
            product_price=54990.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=54990.0,
            currency="INR",
            merchant_name="Official Lenovo Brand Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
            brand="Lenovo",
            model="IdeaPad Slim 3",
            ram_gb=16,
            storage_gb=512,
            storage_type="SSD",
            processor="Intel Core i5",
            availability="InStock",
            marketplace="amazon.in",
            retailer="amazon.in",
            spec_verification_status="VERIFIED",
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is True
        assert result.status == "APPROVED"
        assert len(result.violations) == 0
        assert result.requires_human_approval is True
        assert result.can_proceed_to_paypal is True
        assert result.policy_signature.startswith("tg_sig_")


# =============================================================================
# SCENARIO B: Insufficient Specifications
# =============================================================================
class TestScenarioBInsufficientSpecifications:
    """Scenario B: 8GB RAM and 256GB SSD blocked when 16GB RAM / 512GB SSD is required."""

    def test_under_spec_laptop_blocked_under_tg_003(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            category="laptop",
            min_ram_gb=16,
            min_storage_gb=512,
            storage_type="SSD",
            processor_requirement="Intel Core i5",
        )

        transaction = ProposedTransaction(
            product_name="HP 15s 15.6-inch Laptop (Intel Core i3, 8GB RAM, 256GB SSD)",
            category="laptop",
            product_price=38990.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=38990.0,
            currency="INR",
            merchant_name="Official HP Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
            ram_gb=8,
            storage_gb=256,
            storage_type="SSD",
            processor="Intel Core i3",
            availability="InStock",
            spec_verification_status="VERIFIED",
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        assert result.status == "BLOCKED"
        violation_rules = [v.rule_id for v in result.violations]
        assert "TG-003" in violation_rules

        # Check explicit messages for RAM, Storage, and Processor
        messages = " ".join(v.message for v in result.violations)
        assert "8GB RAM" in messages or "RAM" in messages
        assert "256GB" in messages or "Storage" in messages


# =============================================================================
# SCENARIO C: Missing / Ambiguous Specifications
# =============================================================================
class TestScenarioCMissingSpecifications:
    """Scenario C: Laptop with missing/unknown specs fails closed under TG-006."""

    def test_missing_mandatory_specs_fails_closed(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            category="laptop",
            min_ram_gb=16,
            min_storage_gb=512,
        )

        transaction = ProposedTransaction(
            product_name="Generic Portable Computing Device",
            category="laptop",
            product_price=42000.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=42000.0,
            currency="INR",
            merchant_name="Electronics Wholesaler",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
            ram_gb=None,  # Missing
            storage_gb=None,  # Missing
            spec_verification_status="UNKNOWN",
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        violation_rules = [v.rule_id for v in result.violations]
        assert "TG-006" in violation_rules
        assert any("missing" in v.message.lower() or "unverified" in v.message.lower() for v in result.violations)


# =============================================================================
# SCENARIO D: Wrong Marketplace / Origin Leak
# =============================================================================
class TestScenarioDWrongMarketplace:
    """Scenario D: Office Depot listing appearing under Amazon India mandate is blocked."""

    def test_office_depot_blocked_under_amazon_india_mandate(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            marketplace="amazon.in",
            user_restrictions=["amazon.in only"],
        )

        transaction = ProposedTransaction(
            product_name="HP 15-dy2027od Laptop",
            product_description="Discovered from Office Depot universal graph listing.",
            category="laptop",
            product_price=27000.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=27000.0,
            currency="INR",
            merchant_name="officedepot.com",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
            marketplace="channel3",
            retailer="officedepot.com",
            availability="OutOfStock",
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        tg_004_violations = [v for v in result.violations if v.rule_id == "TG-004"]
        assert len(tg_004_violations) > 0
        assert "Marketplace Origin Mismatch" in tg_004_violations[0].rule_name


# =============================================================================
# SCENARIO E: Currency Mismatch & Verifiable Decimal Arithmetic
# =============================================================================
class TestScenarioECurrencyMismatchAndArithmetic:
    """Scenario E: Currency mismatch enforcement and verifiable Decimal arithmetic."""

    def test_unconverted_currency_blocked_under_tg_002(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
        )

        transaction = ProposedTransaction(
            product_name="HP 15-dy2027od Laptop",
            product_price=325.99,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=325.99,
            currency="USD",  # Mismatched currency
            merchant_name="Official Merchant",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        assert any(v.rule_id == "TG-002" for v in result.violations)

    def test_decimal_currency_conversion_with_audit_metadata(self):
        res = currency_service.convert_with_metadata(Decimal("100.00"), "USD", "INR")

        assert res.converted_amount == Decimal("8300.00")
        assert res.original_currency == "USD"
        assert res.target_currency == "INR"
        assert res.exchange_rate == Decimal("83.00")
        assert res.is_verified is True
        assert "Benchmark" in res.rate_source
        assert "1 USD = 83.0000 INR" in res.formula


# =============================================================================
# SCENARIO F: Unavailable Product / Out-of-Stock
# =============================================================================
class TestScenarioFUnavailableProduct:
    """Scenario F: Out-of-stock product is blocked when in_stock_required=True."""

    def test_out_of_stock_product_blocked_under_tg_006(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            in_stock_required=True,
        )

        transaction = ProposedTransaction(
            product_name="Lenovo ThinkPad E14 (Out of Stock)",
            category="laptop",
            product_price=52000.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=52000.0,
            currency="INR",
            merchant_name="Official Lenovo Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
            availability="OutOfStock",
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        assert any(v.rule_id == "TG-006" for v in result.violations)
        assert any("out of stock" in v.message.lower() for v in result.violations)


# =============================================================================
# SCENARIO G: Wireless Mouse Under Laptop Mandate
# =============================================================================
class TestScenarioGWirelessMouseUnderLaptopMandate:
    """Scenario G: Non-laptop products rejected under laptop-only mandate."""

    def test_wireless_mouse_blocked_under_laptop_mandate(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            category="laptop",
            user_restrictions=["new laptop only"],
        )

        transaction = ProposedTransaction(
            product_name="Logitech MX Master 3S Wireless Performance Mouse",
            category="Computer Accessories / Mice",
            product_price=8995.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=8995.0,
            currency="INR",
            merchant_name="Logitech Official Store",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        assert any(v.rule_id == "TG-003" for v in result.violations)


# =============================================================================
# SCENARIO H: Over-Budget Laptop
# =============================================================================
class TestScenarioHOverBudgetLaptop:
    """Scenario H: Product exceeding budget limit is blocked under TG-001."""

    def test_over_budget_laptop_blocked_under_tg_001(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
        )

        transaction = ProposedTransaction(
            product_name="Dell XPS 15 OLED Laptop",
            category="laptop",
            product_price=85000.0,
            shipping_cost=0.0,
            tax=0.0,
            additional_charges=0.0,
            final_total=85000.0,
            currency="INR",
            merchant_name="Dell Official Direct",
            merchant_verified=True,
            product_condition="new",
            add_ons=[],
        )

        result = policy_engine.evaluate_mandate(mandate, transaction)

        assert result.approved is False
        assert any(v.rule_id == "TG-001" for v in result.violations)
        assert any("exceeds" in v.message.lower() for v in result.violations)


# =============================================================================
# SCENARIO I: Marketplace Switching & Currency Isolation
# =============================================================================
class TestScenarioIMarketplaceSwitching:
    """Scenario I: Switching between amazon.in (INR) and amazon.com (USD)."""

    @pytest.mark.asyncio
    async def test_marketplace_switching_currency_and_catalog(self):
        mandate_inr = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            marketplace="amazon.in",
        )
        res_inr = await product_discovery_service.search_candidates(
            mandate=mandate_inr,
            query="laptop",
            marketplace_id="demo",
            region="demo_in",
        )
        assert res_inr.total_count > 0
        assert res_inr.candidates[0].currency == "INR"

        mandate_usd = PurchaseMandate(
            max_amount=720.0,
            currency="USD",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
            marketplace="amazon.com",
        )
        res_usd = await product_discovery_service.search_candidates(
            mandate=mandate_usd,
            query="laptop",
            marketplace_id="demo",
            region="demo_us",
        )
        assert res_usd.total_count > 0
        assert res_usd.candidates[0].currency == "USD"


# =============================================================================
# SCENARIO J: Search Query & State Synchronization
# =============================================================================
class TestScenarioJSearchQuerySync:
    """Scenario J: Query in response strictly matches the user's query."""

    @pytest.mark.asyncio
    async def test_search_query_reflection(self):
        mandate = PurchaseMandate(
            max_amount=60000.0,
            currency="INR",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
        )

        for q in ["laptop", "wireless mouse", "mechanical keyboard"]:
            res = await product_discovery_service.search_candidates(
                mandate=mandate,
                query=q,
                marketplace_id="demo",
                region="demo_in",
            )
            assert res.query == q


# =============================================================================
# SCENARIO K: Specification Normalization Layer
# =============================================================================
class TestScenarioKSpecificationNormalizer:
    """Scenario K: Comprehensive hardware specification normalization."""

    def test_extract_specs_hp_laptop(self):
        title = "HP 15-dy2027od Laptop, 15.6\" Screen, Intel® Core™ i5, 8GB Memory, 256GB Solid State Drive"
        specs = product_normalizer.normalize_specifications(title=title, category="laptop")

        assert specs["brand"] == "HP"
        assert specs["model"] == "15-dy2027od"
        assert specs["ram_gb"] == 8
        assert specs["storage_gb"] == 256
        assert specs["storage_type"] == "SSD"
        assert specs["processor"] == "Intel Core i5"
        assert specs["screen_size"] == "15.6 inch"

    def test_extract_specs_lenovo_ideapad(self):
        title = "Lenovo IdeaPad Slim 3 15.6-inch Laptop (Intel Core i5-1235U, 16GB RAM, 512GB SSD, Windows 11)"
        specs = product_normalizer.normalize_specifications(title=title, category="laptop")

        assert specs["brand"] == "Lenovo"
        assert specs["ram_gb"] == 16
        assert specs["storage_gb"] == 512
        assert specs["storage_type"] == "SSD"
        assert "Intel Core i5" in specs["processor"]
        assert specs["spec_verification_status"] == "VERIFIED"

    def test_extract_specs_apple_macbook(self):
        title = "Apple MacBook Air 13-inch M2 chip, 8GB Unified Memory, 256GB SSD Storage"
        specs = product_normalizer.normalize_specifications(title=title, category="laptop")

        assert specs["brand"] == "Apple"
        assert specs["ram_gb"] == 8
        assert specs["storage_gb"] == 256
        assert "Apple M2" in specs["processor"]

    def test_extract_availability_cues(self):
        assert product_normalizer.extract_availability(raw_avail="InStock") == "InStock"
        assert product_normalizer.extract_availability(raw_avail="OutOfStock") == "OutOfStock"
        assert product_normalizer.extract_availability(text="Currently unavailable online") == "OutOfStock"
        assert product_normalizer.extract_availability(text="Ships in 24 hours - in stock") == "InStock"


# =============================================================================
# SCENARIO L: End-to-End Security Pipeline
# =============================================================================
class TestScenarioLEndToEndSecurityPipeline:
    """Scenario L: Full security pipeline with mandatory human authorization."""

    @pytest.mark.asyncio
    async def test_end_to_end_security_lifecycle(self):
        # 1. AI Intent Interpretation
        prompt = (
            "Find me a brand new HP or Lenovo laptop under ₹60,000 on Amazon India "
            "with at least 16GB RAM, 512GB SSD, Intel Core i5 or better, sold by a verified seller, in stock only. "
            "No refurbished, no accessories."
        )
        interpretation = await intent_interpreter_service.interpret_intent(prompt)

        assert interpretation.success is True
        mandate = interpretation.mandate
        assert mandate is not None
        assert mandate.max_amount == 60000.0
        assert mandate.currency == "INR"
        assert mandate.min_ram_gb == 16
        assert mandate.min_storage_gb == 512

        # 2. Candidate Discovery & Policy Evaluation
        candidate_prod = DiscoveredProduct(
            product_id="test_lenovo_compliant_001",
            name="Lenovo IdeaPad Slim 3 15.6-inch Laptop (Intel Core i5, 16GB RAM, 512GB SSD)",
            description="Brand new Lenovo laptop matching all user requirements.",
            category="laptop",
            price=54990.0,
            currency="INR",
            condition="new",
            merchant_name="Official Lenovo Brand Store",
            merchant_verified=True,
            verification_status="VERIFIED",
            data_source="amazon_api",
            is_demo_data=False,
            demo_notice="",
            marketplace_id="amazon",
            region="amazon.in",
            availability="InStock",
            brand="Lenovo",
            model="IdeaPad Slim 3",
            ram_gb=16,
            storage_gb=512,
            storage_type="SSD",
            processor="Intel Core i5",
            spec_verification_status="VERIFIED",
        )

        evaluation = product_discovery_service._evaluate_candidate(candidate_prod, mandate)
        assert evaluation is not None
        assert evaluation.approved is True

        # 3. Stage Proposal in SQLite (STAGED state)
        tx_id = f"stg_{uuid.uuid4().hex[:10]}"
        staged_record = proposal_store.save_staged_proposal(
            staged_proposal_id=tx_id,
            mandate=mandate,
            candidate=candidate_prod,
            policy_evaluation=evaluation.policy_result,
            user_id="operator_alice",
        )
        assert staged_record.status == TransactionState.STAGED.value
        assert staged_record.staged_proposal_id == tx_id

        # 4. Invariant: Unapproved Proposal CANNOT Execute Payment
        # PayPal Sandbox order creation is strictly BLOCKED prior to explicit human sign-off
        with pytest.raises(PaymentExecutionBlockedError) as block_err:
            await paypal_service.create_sandbox_order(
                staged_proposal_id=tx_id,
                user_id="operator_alice",
                caller_role="human_user",
            )
        assert "Explicit human approval is required" in str(block_err.value)

        # 5. Explicit Human Approval
        approval_res = record_human_approval(
            transaction_id=tx_id,
            user_id="operator_alice",
            policy_signature=evaluation.policy_result.policy_signature,
            approved_amount=candidate_prod.price,
            currency=candidate_prod.currency,
            action="AUTHORIZE_PAYPAL_SANDBOX_CHECKOUT",
            actor_role="human_user",
            consent_token="tok_cons_operator_alice",
        )
        assert approval_res["current_state"] == TransactionState.HUMAN_APPROVED

        # 6. Proposal is now genuinely approved in SQLite
        auth_rec = get_human_approval(tx_id)
        assert auth_rec is not None
        assert auth_rec["transaction_id"] == tx_id
        assert auth_rec["actor_role"] == "human_user"

        retrieved = proposal_store.get_staged_proposal(tx_id)
        assert retrieved is not None
        assert retrieved.status == TransactionState.HUMAN_APPROVED.value
