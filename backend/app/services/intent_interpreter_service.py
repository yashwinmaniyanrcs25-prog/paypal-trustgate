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
import re
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
  "category": string or null (e.g. "laptop", "keyboard", "mouse"),
  "search_query": string or null (e.g. "laptop", "keyboard", "wireless mouse"),
  "condition": string or null ("NEW", "USED", "REFURBISHED"),
  "allowed_conditions": list of strings (only "new", "used", "refurbished"),
  "min_ram_gb": integer or null (e.g. 16, 8, 32),
  "min_storage_gb": integer or null (e.g. 512, 256, 1024),
  "storage_type": string or null (e.g. "SSD", "NVMe", "HDD"),
  "processor_requirement": string or null (e.g. "Intel Core i5 or AMD Ryzen 5 or better"),
  "gpu_requirement": string or null,
  "display_size": string or null,
  "brand_preference": string or null,
  "model_preference": string or null,
  "marketplace": string or null (e.g. "amazon.in", "amazon.com"),
  "verified_seller_required": boolean,
  "require_merchant_verification": boolean,
  "allow_accessories": boolean,
  "allow_add_ons": boolean,
  "in_stock_required": boolean,
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

2. CATEGORY & SEARCH QUERY SEPARATION:
   - "category": Extract ONLY the physical product category noun (e.g. "laptop", "keyboard", "mouse", "headphones", "monitor").
     * CRITICAL: Do NOT include condition words ("new", "brand-new", "refurbished") or restrictions in category!
     * For "I need a brand-new laptop...", category MUST be "laptop".
   - "search_query": The primary catalog search query term (e.g. "laptop", "wireless mouse", "Keychron K2").
     * NEVER use condition text ("brand new only", "new"), seller restrictions ("verified seller"), or prohibitions ("no accessories", "no refurbished") as the search_query or category.
     * Keep category and search_query focused on the item being sought (e.g. "laptop").

3. SPECIFICATIONS (for laptops & electronics):
   - Extract min_ram_gb (e.g., "16GB RAM" -> 16, "at least 8GB" -> 8).
   - Extract min_storage_gb (e.g., "512GB SSD" -> 512, "1TB" -> 1024).
   - Extract storage_type (e.g., "SSD", "NVMe").
   - Extract processor_requirement (e.g., "Intel Core i5 or AMD Ryzen 5 or better").
   - Extract marketplace if specified (e.g. "Amazon India" -> "amazon.in", "Amazon US" -> "amazon.com").
   - in_stock_required defaults to true.

4. ALLOWED CONDITIONS:
   - "new", "brand-new", "brand new" -> condition: "NEW", allowed_conditions: ["new"]
   - "no refurbished" -> condition: "NEW", allowed_conditions: ["new"]
   - "used or refurbished" -> condition: "USED", allowed_conditions: ["used", "refurbished"]
   - Default condition: "NEW", allowed_conditions: ["new"].
   - Condition belongs ONLY in condition / allowed_conditions, NEVER in category or search_query.

5. MERCHANT VERIFICATION:
   - If user asks for "verified seller", "verified sellers", "only verified merchant", "official store", set verified_seller_required: true, require_merchant_verification: true.
   - Default is true for security.

6. ADD-ONS & ACCESSORIES:
   - "no accessories", "no add-ons", "no bundle items", "without warranty upsells", "no extended warranties or subscriptions" -> allow_accessories: false, allow_add_ons: false.
   - If user explicitly permits add-ons -> allow_accessories: true, allow_add_ons: true.
   - Default is false.
   - Do NOT put "no accessories" into category or search_query.

7. USER RESTRICTIONS:
   - Extract contextual constraints explicitly mentioned by user (e.g. "Amazon India only", "verified seller only").
   - Prohibitions and conditions (like "brand-new", "no refurbished", "no accessories") are already handled by allowed_conditions, require_merchant_verification, and allow_add_ons.

8. ABSOLUTE SECURITY INVARIANT:
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
        prompt_lower = cleaned_prompt.lower()
        if raw_currency == "₹" or "RUPEE" in raw_currency or "INR" in raw_currency or "₹" in cleaned_prompt or "amazon india" in prompt_lower:
            currency_code = "INR"
        elif raw_currency == "$" or "DOLLAR" in raw_currency or "USD" in raw_currency:
            currency_code = "USD"
        elif raw_currency == "€" or "EURO" in raw_currency or "EUR" in raw_currency:
            currency_code = "EUR"
        elif raw_currency == "£" or "POUND" in raw_currency or "GBP" in raw_currency:
            currency_code = "GBP"
        else:
            currency_code = raw_currency if len(raw_currency) == 3 else "USD"

        # Terms that must NEVER be used as category or primary search query
        PROHIBITED_QUERY_TERMS = {
            "brand new only", "brand new", "brand-new", "new only", "new", "refurbished",
            "used", "verified seller", "verified seller only", "verified sellers",
            "no refurbished", "no accessories", "no refurbished products", "no add-ons",
            "in stock only", "in-stock only", "in stock", "verified", "accessories",
        }

        # 1. Category extraction & sanitization
        raw_cat = str(parsed_data.get("category") or "").strip()
        clean_cat = raw_cat
        for prefix in ("brand-new", "brand new", "brand new only", "new only", "new"):
            if clean_cat.lower().startswith(prefix):
                clean_cat = clean_cat[len(prefix):].strip()
        if not clean_cat or clean_cat.lower() in PROHIBITED_QUERY_TERMS:
            # Infer from user prompt
            if any(lp in prompt_lower for lp in ("laptop", "notebook", "ultrabook", "macbook", "chromebook")):
                clean_cat = "laptop"
            elif "keyboard" in prompt_lower or "keychron" in prompt_lower:
                clean_cat = "keyboard"
            elif "mouse" in prompt_lower or "mice" in prompt_lower:
                clean_cat = "mouse"
            elif "headphone" in prompt_lower or "headset" in prompt_lower:
                clean_cat = "headphones"
            elif "monitor" in prompt_lower:
                clean_cat = "monitor"
            else:
                clean_cat = raw_cat or "laptop"

        # 2. Search query extraction & sanitization
        raw_query = str(parsed_data.get("search_query") or "").strip()
        clean_query = raw_query
        for prefix in ("brand-new", "brand new", "brand new only", "new only", "new"):
            if clean_query.lower().startswith(prefix):
                clean_query = clean_query[len(prefix):].strip()
        if not clean_query or clean_query.lower() in PROHIBITED_QUERY_TERMS:
            clean_query = clean_cat or "laptop"

        # 3. Allowed conditions
        raw_conds = parsed_data.get("allowed_conditions")
        if not raw_conds and parsed_data.get("condition"):
            raw_conds = [str(parsed_data.get("condition")).lower()]
        if not raw_conds:
            raw_conds = ["new"]
        if "no refurbished" in prompt_lower or "brand-new" in prompt_lower or "brand new" in prompt_lower or "new" in prompt_lower:
            raw_conds = ["new"]

        # 4. Merchant verification requirement
        merchant_ver = parsed_data.get("require_merchant_verification")
        if merchant_ver is None:
            merchant_ver = parsed_data.get("verified_seller_required")
        if merchant_ver is None:
            merchant_ver = ("verified seller" in prompt_lower or "verified merchant" in prompt_lower or "verified sellers" in prompt_lower)
        merchant_ver = bool(merchant_ver) if merchant_ver is not None else True

        # 5. Add-ons & accessories allowance
        allow_add_ons = parsed_data.get("allow_add_ons")
        if allow_add_ons is None:
            allow_add_ons = parsed_data.get("allow_accessories")
        if allow_add_ons is None or ("no accessories" in prompt_lower or "no add-ons" in prompt_lower):
            allow_add_ons = False
        else:
            allow_add_ons = bool(allow_add_ons)

        # 6. Hardware specifications extraction with fallback regex
        raw_ram = parsed_data.get("min_ram_gb")
        min_ram_gb = int(raw_ram) if raw_ram is not None and str(raw_ram).isdigit() else None
        if min_ram_gb is None:
            ram_match = re.search(r'(\d+)\s*gb\s*ram', prompt_lower)
            if ram_match:
                min_ram_gb = int(ram_match.group(1))

        raw_storage = parsed_data.get("min_storage_gb")
        min_storage_gb = int(raw_storage) if raw_storage is not None and str(raw_storage).isdigit() else None
        if min_storage_gb is None:
            st_match = re.search(r'(\d+)\s*(?:gb|tb)\s*(?:ssd|nvme|storage)?', prompt_lower)
            if st_match:
                val = int(st_match.group(1))
                if "tb" in st_match.group(0):
                    val *= 1024
                min_storage_gb = val

        storage_type = parsed_data.get("storage_type")
        if not storage_type:
            if "nvme" in prompt_lower:
                storage_type = "NVMe"
            elif "ssd" in prompt_lower:
                storage_type = "SSD"

        proc_req = parsed_data.get("processor_requirement")
        if not proc_req:
            if "core i5 or ryzen 5" in prompt_lower or "i5 or ryzen 5" in prompt_lower:
                proc_req = "Intel Core i5 or AMD Ryzen 5 or better"
            elif "core i5" in prompt_lower or "i5" in prompt_lower:
                proc_req = "Intel Core i5 or better"
            elif "core i7" in prompt_lower or "i7" in prompt_lower:
                proc_req = "Intel Core i7 or better"

        mkt = parsed_data.get("marketplace")
        if not mkt:
            if "amazon india" in prompt_lower or "amazon.in" in prompt_lower:
                mkt = "amazon.in"
            elif "amazon us" in prompt_lower or "amazon.com" in prompt_lower:
                mkt = "amazon.com"

        # 7. Clean user restrictions
        raw_restrictions = parsed_data.get("user_restrictions", [])
        user_restrictions = []
        if isinstance(raw_restrictions, list):
            for r in raw_restrictions:
                r_clean = str(r).strip()
                r_lower = r_clean.lower()
                # Exclude redundant condition/addon strings that cause query confusion
                if r_lower in ("brand new only", "brand-new only", "new only", "new condition", "no refurbished", "no accessories"):
                    continue
                user_restrictions.append(r_clean)

        try:
            mandate = PurchaseMandate(
                max_amount=float(max_amount),
                currency=currency_code,
                allowed_conditions=raw_conds,
                require_merchant_verification=merchant_ver,
                allow_add_ons=allow_add_ons,
                user_restrictions=user_restrictions,
                category=clean_cat,
                search_query=clean_query,
                min_ram_gb=min_ram_gb,
                min_storage_gb=min_storage_gb,
                storage_type=storage_type,
                processor_requirement=proc_req,
                gpu_requirement=parsed_data.get("gpu_requirement"),
                display_size=parsed_data.get("display_size"),
                brand_preference=parsed_data.get("brand_preference"),
                model_preference=parsed_data.get("model_preference"),
                marketplace=mkt,
                in_stock_required=bool(parsed_data.get("in_stock_required", True)),
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
