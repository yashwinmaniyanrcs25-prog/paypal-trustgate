"""Deterministic policy evaluation endpoints."""

from typing import List, Dict, Any, Union
from fastapi import APIRouter, HTTPException, status
from app.models.policy import (
    MandatePolicyEvaluationRequest,
    MandatePolicyEvaluationResponse,
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
)
from app.services.policy_engine import policy_engine
from app.services.supabase_service import supabase_service

router = APIRouter(tags=["Policy Engine"])


@router.post(
    "/evaluate",
    response_model=Union[MandatePolicyEvaluationResponse, PolicyEvaluationResponse],
    status_code=status.HTTP_200_OK,
    summary="Evaluate proposed transaction against purchase mandate constraints",
)
async def evaluate_purchase_policy(
    request: Union[MandatePolicyEvaluationRequest, PolicyEvaluationRequest]
):
    """Executes deterministic policy verification.

    Validates spending limits, currency matches, product conditions, merchant verification,
    and prohibits unauthorized add-ons. Logs the result to the audit ledger.
    """
    try:
        if isinstance(request, MandatePolicyEvaluationRequest):
            result = policy_engine.evaluate_mandate(
                mandate=request.mandate,
                transaction=request.transaction,
                caller_role=request.caller_role,
            )
            total = result.transaction_summary.get("final_total", 0.0)
            await supabase_service.log_policy_evaluation(
                evaluation_id=result.evaluation_id,
                user_id="mandate_user",
                passed=result.approved,
                total_cost=total,
                rules_checked=len(result.checks),
                violations=[v.message for v in result.violations],
            )
            return result
        else:
            result = policy_engine.evaluate(request)
            await supabase_service.log_policy_evaluation(
                evaluation_id=result.evaluation_id,
                user_id=request.user_id,
                passed=result.passed,
                total_cost=result.total_evaluated_cost,
                rules_checked=len(result.checks),
                violations=[v.message for v in result.violations],
            )
            return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Policy evaluation failure: {str(e)}",
        )


@router.get(
    "/rules",
    summary="Get active deterministic policy rules",
)
async def get_active_rules():
    """Returns currently enforced deterministic guardrails."""
    return {
        "rules": [
            {
                "rule_id": "TG-001",
                "name": "Mandate Spending Limit & Math Integrity",
                "description": "Total checkout price must not exceed mandate maximum amount and must equal itemized charges sum.",
                "enforcement": "DETERMINISTIC_MATHEMATICAL",
            },
            {
                "rule_id": "TG-002",
                "name": "Currency Alignment Check",
                "description": "Transaction currency must strictly match the currency designated in the purchase mandate.",
                "enforcement": "CURRENCY_MATCH",
            },
            {
                "rule_id": "TG-003",
                "name": "Product Condition Compliance",
                "description": "Product condition (new, used, refurbished) must conform to mandate allowed conditions.",
                "enforcement": "ENUM_MEMBERSHIP",
            },
            {
                "rule_id": "TG-004",
                "name": "Merchant Verification & Trust Check",
                "description": "Merchant must be verified if required by mandate and not listed in untrusted vendor blacklist.",
                "enforcement": "MERCHANT_WHITELIST",
            },
            {
                "rule_id": "TG-005",
                "name": "Add-On & Hidden Fee Protection",
                "description": "Prohibits unexpected accessory add-ons or hidden charges unless explicitly enabled by user mandate.",
                "enforcement": "PARAM_BOUNDS",
            },
            {
                "rule_id": "TG-006",
                "name": "Data Integrity & Safe Failure Check",
                "description": "Fails safely if transaction data has missing identifiers, empty names, or negative numbers.",
                "enforcement": "SAFE_INTEGRITY",
            },
            {
                "rule_id": "TG-007",
                "name": "AI Zero Autonomous Execution Invariant",
                "description": "AI models are strictly prohibited from directly approving or executing payments.",
                "enforcement": "CORE_INVARIANT_BLOCK",
            },
        ]
    }


@router.get(
    "/audit",
    summary="Get recent policy evaluation audit logs",
)
async def get_audit_trail():
    """Returns immutable policy evaluation records."""
    logs = await supabase_service.get_recent_audit_logs(limit=25)
    return {"count": len(logs), "logs": logs}
