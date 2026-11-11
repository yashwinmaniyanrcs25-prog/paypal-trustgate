"""Groq-powered Natural Language Purchase Intent Interpreter Service.

This service utilizes Grok / Groq OpenAI-compatible API to translate
natural-language shopping requests into structured Purchase Mandates conforming to
TrustGate Pydantic schemas.

CRITICAL INVARIANTS:
1. The AI only interprets intent into mandate bounds. It NEVER authorizes payments.
2. If required fields (e.g. maximum budget) are missing or ambiguous, it returns a clarification requirement.
3. The service NEVER silently falls back to fabricated output when provider is unconfigured or fails.
4. Secrets are NEVER printed, logged, or exposed in error messages.
5. Models are NEVER silently substituted or guessed.
"""

import json
import logging
import httpx
from typing import Dict, Any, Optional

from app.core.config import settings
from app.models.intent import IntentInterpretationResponse
from app.models.policy import PurchaseMandate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an Intent-to-Mandate Interpreter for PayPal TrustGate.
Your role is to strictly translate natural-language shopping requests into a structured Purchase Mandate JSON.

OUTPUT JSON SCHEMA:
{
  "max_amount": float or null,
  "currency": string (3-letter ISO code: "USD", "INR", "EUR", "GBP", etc.),
  "allowed_conditions": list of strings (only "new", "used", "refurbished"),
  "require_merchant_verification": boolean,
  "allow_add_ons": boolean,
  "user_restrictions": list of strings,
  "needs_clarification": boolean,
  "clarification_prompt": string or null,
  "extracted_intent_summary": string
}

RULES:
1. MAX BUDGET: Must be explicitly specified by the user.
   - Examples:
     * "under ₹60,000" -> max_amount: 60000.0, currency: "INR"
     * "under $150" -> max_amount: 150.0, currency: "USD"
     * "below 500 euros" -> max_amount: 500.0, currency: "EUR"
   - Currency symbol mapping: ₹ -> "INR", $ -> "USD", € -> "EUR", £ -> "GBP".
   - If the user DOES NOT specify any budget or spending limit, set:
     "needs_clarification": true,
     "clarification_prompt": "A maximum budget limit is required to create a safe purchase mandate. Please specify your maximum spending limit and currency (e.g., 'under ₹60,000' or 'max $500').",
     "max_amount": null.
   - DO NOT INVENT A BUDGET IF THE USER DID NOT SPECIFY ONE.

2. ALLOWED CONDITIONS:
   - "new" -> ["new"]
   - "no refurbished" -> ["new"]
   - "used or refurbished" -> ["used", "refurbished"]
   - If no condition is mentioned, default to ["new"].

3. MERCHANT VERIFICATION:
   - If user asks for "verified seller", "only verified merchant", "official store", set require_merchant_verification: true.
   - Default is true for security.

4. ADD-ONS & ACCESSORIES:
   - "no accessories", "no add-ons", "no bundle items", "without warranty upsells" -> allow_add_ons: false.
   - If user explicitly permits add-ons -> allow_add_ons: true.
   - Default is false.

5. USER RESTRICTIONS:
   - Extract key constraints explicitly mentioned by user (e.g. "laptop only", "no accessories", "verified seller only").
   - DO NOT invent constraints the user did not specify.

6. ABSOLUTE SECURITY INVARIANT:
   - Output ONLY structured intent bounds. You have zero payment execution authority.

Return strictly valid JSON matching the schema above.
"""


class IntentInterpreterService:
    """Interprets natural language into structured Purchase Mandates via Groq inference."""

    def __init__(self):
        self.timeout = 15.0

    async def interpret_intent(self, prompt: str) -> IntentInterpretationResponse:
        """Translates user natural language into a structured Purchase Mandate."""
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            return IntentInterpretationResponse(
                raw_prompt=prompt,
                success=False,
                status="VALIDATION_ERROR",
                error_message="Purchase description cannot be empty.",
            )

        api_key = settings.get_ai_api_key()
        if not api_key:
            logger.warning("Inference API key is not configured.")
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="PROVIDER_UNCONFIGURED",
                error_message=(
                    "Inference API key is not configured on the backend. "
                    "Please set AI_API_KEY in backend/.env with your Groq API key (starts with 'gsk_'). "
                    "You can obtain one at https://console.groq.com/keys."
                ),
            )

        base_url = settings.get_ai_base_url()
        model = settings.get_ai_model()

        # If model is unconfigured or set to a placeholder, fail with a clear configuration message
        if not model or model.upper() in (
            "XAI_API",
            "YOUR_AVAILABLE_GROQ_MODEL",
            "YOUR_MODEL",
            "YOUR_MODEL_HERE",
            "PLACEHOLDER",
        ):
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="PROVIDER_UNCONFIGURED",
                error_message=(
                    "Inference model is not configured. "
                    "Please set AI_MODEL (or XAI_MODEL) in backend/.env to a valid model available to your Groq account "
                    "(e.g., AI_MODEL=openai/gpt-oss-120b or AI_MODEL=llama-3.1-8b-instant). "
                    "You can verify currently active models in the Groq Console at https://console.groq.com/docs/models."
                ),
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User purchase request: {cleaned_prompt}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_json = response.json()

            raw_content = response_json["choices"][0]["message"]["content"]
            parsed_data = json.loads(raw_content)

        except httpx.TimeoutException:
            logger.error("Inference provider request timed out.")
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="PROVIDER_ERROR",
                error_message="The Groq inference provider timed out. Please try again or check Groq status.",
            )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            safe_detail = "Forbidden"
            try:
                err_json = e.response.json()
                if isinstance(err_json, dict) and "error" in err_json:
                    err_val = err_json["error"]
                    if isinstance(err_val, dict):
                        safe_detail = err_val.get("message", "Error")
                    else:
                        safe_detail = str(err_val)
            except Exception:
                safe_detail = e.response.reason_phrase or "Error"

            logger.error("Inference provider returned HTTP %s (sanitized: %s)", status_code, safe_detail)

            if status_code == 401:
                msg = (
                    "Groq API returned HTTP 401 Unauthorized: Invalid API key. "
                    "Please verify AI_API_KEY in backend/.env against https://console.groq.com/keys."
                )
            elif status_code == 403:
                msg = (
                    f"Groq API returned HTTP 403 Forbidden ({safe_detail}). "
                    "Please verify your Groq account standing and organization settings at https://console.groq.com/."
                )
            elif status_code == 404:
                msg = (
                    f"Groq API returned HTTP 404: Model '{model}' not found. "
                    "Please check active models available to your account at https://console.groq.com/docs/models."
                )
            elif status_code == 429:
                msg = "Groq API returned HTTP 429: Rate limit or token quota exceeded. Please wait a moment and try again."
            else:
                msg = f"Groq API returned HTTP {status_code}: {safe_detail}."

            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="PROVIDER_ERROR",
                error_message=msg,
            )
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response from Groq: %s", str(e))
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="VALIDATION_ERROR",
                error_message="The inference provider returned non-JSON structured output. Please rephrase the request.",
            )
        except Exception as e:
            logger.error("Unexpected error calling inference provider: %s", str(e))
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="PROVIDER_ERROR",
                error_message="An unexpected error occurred while communicating with the inference provider.",
            )

        # Process Groq's structured output
        needs_clarification = parsed_data.get("needs_clarification", False)
        clarification_prompt = parsed_data.get("clarification_prompt")
        max_amount = parsed_data.get("max_amount")

        # If budget is missing or clarification flagged
        if needs_clarification or max_amount is None or float(max_amount) <= 0:
            default_clarification = (
                "A maximum budget limit is required to create a safe purchase mandate. "
                "Please specify your maximum spending limit and currency (e.g. 'under ₹60,000' or 'max $500')."
            )
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=True,
                status="NEEDS_CLARIFICATION",
                needs_clarification=True,
                clarification_prompt=clarification_prompt or default_clarification,
                mandate=None,
                extracted_intent_summary=parsed_data.get("extracted_intent_summary"),
                ai_explanation="The purchase request lacks an unambiguous maximum budget limit.",
                is_confirmed=False,
            )

        # Normalize currency (handle ₹ symbol mapping if not already converted)
        raw_currency = str(parsed_data.get("currency", "USD")).strip().upper()
        if raw_currency == "₹" or "RUPEE" in raw_currency or "INR" in raw_currency:
            currency_code = "INR"
        elif raw_currency == "$" or "DOLLAR" in raw_currency or "USD" in raw_currency:
            currency_code = "USD"
        elif raw_currency == "€" or "EURO" in raw_currency or "EUR" in raw_currency:
            currency_code = "EUR"
        elif raw_currency == "£" or "POUND" in raw_currency or "GBP" in raw_currency:
            currency_code = "GBP"
        else:
            currency_code = raw_currency if len(raw_currency) == 3 else "USD"

        try:
            mandate = PurchaseMandate(
                max_amount=float(max_amount),
                currency=currency_code,
                allowed_conditions=parsed_data.get("allowed_conditions", ["new"]),
                require_merchant_verification=bool(
                    parsed_data.get("require_merchant_verification", True)
                ),
                allow_add_ons=bool(parsed_data.get("allow_add_ons", False)),
                user_restrictions=parsed_data.get("user_restrictions", []),
            )
        except Exception as val_err:
            logger.error("Failed to construct PurchaseMandate from output: %s", str(val_err))
            return IntentInterpretationResponse(
                raw_prompt=cleaned_prompt,
                success=False,
                status="VALIDATION_ERROR",
                error_message=f"Interpreted mandate failed schema validation: {str(val_err)}",
            )

        summary = parsed_data.get(
            "extracted_intent_summary",
            f"Extracted purchase mandate: Max {currency_code} {mandate.max_amount:.2f}, "
            f"Conditions: {mandate.allowed_conditions}, Verified Merchant: {mandate.require_merchant_verification}, "
            f"Add-ons: {mandate.allow_add_ons}."
        )

        return IntentInterpretationResponse(
            raw_prompt=cleaned_prompt,
            success=True,
            status="SUCCESS",
            needs_clarification=False,
            clarification_prompt=None,
            mandate=mandate,
            extracted_intent_summary=summary,
            ai_explanation="Successfully translated natural language request into structured purchase mandate via Groq.",
            is_confirmed=False,
        )


intent_interpreter_service = IntentInterpreterService()
