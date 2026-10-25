"""NVIDIA NIM chat-completions client with safe provider error mapping."""

import asyncio
import json
import re
from typing import Any

import httpx

from backend.config import settings


class AIProviderError(Exception):
    """Base class for user-safe AI provider errors."""

    status_code = 502


class AIConfigurationError(AIProviderError):
    status_code = 503


class AIAuthenticationError(AIProviderError):
    status_code = 502


class AIRateLimitError(AIProviderError):
    status_code = 429


class AIProviderTimeout(AIProviderError):
    status_code = 504


class AIModelUnavailable(AIProviderError):
    status_code = 502


class AIProviderUnavailable(AIProviderError):
    status_code = 502


class AIInvalidResponse(AIProviderError):
    status_code = 502


class NVIDIAProvider:
    """Calls NVIDIA's OpenAI-compatible NIM inference endpoint."""

    async def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = (settings.nvidia_nim_api_key or "").strip()
        if not api_key:
            raise AIConfigurationError(
                "AI analysis is not configured. Add NVIDIA_NIM_API_KEY to the backend environment; document uploads and extraction still work."
            )

        url = f"{settings.nvidia_nim_api_base_url.rstrip('/')}/chat/completions"
        request_body = {
            "model": settings.nvidia_nim_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": settings.nvidia_nim_temperature,
            "top_p": settings.nvidia_nim_top_p,
            "max_tokens": settings.nvidia_nim_max_tokens,
            "stream": False,
        }

        try:
            async with asyncio.timeout(settings.nvidia_nim_timeout_seconds):
                async with _provider_slots:
                    async with httpx.AsyncClient(timeout=settings.nvidia_nim_timeout_seconds) as client:
                        response = await client.post(
                            url,
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json=request_body,
                        )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise AIProviderTimeout("NVIDIA NIM took too long to respond. Try again with a shorter document.") from exc
        except httpx.RequestError as exc:
            raise AIProviderUnavailable("NVIDIA NIM could not be reached. Check the provider URL and try again.") from exc

        if response.status_code == 429:
            raise AIRateLimitError("NVIDIA NIM is rate limiting requests. Please wait briefly and try again.")
        if response.status_code in {401, 403}:
            raise AIAuthenticationError("NVIDIA NIM rejected the configured API key. Check the backend secret and model access.")
        if response.status_code == 404:
            raise AIModelUnavailable("The configured NVIDIA NIM model or endpoint is unavailable. Check the model name and API base URL.")
        if response.status_code >= 500:
            raise AIProviderUnavailable("NVIDIA NIM is temporarily unavailable. Try again later.")
        if response.status_code >= 400:
            raise AIProviderError(f"NVIDIA NIM rejected the request (HTTP {response.status_code}). Check the model and generation settings.")

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model response")
            content = content.strip()
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
            if fenced:
                content = fenced.group(1)
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("model output must be an object")
            return parsed
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIInvalidResponse("NVIDIA NIM returned malformed structured output. Please retry the analysis.") from exc


_provider_slots = asyncio.Semaphore(settings.max_concurrent_ai_requests)
provider = NVIDIAProvider()
