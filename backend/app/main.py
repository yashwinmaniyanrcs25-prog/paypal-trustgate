"""FastAPI application entrypoint for PayPal TrustGate."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import PaymentExecutionBlockedError
from app.api.routes import api_router
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trustgate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events."""
    logger.info("Initializing %s...", settings.APP_NAME)
    init_db()
    logger.info("Persistent database initialized.")
    logger.info("Security Invariant: AI_DIRECT_EXECUTION_ALLOWED = %s", settings.AI_DIRECT_EXECUTION_ALLOWED)
    logger.info("PayPal Mode: %s", settings.PAYPAL_MODE)
    logger.info("AI Provider Model: %s (Base URL: %s)", settings.get_ai_model() or "Unconfigured", settings.get_ai_base_url())
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-Powered Payment Security System for Agentic Commerce. "
        "Enforces deterministic policy gates between autonomous AI models and PayPal checkout."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PaymentExecutionBlockedError)
async def payment_execution_blocked_handler(request: Request, exc: PaymentExecutionBlockedError):
    """Security guardrail handler: intercepts unauthorized autonomous payment attempts."""
    logger.warning("BLOCKED TRANSACTION ATTEMPT: %s", exc.message)
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "PAYMENT_EXECUTION_BLOCKED",
            "message": exc.message,
            "policy": "TRUSTGATE_CORE_INVARIANT_01",
            "detail": "AI agents are strictly forbidden from authorizing payments.",
        },
    )


# Attach routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root():
    """Service status and quick info."""
    return {
        "service": settings.APP_NAME,
        "status": "online",
        "version": "0.1.0",
        "docs": "/docs",
        "api_v1": settings.API_V1_STR,
        "security_policy": "AI_PROPOSE_HUMAN_DISPOSE",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

