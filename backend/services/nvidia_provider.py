"""NVIDIA NIM adapter using the project's existing HTTPX dependency."""

import json
from typing import Any

from backend.config import NVIDIA_APPROVED_BASE_URL, settings
from backend.services.ai_service import (
    AIConfigurationError,
    parse_structured_response,
    post_completion,
)


class NVIDIAProvider:
    """OpenAI-compatible adapter for the explicitly approved NVIDIA endpoint."""

    async def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = (settings.nvidia_nim_api_key or "").strip()
        model = (settings.nvidia_nim_model or "").strip()
        base_url = settings.nvidia_nim_api_base_url
        if (
            settings.allow_paid_apis is not False
            or settings.ai_provider != "nvidia_nim"
            or not settings.nvidia_nim_free_access_confirmed
            or not api_key
            or not model
            or base_url != NVIDIA_APPROVED_BASE_URL
        ):
            raise AIConfigurationError("NVIDIA NIM is not fully configured for the approved endpoint.")

        response = await post_completion(
            url=f"{NVIDIA_APPROVED_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "temperature": settings.nvidia_nim_temperature,
                "top_p": settings.nvidia_nim_top_p,
                "max_tokens": settings.ai_max_output_tokens,
                "stream": False,
            },
            provider_name="NVIDIA NIM",
        )
        return parse_structured_response(response, "NVIDIA NIM")
