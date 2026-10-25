"""Optional, hard-gated xAI API adapter using the existing HTTPX dependency."""

import json
from typing import Any

from backend.config import XAI_APPROVED_BASE_URL, settings
from backend.services.ai_service import AIConfigurationError, parse_structured_response, post_completion


class GrokProvider:
    """OpenAI-compatible xAI adapter; selection and free-access gates live in AIService."""

    async def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = (settings.xai_api_key or "").strip()
        model = (settings.xai_model or "").strip()
        base_url = settings.xai_base_url or XAI_APPROVED_BASE_URL
        if (
            settings.allow_paid_apis is not False
            or settings.ai_provider != "grok"
            or not settings.enable_grok
            or not settings.grok_free_api_access_confirmed
            or not api_key
            or not model
            or base_url != XAI_APPROVED_BASE_URL
        ):
            raise AIConfigurationError("Grok is disabled or is not fully configured for confirmed free API access.")

        response = await post_completion(
            url=f"{XAI_APPROVED_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "max_tokens": settings.ai_max_output_tokens,
                "stream": False,
            },
            provider_name="Grok",
        )
        return parse_structured_response(response, "Grok")
