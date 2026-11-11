"""Health check and system status endpoint."""

from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.services.paypal_service import paypal_service
from app.services.supabase_service import supabase_service

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def get_system_health():
    """Returns application health, security status, and integration state."""
    ai_key = settings.get_ai_api_key()
    ai_model = settings.get_ai_model()
    ai_base_url = settings.get_ai_base_url()
    ai_configured = bool(ai_key) and bool(ai_model)
    provider_name = "Groq" if "groq.com" in ai_base_url else "OpenAI-Compatible"

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "security_policy": {
            "ai_direct_execution_blocked": True,
            "human_in_the_loop_mandatory": True,
            "deterministic_guardrails": "ENFORCED",
        },
        "integrations": {
            "ai_inference": {
                "provider": provider_name,
                "model": ai_model or "Not Configured",
                "endpoint": ai_base_url,
                "configured": ai_configured,
            },
            "grok_ai": {
                "provider": provider_name,
                "model": ai_model or "Not Configured",
                "endpoint": ai_base_url,
                "configured": ai_configured,
            },
            "marketplaces": {
                "primary": "Channel3 Universal Product Graph",
                "status": "Configured" if settings.is_channel3_configured() else "Not Configured",
                "configured": settings.is_channel3_configured(),
                "supported_regions": ["global", "us", "amazon.in", "amazon.com"],
            },
            "channel3": settings.get_channel3_status(),
            "apimatic_context_plugin": {
                "installed_in_agent": False,
                "installer_command": "npx context-plugins install paypal",
                "marketplace_url": "https://context.apimatic.io/plugins/paypal/",
                "status": "NOT_INSTALLED_IN_AGENT",
            },
            "database": {
                "engine": "SQLite Persistent (ACID compliant)",
                "status": "online",
                "restart_resilient": True,
            },
            "paypal_sandbox": paypal_service.get_sandbox_status(),
            "supabase": supabase_service.get_status(),
        },
    }
