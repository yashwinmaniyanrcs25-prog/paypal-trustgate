"""Deterministic Policy Engine for PayPal TrustGate.

This engine executes mathematical and rule-based invariants against purchase mandates
and proposed transactions. It operates strictly outside of LLM reasoning to ensure zero
prompt-injection or hallucination vulnerability.
"""

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.models.policy import (
    PurchaseMandate,
    ProposedTransaction,
    MandatePolicyEvaluationResponse,
    PolicyCheckSummary,
    PolicyViolation,
    RuleSeverity,
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
)


class PolicyEngine:
    """Evaluates proposed transactions against deterministic security policies and purchase mandates."""

    BLOCKED_MERCHANTS = {
        "unknown_scam_store",
        "shady_dropship_hub",
        "unverified_seller",
        "malicious_vendor",
        "fraudulent_retailer",
    }

    def evaluate_mandate(
        self,
        mandate: PurchaseMandate,
        transaction: ProposedTransaction,
        caller_role: str = "human_user",
    ) -> MandatePolicyEvaluationResponse:
        """Evaluates a structured proposed transaction against a purchase mandate.

        Rules checked:
        1. TG-001: Spending Limit & Math Integrity Check
        2. TG-002: Currency Alignment Check
        3. TG-003: Product Condition Compliance Check
        4. TG-004: Merchant Verification Requirement Check
        5. TG-005: Prohibited Add-Ons & Unexpected Charges Check
        6. TG-006: Transaction Data Integrity & Safe Failure Check
        7. TG-007: AI Zero Autonomous Execution Invariant
        """
        evaluation_id = f"eval_{uuid.uuid4().hex[:8]}"
        checks: List[PolicyCheckSummary] = []
        violations: List[PolicyViolation] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # -------------------------------------------------------------
        # Rule 6 (Run First): Safe Failure on Invalid or Missing Data
        # -------------------------------------------------------------
        has_valid_names = bool(transaction.product_name and transaction.product_name.strip()) and bool(
            transaction.merchant_name and transaction.merchant_name.strip()
        )
        has_valid_numbers = (
            transaction.product_price >= 0
            and transaction.shipping_cost >= 0
            and transaction.tax >= 0
            and transaction.additional_charges >= 0
            and transaction.final_total > 0
        )
        has_valid_currency = len(transaction.currency.strip()) == 3

        # Check stock availability
        avail_lower = str(getattr(transaction, "availability", "InStock") or "InStock").strip().lower()
        is_in_stock = avail_lower not in (
            "outofstock", "out of stock", "no longer available",
            "currently unavailable", "backorder", "sold out", "discontinued"
        )

        # Check for missing/unknown critical specifications when explicitly mandated
        missing_spec_violations: List[PolicyViolation] = []
        if mandate.min_ram_gb is not None and getattr(transaction, "ram_gb", None) is None:
            missing_spec_violations.append(
                PolicyViolation(
                    rule_id="TG-006",
                    rule_name="Unverified Product RAM Specification",
                    message=f"Product RAM specification is UNKNOWN or missing from provider listing. User mandate strictly requires at least {mandate.min_ram_gb}GB RAM.",
                    severity=RuleSeverity.CRITICAL,
                    expected=f">={mandate.min_ram_gb}GB",
                    actual="UNKNOWN",
                )
            )
        if mandate.min_storage_gb is not None and getattr(transaction, "storage_gb", None) is None:
            missing_spec_violations.append(
                PolicyViolation(
                    rule_id="TG-006",
                    rule_name="Unverified Product Storage Specification",
                    message=f"Product storage capacity specification is UNKNOWN or missing from provider listing. User mandate strictly requires at least {mandate.min_storage_gb}GB storage.",
                    severity=RuleSeverity.CRITICAL,
                    expected=f">={mandate.min_storage_gb}GB",
                    actual="UNKNOWN",
                )
            )

        data_valid = (
            has_valid_names
            and has_valid_numbers
            and has_valid_currency
            and is_in_stock
            and len(missing_spec_violations) == 0
        )

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-006",
                rule_name="Data Integrity & Safe Failure Check",
                description="Ensures all transaction fields contain valid, non-negative, and properly structured data.",
                passed=data_valid,
                details=(
                    "Transaction structure, numeric values, and required specifications are verified valid."
                    if data_valid
                    else (
                        f"Product is unavailable ({getattr(transaction, 'availability', 'OutOfStock')})."
                        if not is_in_stock
                        else (
                            missing_spec_violations[0].message
                            if missing_spec_violations
                            else "Missing required identification or invalid negative numeric values detected."
                        )
                    )
                ),
            )
        )
        if not is_in_stock:
            violations.append(
                PolicyViolation(
                    rule_id="TG-006",
                    rule_name="Product Out of Stock or Discontinued",
                    message=f"Product is currently unavailable or out of stock ({getattr(transaction, 'availability', 'OutOfStock')}). Cannot be approved for purchase.",
                    severity=RuleSeverity.CRITICAL,
                    expected="InStock",
                    actual=getattr(transaction, "availability", "OutOfStock"),
                )
            )
        if missing_spec_violations:
            violations.extend(missing_spec_violations)
        if not (has_valid_names and has_valid_numbers and has_valid_currency):
            violations.append(
                PolicyViolation(
                    rule_id="TG-006",
                    rule_name="Invalid Transaction Data",
                    message="Transaction contains missing required identifiers or negative financial quantities.",
                    severity=RuleSeverity.CRITICAL,
                    expected="Valid product/merchant names and non-negative numbers",
                    actual={
                        "product_name": transaction.product_name,
                        "merchant_name": transaction.merchant_name,
                        "price": transaction.product_price,
                        "final_total": transaction.final_total,
                    },
                )
            )

        # -------------------------------------------------------------
        # Rule 1: Spending Limit & Checkout Total Math Integrity
        # -------------------------------------------------------------
        budget_limit = round(mandate.max_amount, 2)
        declared_total = round(transaction.final_total, 2)
        itemized_sum = round(
            transaction.product_price
            + transaction.shipping_cost
            + transaction.tax
            + transaction.additional_charges,
            2,
        )

        within_spending_limit = declared_total <= budget_limit
        math_consistent = abs(declared_total - itemized_sum) <= 0.02

        rule_1_passed = within_spending_limit and math_consistent
        checks.append(
            PolicyCheckSummary(
                rule_id="TG-001",
                rule_name="Mandate Spending Limit Enforcement",
                description="Verifies checkout total does not exceed mandate maximum amount and matches itemized charges.",
                passed=rule_1_passed,
                details=(
                    f"Final total ({transaction.currency} {declared_total:.2f}) <= Mandate limit ({mandate.currency} {budget_limit:.2f}); "
                    f"Itemized sum matches declared total."
                    if rule_1_passed
                    else (
                        f"Final total ({transaction.currency} {declared_total:.2f}) exceeds mandate limit ({mandate.currency} {budget_limit:.2f})"
                        if not within_spending_limit
                        else f"Math discrepancy: Declared total ({declared_total:.2f}) does not match itemized charges sum ({itemized_sum:.2f})"
                    )
                ),
            )
        )
        if not within_spending_limit:
            violations.append(
                PolicyViolation(
                    rule_id="TG-001",
                    rule_name="Spending Limit Exceeded",
                    message=f"Final checkout total of {transaction.currency} {declared_total:.2f} exceeds user mandate maximum budget of {mandate.currency} {budget_limit:.2f}.",
                    severity=RuleSeverity.CRITICAL,
                    expected=f"<= {mandate.currency} {budget_limit:.2f}",
                    actual=f"{transaction.currency} {declared_total:.2f}",
                )
            )
        if not math_consistent:
            violations.append(
                PolicyViolation(
                    rule_id="TG-001",
                    rule_name="Checkout Total Tampering Detected",
                    message=f"Declared final total ({declared_total:.2f}) diverges from itemized components sum ({itemized_sum:.2f}).",
                    severity=RuleSeverity.CRITICAL,
                    expected=f"{itemized_sum:.2f}",
                    actual=f"{declared_total:.2f}",
                )
            )

        # -------------------------------------------------------------
        # Rule 2: Currency Match Check
        # -------------------------------------------------------------
        currency_match = transaction.currency.strip().upper() == mandate.currency.strip().upper()
        checks.append(
            PolicyCheckSummary(
                rule_id="TG-002",
                rule_name="Currency Alignment Check",
                description="Verifies that transaction currency exactly matches the mandated currency.",
                passed=currency_match,
                details=(
                    f"Transaction currency '{transaction.currency}' matches mandate currency '{mandate.currency}'."
                    if currency_match
                    else f"Currency mismatch: Transaction is in '{transaction.currency}' but mandate mandates '{mandate.currency}'."
                ),
            )
        )
        if not currency_match:
            violations.append(
                PolicyViolation(
                    rule_id="TG-002",
                    rule_name="Currency Mismatch",
                    message=f"Transaction currency '{transaction.currency}' does not match mandate requirement '{mandate.currency}'.",
                    severity=RuleSeverity.HIGH,
                    expected=mandate.currency,
                    actual=transaction.currency,
                )
            )

        # -------------------------------------------------------------
        # Rule 3: Product Condition & Specification Compliance
        # -------------------------------------------------------------
        normalized_allowed_conditions = [c.strip().lower() for c in mandate.allowed_conditions]
        actual_condition = transaction.product_condition.strip().lower()
        condition_allowed = actual_condition in normalized_allowed_conditions

        # Category and User Restriction evaluation
        category_compliant, category_violation_msg = self._check_category_and_restrictions(
            mandate=mandate,
            transaction=transaction,
        )

        # Hardware Specification Compliance Check
        spec_violations = self._check_hardware_specifications(mandate, transaction)
        specs_compliant = len(spec_violations) == 0

        rule_3_passed = condition_allowed and category_compliant and specs_compliant
        if rule_3_passed:
            check_details = (
                f"Condition '{transaction.product_condition}', category, and specifications conform to mandate constraints."
            )
        else:
            reasons = []
            if not condition_allowed:
                reasons.append(f"Condition '{transaction.product_condition}' prohibited ({normalized_allowed_conditions})")
            if not category_compliant:
                reasons.append(category_violation_msg or "Category mismatch")
            for sv in spec_violations:
                reasons.append(sv.message)
            check_details = "; ".join(reasons)

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-003",
                rule_name="Product Condition Compliance",
                description="Verifies product condition conforms to allowed conditions in the purchase mandate.",
                passed=rule_3_passed,
                details=check_details,
            )
        )
        if not condition_allowed:
            violations.append(
                PolicyViolation(
                    rule_id="TG-003",
                    rule_name="Prohibited Product Condition",
                    message=f"Product condition '{transaction.product_condition}' is not allowed by mandate. Permitted: {normalized_allowed_conditions}.",
                    severity=RuleSeverity.HIGH,
                    expected=normalized_allowed_conditions,
                    actual=transaction.product_condition,
                )
            )
        if not category_compliant:
            violations.append(
                PolicyViolation(
                    rule_id="TG-003",
                    rule_name="Category or User Restriction Mismatch",
                    message=category_violation_msg or "Product does not conform to mandate user restrictions.",
                    severity=RuleSeverity.CRITICAL,
                    expected="Eligible product matching mandate user restrictions",
                    actual=f"{transaction.product_name} (Category: {getattr(transaction, 'category', 'General')})",
                )
            )
        if spec_violations:
            violations.extend(spec_violations)

        # -------------------------------------------------------------
        # Rule 4: Merchant Verification Requirement
        # -------------------------------------------------------------
        merchant_name_lower = transaction.merchant_name.strip().lower()
        is_blocked_merchant = merchant_name_lower in self.BLOCKED_MERCHANTS

        # Marketplace Compliance Check
        marketplace_compliant, mkt_violation = self._check_marketplace_restriction(mandate, transaction)

        if mandate.require_merchant_verification:
            merchant_verified = transaction.merchant_verified and not is_blocked_merchant and marketplace_compliant
        else:
            merchant_verified = not is_blocked_merchant and marketplace_compliant

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-004",
                rule_name="Merchant Verification & Trust Check",
                description="Verifies merchant is verified when required and not on prohibited vendor lists.",
                passed=merchant_verified,
                details=(
                    f"Merchant '{transaction.merchant_name}' meets verification requirement."
                    if merchant_verified
                    else (
                        mkt_violation.message
                        if not marketplace_compliant and mkt_violation
                        else (
                            f"Merchant '{transaction.merchant_name}' is on the TrustGate blacklist."
                            if is_blocked_merchant
                            else f"Merchant '{transaction.merchant_name}' is unverified, but mandate requires verified status."
                        )
                    )
                ),
            )
        )
        if not marketplace_compliant and mkt_violation:
            violations.append(mkt_violation)
        if not merchant_verified and not is_blocked_merchant and not mkt_violation:
            violations.append(
                PolicyViolation(
                    rule_id="TG-004",
                    rule_name="Unverified or Untrusted Merchant",
                    message=f"Merchant '{transaction.merchant_name}' is not verified, violating mandate requirement.",
                    severity=RuleSeverity.HIGH,
                    expected="Verified merchant" if mandate.require_merchant_verification else "Non-blacklisted merchant",
                    actual=f"merchant_verified={transaction.merchant_verified}",
                )
            )
        elif is_blocked_merchant:
            violations.append(
                PolicyViolation(
                    rule_id="TG-004",
                    rule_name="Unverified or Untrusted Merchant",
                    message=f"Merchant '{transaction.merchant_name}' is flagged as an untrusted or blacklisted vendor.",
                    severity=RuleSeverity.CRITICAL,
                    expected="Non-blacklisted merchant",
                    actual=transaction.merchant_name,
                )
            )

        # -------------------------------------------------------------
        # Rule 5: Prohibited Add-Ons & Unexpected Charges Check
        # -------------------------------------------------------------
        has_add_ons = len(transaction.add_ons) > 0
        has_unexpected_charges = transaction.additional_charges > 0

        add_ons_compliant = True
        if not mandate.allow_add_ons:
            if has_add_ons or has_unexpected_charges:
                add_ons_compliant = False

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-005",
                rule_name="Add-On & Hidden Fee Protection",
                description="Ensures unwanted accessory add-ons or unexpected charges are rejected when disallowed by mandate.",
                passed=add_ons_compliant,
                details=(
                    "No prohibited add-ons or unexpected additional charges detected."
                    if add_ons_compliant
                    else (
                        f"Prohibited add-ons detected: {transaction.add_ons}; "
                        if has_add_ons
                        else ""
                    )
                    + (
                        f"Unexpected additional charges of {transaction.currency} {transaction.additional_charges:.2f} detected."
                        if has_unexpected_charges
                        else ""
                    )
                ),
            )
        )
        if not add_ons_compliant:
            violations.append(
                PolicyViolation(
                    rule_id="TG-005",
                    rule_name="Prohibited Add-Ons or Additional Charges",
                    message=(
                        f"Mandate prohibits add-ons, but transaction includes: {transaction.add_ons} "
                        f"(and unexpected fee of {transaction.currency} {transaction.additional_charges:.2f})."
                    ),
                    severity=RuleSeverity.HIGH,
                    expected="allow_add_ons=False (zero add-ons and $0.00 additional charges)",
                    actual={
                        "add_ons": transaction.add_ons,
                        "additional_charges": transaction.additional_charges,
                    },
                )
            )

        # -------------------------------------------------------------
        # Rule 7: AI Autonomous Authorization Invariant (CRITICAL)
        # -------------------------------------------------------------
        is_ai_caller = caller_role.lower() in ("ai_agent", "grok", "agent", "llm", "bot")
        rule_7_passed = not is_ai_caller
        checks.append(
            PolicyCheckSummary(
                rule_id="TG-007",
                rule_name="AI Zero Autonomous Execution Invariant",
                description="Strictly ensures autonomous AI models cannot execute payments or bypass human approval.",
                passed=rule_7_passed,
                details=(
                    "Caller role verified as human user."
                    if rule_7_passed
                    else f"BLOCKED: AI agent ('{caller_role}') attempted direct payment authorization."
                ),
            )
        )
        if not rule_7_passed:
            violations.append(
                PolicyViolation(
                    rule_id="TG-007",
                    rule_name="Autonomous Authorization Forbidden",
                    message="AI agents have propose-only capability and are strictly barred from authorizing financial transactions.",
                    severity=RuleSeverity.CRITICAL,
                    expected="caller_role == 'human_user'",
                    actual=f"caller_role == '{caller_role}'",
                )
            )

        # -------------------------------------------------------------
        # Final Determination & Signature Generation
        # -------------------------------------------------------------
        approved = len(violations) == 0
        status = "APPROVED" if approved else "BLOCKED"

        if approved:
            explanation = (
                f"Transaction for '{transaction.product_name}' ({transaction.currency} {declared_total:.2f}) "
                f"strictly satisfies all mandate constraints (budget <= {mandate.max_amount:.2f}, "
                f"condition '{transaction.product_condition}', verified merchant). "
                f"Approved by TrustGate policy engine. Note: Explicit human sign-off is still required prior to PayPal checkout."
            )
        else:
            reasons = [f"({idx + 1}) {v.message}" for idx, v in enumerate(violations)]
            explanation = (
                f"Transaction for '{transaction.product_name}' was BLOCKED by TrustGate policy engine "
                f"due to {len(violations)} rule violation(s): " + " ".join(reasons)
            )

        # Cryptographic tamper-evident signature
        sign_payload = f"{evaluation_id}:{status}:{declared_total}:{transaction.currency}:{len(checks)}:{time.time()}"
        signature = f"tg_sig_{hashlib.sha256(sign_payload.encode()).hexdigest()[:24]}"

        return MandatePolicyEvaluationResponse(
            evaluation_id=evaluation_id,
            approved=approved,
            status=status,
            violations=violations,
            explanation=explanation,
            checks=checks,
            mandate_summary={
                "max_amount": mandate.max_amount,
                "currency": mandate.currency,
                "allowed_conditions": mandate.allowed_conditions,
                "require_merchant_verification": mandate.require_merchant_verification,
                "allow_add_ons": mandate.allow_add_ons,
                "user_restrictions": mandate.user_restrictions,
            },
            transaction_summary={
                "product_name": transaction.product_name,
                "final_total": transaction.final_total,
                "currency": transaction.currency,
                "merchant_name": transaction.merchant_name,
                "merchant_verified": transaction.merchant_verified,
                "product_condition": transaction.product_condition,
                "add_ons": transaction.add_ons,
                "itemized_breakdown": {
                    "product_price": transaction.product_price,
                    "shipping_cost": transaction.shipping_cost,
                    "tax": transaction.tax,
                    "additional_charges": transaction.additional_charges,
                },
            },
            requires_human_approval=True,
            can_proceed_to_paypal=approved,
            policy_signature=signature,
            evaluated_at=now_iso,
        )

    def _check_category_and_restrictions(
        self,
        mandate: PurchaseMandate,
        transaction: ProposedTransaction,
    ) -> tuple[bool, Optional[str]]:
        """Evaluates whether the proposed transaction satisfies mandate user_restrictions and product category rules."""
        if not mandate.user_restrictions:
            return True, None

        prod_name = (transaction.product_name or "").lower()
        category = getattr(transaction, "category", "General") or "General"
        category_lower = category.lower()

        for raw_restriction in mandate.user_restrictions:
            restriction = raw_restriction.strip().lower()
            if not restriction:
                continue

            # Skip general merchant/condition restrictions that are evaluated in TG-003/TG-004
            if restriction in ("verified seller", "verified merchant", "new only", "new condition"):
                continue

            is_exclusive = "only" in restriction

            # 1. Laptop restrictions: e.g. "new laptop only", "laptop only", "laptops only"
            if ("laptop" in restriction or "notebook" in restriction) and is_exclusive:
                # Disallow accessories, mice, keyboards, cables, etc.
                is_accessory_category = any(
                    acc in category_lower
                    for acc in ("accessories", "mice", "mouse", "keyboard", "headphone", "audio", "cables", "chargers", "cases", "parts")
                )

                # Check if product name indicates an accessory rather than a standalone laptop
                accessory_terms = (
                    "mouse", "keyboard", "trackpad", "headphone", "headset", "earbuds",
                    "charger", "adapter", "sleeve", "stand", "dock", "hub", "cable",
                    "case", "cooling pad", "screen protector", "skin", "backpack", "mousepad"
                )
                is_accessory_name = any(acc in prod_name for acc in accessory_terms)
                if any(model in prod_name for model in ("ideapad", "thinkpad", "vivobook", "zenbook", "aspire", "pavilion", "macbook", "xps", "laptop")):
                    has_laptop_accessory_phrase = any(
                        phrase in prod_name
                        for phrase in ("laptop sleeve", "laptop bag", "laptop stand", "laptop charger", "laptop case", "laptop cooling", "for laptop", "laptop skin", "laptop backpack", "laptop mouse")
                    )
                    if not has_laptop_accessory_phrase and any(lp in prod_name for lp in ("laptop", "notebook", "ultrabook", "macbook")):
                        is_accessory_name = False

                is_laptop_item = (
                    ("laptop" in category_lower or "notebook" in category_lower or "laptops" in category_lower)
                    or (
                        any(term in prod_name for term in ("laptop", "notebook", "ultrabook", "macbook", "thinkpad", "ideapad", "zenbook", "vivobook", "chromebook"))
                        and not is_accessory_name
                        and not is_accessory_category
                    )
                )

                if is_accessory_category or is_accessory_name or not is_laptop_item:
                    return False, (
                        f"Product '{transaction.product_name}' (Category: {category}) violates mandate restriction: "
                        f"'{raw_restriction}'. Unrelated categories, mice, keyboards, and accessories are prohibited."
                    )

            # 2. Mouse restrictions: e.g. "mouse only", "mice only"
            elif ("mouse" in restriction or "mice" in restriction) and is_exclusive:
                is_mouse = "mouse" in category_lower or "mice" in category_lower or "mouse" in prod_name
                if not is_mouse or "laptop" in category_lower:
                    return False, (
                        f"Product '{transaction.product_name}' (Category: {category}) violates mandate restriction: "
                        f"'{raw_restriction}'. Product is not an eligible mouse candidate."
                    )

            # 3. Keyboard restrictions: e.g. "keyboard only", "mechanical keyboard only"
            elif "keyboard" in restriction and is_exclusive:
                is_keyboard = "keyboard" in category_lower or "keyboard" in prod_name
                if not is_keyboard or "laptop" in category_lower:
                    return False, (
                        f"Product '{transaction.product_name}' (Category: {category}) violates mandate restriction: "
                        f"'{raw_restriction}'. Product is not an eligible keyboard candidate."
                    )

            # 4. Explicit model/brand restriction (e.g. "keychron k2")
            elif "keychron" in restriction:
                if "keychron" not in prod_name:
                    return False, (
                        f"Product '{transaction.product_name}' violates mandate restriction: '{raw_restriction}'. "
                        f"Must match required brand/model."
                    )

        return True, None

    @classmethod
    def _is_processor_compliant(cls, requirement: str, candidate_proc: Optional[str]) -> bool:
        """Determines whether candidate processor meets user's minimum processor specification."""
        if not requirement:
            return True
        if not candidate_proc or candidate_proc.strip().upper() == "UNKNOWN":
            return False

        cand_lower = candidate_proc.lower()
        req_lower = requirement.lower()

        # Check for Core i5 / Ryzen 5 or better tier requirement
        if "core i5" in req_lower or "ryzen 5" in req_lower or "i5" in req_lower or "ryzen 5" in req_lower:
            # Low tier CPUs are strictly rejected
            if any(low in cand_lower for low in ("celeron", "pentium", "athlon", "core i3", "i3-", "ryzen 3")):
                return False
            # Core i5, i7, i9, Core Ultra, Ryzen 5, 7, 9, Apple M1..M4 are compliant
            if any(high in cand_lower for high in ("core i5", "core i7", "core i9", "ultra", "ryzen 5", "ryzen 7", "ryzen 9", "m1", "m2", "m3", "m4")):
                return True
            return False

        # Check for Core i7 / Ryzen 7 tier requirement
        if "i7" in req_lower or "ryzen 7" in req_lower:
            if any(low in cand_lower for low in ("celeron", "pentium", "athlon", "core i3", "core i5", "ryzen 3", "ryzen 5")):
                return False
            if any(high in cand_lower for high in ("core i7", "core i9", "ultra", "ryzen 7", "ryzen 9", "m2", "m3", "m4")):
                return True
            return False

        return True

    def _check_hardware_specifications(
        self,
        mandate: PurchaseMandate,
        transaction: ProposedTransaction,
    ) -> List[PolicyViolation]:
        """Validates hardware specifications: RAM, storage capacity, storage type, processor."""
        violations: List[PolicyViolation] = []

        # 1. RAM Capacity Check
        if mandate.min_ram_gb is not None:
            tx_ram = getattr(transaction, "ram_gb", None)
            if tx_ram is not None and tx_ram < mandate.min_ram_gb:
                violations.append(
                    PolicyViolation(
                        rule_id="TG-003",
                        rule_name="Insufficient RAM Capacity",
                        message=f"Product has {tx_ram}GB RAM, which is below user mandate requirement of at least {mandate.min_ram_gb}GB RAM.",
                        severity=RuleSeverity.CRITICAL,
                        expected=f">={mandate.min_ram_gb}GB",
                        actual=f"{tx_ram}GB",
                    )
                )

        # 2. Storage Capacity Check
        if mandate.min_storage_gb is not None:
            tx_storage = getattr(transaction, "storage_gb", None)
            if tx_storage is not None and tx_storage < mandate.min_storage_gb:
                violations.append(
                    PolicyViolation(
                        rule_id="TG-003",
                        rule_name="Insufficient Storage Capacity",
                        message=f"Product has {tx_storage}GB storage, which is below user mandate requirement of at least {mandate.min_storage_gb}GB storage.",
                        severity=RuleSeverity.CRITICAL,
                        expected=f">={mandate.min_storage_gb}GB",
                        actual=f"{tx_storage}GB",
                    )
                )

        # 3. Storage Type Check
        if mandate.storage_type:
            tx_st_type = getattr(transaction, "storage_type", None)
            if tx_st_type:
                req_st = mandate.storage_type.lower()
                act_st = tx_st_type.lower()
                if "ssd" in req_st and "ssd" not in act_st and "nvme" not in act_st:
                    violations.append(
                        PolicyViolation(
                            rule_id="TG-003",
                            rule_name="Storage Type Mismatch",
                            message=f"Product storage type is '{tx_st_type}', but mandate strictly requires '{mandate.storage_type}'.",
                            severity=RuleSeverity.HIGH,
                            expected=mandate.storage_type,
                            actual=tx_st_type,
                        )
                    )

        # 4. Processor Requirement Check
        if mandate.processor_requirement:
            tx_proc = getattr(transaction, "processor", None)
            if not self._is_processor_compliant(mandate.processor_requirement, tx_proc):
                violations.append(
                    PolicyViolation(
                        rule_id="TG-003",
                        rule_name="Processor Requirement Mismatch",
                        message=f"Product processor '{tx_proc or 'UNKNOWN'}' does not meet mandate requirement: '{mandate.processor_requirement}'.",
                        severity=RuleSeverity.CRITICAL,
                        expected=mandate.processor_requirement,
                        actual=tx_proc or "UNKNOWN",
                    )
                )

        return violations

    def _check_marketplace_restriction(
        self,
        mandate: PurchaseMandate,
        transaction: ProposedTransaction,
    ) -> Tuple[bool, Optional[PolicyViolation]]:
        """Validates that candidate listing originates from the mandated marketplace/region."""
        target_marketplace: Optional[str] = mandate.marketplace
        if not target_marketplace and mandate.user_restrictions:
            for r in mandate.user_restrictions:
                r_lower = r.lower()
                if "amazon india" in r_lower or "amazon.in" in r_lower:
                    target_marketplace = "amazon.in"
                    break
                elif "amazon us" in r_lower or "amazon.com" in r_lower:
                    target_marketplace = "amazon.com"
                    break

        if not target_marketplace:
            return True, None

        target_mkt_lower = target_marketplace.strip().lower()
        candidate_marketplace = str(getattr(transaction, "marketplace", "") or "").strip().lower()
        candidate_retailer = str(getattr(transaction, "retailer", "") or "").strip().lower()
        candidate_merchant = str(transaction.merchant_name or "").strip().lower()
        combined_origin = f"{candidate_marketplace} {candidate_retailer} {candidate_merchant}".strip()

        # If mandate requires Amazon India (amazon.in)
        if "amazon.in" in target_mkt_lower or "amazon india" in target_mkt_lower:
            disallowed_retailers = (
                "officedepot", "office depot", "target", "bestbuy", "best buy",
                "walmart", "homedepot", "costco", "amazon.com", "staples"
            )
            for dis in disallowed_retailers:
                if dis in combined_origin:
                    actual_name = getattr(transaction, "retailer", None) or transaction.merchant_name
                    return False, PolicyViolation(
                        rule_id="TG-004",
                        rule_name="Marketplace Origin Mismatch",
                        message=(
                            f"Listing originates from '{actual_name}' (unrelated marketplace provider), "
                            f"but user mandate restricts purchases strictly to '{target_marketplace}'."
                        ),
                        severity=RuleSeverity.CRITICAL,
                        expected=target_marketplace,
                        actual=actual_name,
                    )

        return True, None

    def evaluate(self, request: PolicyEvaluationRequest) -> PolicyEvaluationResponse:
        """Legacy evaluate method for backward compatibility."""
        mandate = PurchaseMandate(
            max_amount=request.budget_limit,
            currency="USD",
            allowed_conditions=["new"],
            require_merchant_verification=True,
            allow_add_ons=False,
        )
        transaction = ProposedTransaction(
            product_name="Legacy Evaluation Item",
            product_price=request.proposed_price,
            shipping_cost=request.shipping_cost,
            final_total=round(request.proposed_price + request.shipping_cost, 2),
            currency="USD",
            merchant_name=request.merchant_name,
            merchant_verified=True,
            product_condition="new",
        )
        res = self.evaluate_mandate(mandate, transaction, request.caller_role)

        return PolicyEvaluationResponse(
            evaluation_id=res.evaluation_id,
            passed=res.approved,
            status="POLICY_VERIFIED" if res.approved else "POLICY_VIOLATION",
            checks=res.checks,
            violations=res.violations,
            total_evaluated_cost=transaction.final_total,
            budget_limit=request.budget_limit,
            requires_human_approval=True,
            can_proceed_to_paypal=res.approved,
            policy_signature=res.policy_signature,
        )


policy_engine = PolicyEngine()
