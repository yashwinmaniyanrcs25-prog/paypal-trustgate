"""Deterministic Policy Engine for PayPal TrustGate.

This engine executes mathematical and rule-based invariants against purchase mandates
and proposed transactions. It operates strictly outside of LLM reasoning to ensure zero
prompt-injection or hallucination vulnerability.
"""

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

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
        data_valid = has_valid_names and has_valid_numbers and has_valid_currency

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-006",
                rule_name="Data Integrity & Safe Failure Check",
                description="Ensures all transaction fields contain valid, non-negative, and properly structured data.",
                passed=data_valid,
                details=(
                    "Transaction structure and numeric values are verified valid."
                    if data_valid
                    else "Missing required identification or invalid negative numeric values detected."
                ),
            )
        )
        if not data_valid:
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
        # Rule 3: Product Condition Compliance Check
        # -------------------------------------------------------------
        normalized_allowed_conditions = [c.strip().lower() for c in mandate.allowed_conditions]
        actual_condition = transaction.product_condition.strip().lower()
        condition_allowed = actual_condition in normalized_allowed_conditions

        checks.append(
            PolicyCheckSummary(
                rule_id="TG-003",
                rule_name="Product Condition Compliance",
                description="Verifies product condition conforms to allowed conditions in the purchase mandate.",
                passed=condition_allowed,
                details=(
                    f"Condition '{transaction.product_condition}' is permitted by mandate ({normalized_allowed_conditions})."
                    if condition_allowed
                    else f"Condition '{transaction.product_condition}' is prohibited. Mandate only permits: {normalized_allowed_conditions}."
                ),
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

        # -------------------------------------------------------------
        # Rule 4: Merchant Verification Requirement
        # -------------------------------------------------------------
        merchant_name_lower = transaction.merchant_name.strip().lower()
        is_blocked_merchant = merchant_name_lower in self.BLOCKED_MERCHANTS

        if mandate.require_merchant_verification:
            merchant_verified = transaction.merchant_verified and not is_blocked_merchant
        else:
            merchant_verified = not is_blocked_merchant

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
                        f"Merchant '{transaction.merchant_name}' is on the TrustGate blacklist."
                        if is_blocked_merchant
                        else f"Merchant '{transaction.merchant_name}' is unverified, but mandate requires verified status."
                    )
                ),
            )
        )
        if not merchant_verified:
            violations.append(
                PolicyViolation(
                    rule_id="TG-004",
                    rule_name="Unverified or Untrusted Merchant",
                    message=(
                        f"Merchant '{transaction.merchant_name}' is flagged as an untrusted or blacklisted vendor."
                        if is_blocked_merchant
                        else f"Merchant '{transaction.merchant_name}' is not verified, violating mandate requirement."
                    ),
                    severity=RuleSeverity.CRITICAL if is_blocked_merchant else RuleSeverity.HIGH,
                    expected="Verified merchant" if mandate.require_merchant_verification else "Non-blacklisted merchant",
                    actual=f"merchant_verified={transaction.merchant_verified}",
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
