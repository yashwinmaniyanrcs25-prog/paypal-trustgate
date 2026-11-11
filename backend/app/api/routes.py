"""Consolidated API router for PayPal TrustGate."""

from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.agent import router as agent_router
from app.api.v1.policies import router as policies_router
from app.api.v1.intent import router as intent_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.payments import router as payments_router
from app.api.v1.audit import router as audit_router
from app.api.v1.channel3 import router as channel3_router
from app.api.v1.apimatic import router as apimatic_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(agent_router)

# Mount intent interpreter under /intent
api_router.include_router(intent_router, prefix="/intent")

# Mount candidate proposal discovery & evaluation under /proposals
api_router.include_router(proposals_router, prefix="/proposals")

# Mount Channel3 Universal Product Graph under /channel3
api_router.include_router(channel3_router, prefix="/channel3")

# Mount APIMatic pre-flight validator under /apimatic
api_router.include_router(apimatic_router, prefix="/apimatic")

# Mount PayPal Sandbox payments under /payments
api_router.include_router(payments_router, prefix="/payments")

# Mount Trust & Audit Layer under /audit
api_router.include_router(audit_router, prefix="/audit")

# Mount policies under both /policy (standard) and /policies (plural alias)
api_router.include_router(policies_router, prefix="/policy")
api_router.include_router(policies_router, prefix="/policies")
