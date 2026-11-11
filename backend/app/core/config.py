"""Application configuration using Pydantic Settings."""
from pathlib import Path
from typing import Optional
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Central configuration for PayPal TrustGate."""

    # Application settings
    APP_NAME: str = "PayPal TrustGate"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS settings
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        import json
        try:
            return json.loads(v)
        except Exception:
            return ["http://localhost:5173", "http://localhost:3000"]

    # Provider-Neutral AI Inference Configuration (Defaults to Groq OpenAI-compatible endpoint)
    AI_API_KEY: str = Field(default="", description="Inference Provider API Key (e.g. Groq gsk_...)")
    AI_BASE_URL: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Inference Provider Base URL (e.g. https://api.groq.com/openai/v1)",
    )
    AI_MODEL: str = Field(
        default="",
        description="Inference Model Identifier (e.g. openai/gpt-oss-120b)",
    )

    # Legacy xAI / Grok aliases (supported for backward compatibility)
    XAI_API_KEY: str = Field(default="", description="Legacy xAI API Key")
    XAI_BASE_URL: str = Field(
        default="", description="Legacy xAI Base URL"
    )
    XAI_MODEL: str = Field(default="", description="Legacy xAI Model")

    GROK_API_KEY: str = Field(default="", description="Legacy Grok API Key")
    GROK_BASE_URL: str = Field(
        default="", description="Legacy Grok Base URL"
    )
    GROK_MODEL: str = Field(default="", description="Legacy Grok Model")

    def get_ai_api_key(self) -> str:
        """Returns the configured API key from AI_API_KEY, XAI_API_KEY, or GROK_API_KEY."""
        key = self.AI_API_KEY or self.XAI_API_KEY or self.GROK_API_KEY or ""
        if key.startswith("your_"):
            return ""
        return key.strip()

    def get_ai_base_url(self) -> str:
        """Returns the configured API base URL, defaulting to Groq."""
        if self.AI_BASE_URL and self.AI_BASE_URL.strip():
            url = self.AI_BASE_URL.strip().rstrip("/")
            # If the user previously had api.x.ai in AI_BASE_URL but has a gsk_ key, point to Groq
            if "api.x.ai" in url and self.get_ai_api_key().startswith("gsk_"):
                return "https://api.groq.com/openai/v1"
            return url
        if self.XAI_BASE_URL and "api.x.ai" not in self.XAI_BASE_URL:
            return self.XAI_BASE_URL.strip().rstrip("/")
        return "https://api.groq.com/openai/v1"

    def get_ai_model(self) -> str:
        """Returns the configured model name from AI_MODEL, XAI_MODEL, or GROK_MODEL.
        Does not invent or silently substitute an arbitrary model.
        """
        raw = (self.AI_MODEL or self.XAI_MODEL or self.GROK_MODEL or "").strip()
        if raw.upper() in ("XAI_API", "YOUR_MODEL", "YOUR_MODEL_HERE", "PLACEHOLDER"):
            return ""
        return raw

    def is_ai_configured(self) -> bool:
        """Checks if genuine AI provider API key is set."""
        key = self.get_ai_api_key()
        return bool(key and not key.startswith("your_"))

    # Backward compatibility aliases
    def get_xai_api_key(self) -> str:
        return self.get_ai_api_key()

    def get_xai_model(self) -> str:
        return self.get_ai_model()

    def get_xai_base_url(self) -> str:
        return self.get_ai_base_url()

    def is_xai_configured(self) -> bool:
        return self.is_ai_configured()

    # PayPal Sandbox Configuration (Sandbox Only)
    PAYPAL_ENV: str = Field(
        default="sandbox", description="PayPal environment: sandbox only"
    )
    PAYPAL_MODE: str = Field(
        default="sandbox", description="PayPal mode: sandbox only"
    )
    PAYPAL_CLIENT_ID: str = Field(
        default="", description="PayPal Sandbox Client ID"
    )
    PAYPAL_CLIENT_SECRET: str = Field(
        default="", description="PayPal Sandbox Client Secret"
    )
    PAYPAL_BASE_URL: str = Field(
        default="https://api-m.sandbox.paypal.com",
        description="PayPal API base URL (sandbox only)",
    )
    PAYPAL_CURRENCY: str = "USD"

    def is_paypal_configured(self) -> bool:
        """Checks if genuine PayPal Sandbox credentials are set."""
        cid = (self.PAYPAL_CLIENT_ID or "").strip()
        sec = (self.PAYPAL_CLIENT_SECRET or "").strip()
        if not cid or not sec:
            return False
        if cid.startswith("your_") or sec.startswith("your_"):
            return False
        return True

    def get_paypal_client_id(self) -> Optional[str]:
        """Returns public Sandbox Client ID only if configured."""
        if not self.is_paypal_configured():
            return None
        return self.PAYPAL_CLIENT_ID.strip()

    def get_paypal_base_url(self) -> str:
        """Enforces sandbox endpoint for hackathon prototype."""
        return "https://api-m.sandbox.paypal.com"

    # Supabase Configuration
    SUPABASE_URL: str = Field(default="", description="Supabase Project URL")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        default="", description="Supabase Service Role Key"
    )

    # Amazon Creators API Configuration
    AMAZON_CREDENTIAL_ID: str = Field(
        default="", description="Amazon Creators API Credential ID (Client ID / Access Key)"
    )
    AMAZON_CREDENTIAL_SECRET: str = Field(
        default="", description="Amazon Creators API Credential Secret"
    )
    AMAZON_CREDENTIAL_VERSION: str = Field(
        default="2.1", description="Amazon Creators API Credential Version"
    )
    AMAZON_PARTNER_TAG: str = Field(
        default="", description="Amazon Partner/Associate Tracking Tag"
    )
    AMAZON_MARKETPLACE: str = Field(
        default="www.amazon.com",
        description="Default Amazon Marketplace Host (e.g. www.amazon.in, www.amazon.com)",
    )

    def get_amazon_credentials(self) -> dict:
        """Returns sanitized Amazon credentials without exposing secrets in logs."""
        cred_id = (self.AMAZON_CREDENTIAL_ID or "").strip()
        secret = (self.AMAZON_CREDENTIAL_SECRET or "").strip()
        tag = (self.AMAZON_PARTNER_TAG or "").strip()

        # Sanitize placeholders
        if cred_id.startswith("your_"):
            cred_id = ""
        if secret.startswith("your_"):
            secret = ""
        if tag.startswith("your_"):
            tag = ""

        return {
            "credential_id": cred_id,
            "credential_secret": secret,
            "credential_version": self.AMAZON_CREDENTIAL_VERSION or "2.1",
            "partner_tag": tag,
            "marketplace": self.AMAZON_MARKETPLACE or "www.amazon.com",
            "is_configured": bool(cred_id and secret and tag),
        }

    # Channel3 Universal Catalog API Configuration
    CHANNEL3_API_KEY: str = Field(
        default="", description="Channel3 Universal Product Catalog API Key"
    )
    CHANNEL3_BASE_URL: str = Field(
        default="https://api.trychannel3.com/v1",
        description="Channel3 API Base URL",
    )

    def is_channel3_configured(self) -> bool:
        """Checks if genuine Channel3 API key is configured."""
        key = (self.CHANNEL3_API_KEY or "").strip()
        if not key or key.startswith("your_"):
            return False
        return True

    def get_channel3_api_key(self) -> str:
        """Returns Channel3 API key if configured. Never print in logs."""
        if not self.is_channel3_configured():
            return ""
        return self.CHANNEL3_API_KEY.strip()

    def get_channel3_base_url(self) -> str:
        """Returns Channel3 API base URL."""
        return (self.CHANNEL3_BASE_URL or "https://api.trychannel3.com/v1").strip().rstrip("/")

    def get_channel3_status(self) -> dict:
        """Returns sanitized Channel3 configuration diagnostics without exposing secrets."""
        configured = self.is_channel3_configured()
        return {
            "configured": configured,
            "base_url": self.get_channel3_base_url(),
            "search_endpoint": f"{self.get_channel3_base_url()}/search",
            "auth_header": "x-api-key",
            "catalog_type": "Universal Multi-Merchant Product Graph (100M+ Products)",
        }

    # Core Security Invariants
    DEFAULT_MAX_ORDER_USD: float = 250.00
    REQUIRE_EXPLICIT_USER_CONSENT: bool = True
    AI_DIRECT_EXECUTION_ALLOWED: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", str(_ENV_PATH)),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
