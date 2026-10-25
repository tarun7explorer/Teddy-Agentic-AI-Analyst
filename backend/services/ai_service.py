"""Canonical, fail-closed interface for optional structured AI requests."""

import asyncio
import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from backend.config import (
    NVIDIA_APPROVED_BASE_URL,
    XAI_APPROVED_BASE_URL,
    settings,
)


class AIProviderError(Exception):
    """Base class for normalized, user-safe provider errors."""

    status_code = 502
    code = "provider_error"


class AIConfigurationError(AIProviderError):
    status_code = 503
    code = "ai_unavailable"


class AIAuthenticationError(AIProviderError):
    code = "provider_authentication_failed"


class AIRateLimitError(AIProviderError):
    status_code = 429
    code = "provider_rate_limited"


class AIQuotaError(AIRateLimitError):
    code = "provider_quota_exhausted"


class AIBillingError(AIProviderError):
    status_code = 402
    code = "provider_payment_required"


class AIProviderTimeout(AIProviderError):
    status_code = 504
    code = "provider_timeout"


class AIModelUnavailable(AIProviderError):
    code = "provider_model_unavailable"


class AIProviderUnavailable(AIProviderError):
    code = "provider_unavailable"


class AIInvalidResponse(AIProviderError):
    code = "provider_invalid_response"


class AIProviderStatus(BaseModel):
    """Secret-free view of whether the configured provider can be used."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "nvidia_nim", "grok"]
    available: bool
    code: str
    message: str


def _provider_error_code(response: Any) -> str:
    """Read only an enumerated error code; never return provider text to callers."""
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            return ""
        value = error.get("code") or error.get("type") or ""
        return str(value).casefold()[:80]
    except Exception:
        return ""


def raise_for_provider_status(response: Any, provider_name: str) -> None:
    status_code = int(response.status_code)
    provider_code = _provider_error_code(response)
    if status_code == 402 or any(term in provider_code for term in ("billing", "payment", "insufficient_funds")):
        raise AIBillingError(f"{provider_name} API access requires billing. No fallback was attempted.")
    if status_code == 429 or any(term in provider_code for term in ("quota", "rate_limit", "rate-limit", "insufficient_quota")):
        if "quota" in provider_code:
            raise AIQuotaError(f"{provider_name} free API quota is unavailable or exhausted. No fallback was attempted.")
        raise AIRateLimitError(f"{provider_name} is rate limiting requests. No retry or fallback was attempted.")
    if status_code in {401, 403}:
        raise AIAuthenticationError(f"{provider_name} rejected the configured API credentials or access.")
    if status_code == 404:
        raise AIModelUnavailable(f"The configured {provider_name} model or endpoint is unavailable.")
    if status_code >= 500:
        raise AIProviderUnavailable(f"{provider_name} is temporarily unavailable.")
    if status_code >= 400:
        raise AIProviderError(f"{provider_name} rejected the request (HTTP {status_code}).")


def parse_structured_response(response: Any, provider_name: str) -> dict[str, Any]:
    raise_for_provider_status(response, provider_name)
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty provider output")
        if len(content) > settings.ai_max_output_chars:
            raise ValueError("provider output exceeded configured size limit")
        content = content.strip()
        if content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
            if content[:4].casefold() == "json":
                content = content[4:].strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("structured output must be an object")
        return parsed
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIInvalidResponse(f"{provider_name} returned malformed or oversized structured output.") from exc


async def post_completion(
    *, url: str, headers: dict[str, str], body: dict[str, Any], provider_name: str,
) -> Any:
    """Send once, with at most one retry only when a connection was never established."""
    approved_urls = {
        "NVIDIA NIM": f"{NVIDIA_APPROVED_BASE_URL}/chat/completions",
        "Grok": f"{XAI_APPROVED_BASE_URL}/chat/completions",
    }
    if approved_urls.get(provider_name) != url:
        raise AIConfigurationError("The configured provider endpoint is not approved.")
    for attempt in range(settings.ai_max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
                return await client.post(url, headers=headers, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if attempt < settings.ai_max_retries:
                continue
            raise AIProviderUnavailable(f"{provider_name} could not be reached.") from exc
        except httpx.TimeoutException as exc:
            raise AIProviderTimeout(f"{provider_name} took too long to respond.") from exc
        except httpx.RequestError as exc:
            raise AIProviderUnavailable(f"{provider_name} could not be reached.") from exc
    raise AIProviderUnavailable(f"{provider_name} could not be reached.")


def _configuration_status() -> AIProviderStatus:
    selected = settings.ai_provider
    if settings.allow_paid_apis is not False:
        return AIProviderStatus(
            provider=selected, available=False, code="paid_api_disabled",
            message="Paid API usage is disabled by application policy.",
        )
    if selected == "none":
        return AIProviderStatus(
            provider="none", available=False, code="ai_disabled",
            message="AI is disabled. Document extraction, analytics, and exports remain available.",
        )
    if selected == "nvidia_nim":
        if not settings.nvidia_nim_free_access_confirmed:
            message = "NVIDIA NIM is unavailable until free access for the selected account, endpoint, and model is confirmed."
        elif not (settings.nvidia_nim_api_key or "").strip():
            message = "NVIDIA NIM is unavailable because NVIDIA_API_KEY is not configured."
        elif not (settings.nvidia_nim_model or "").strip():
            message = "NVIDIA NIM is unavailable because NVIDIA_MODEL was not explicitly configured."
        elif settings.nvidia_nim_api_base_url != NVIDIA_APPROVED_BASE_URL:
            message = "NVIDIA NIM is unavailable because NVIDIA_BASE_URL is not the approved endpoint."
        else:
            return AIProviderStatus(
                provider=selected, available=True, code="ready",
                message="NVIDIA NIM gates are satisfied; current provider pricing and remaining quota are not verified.",
            )
        return AIProviderStatus(provider=selected, available=False, code="ai_configuration_incomplete", message=message)
    if selected == "grok":
        if not settings.enable_grok or not settings.grok_free_api_access_confirmed:
            message = "Grok is disabled unless both explicit enablement and free API access confirmation are set."
        elif not (settings.xai_api_key or "").strip() or not (settings.xai_model or "").strip():
            message = "Grok is unavailable because XAI_API_KEY and XAI_MODEL must be configured."
        elif settings.xai_base_url and settings.xai_base_url != XAI_APPROVED_BASE_URL:
            message = "Grok is unavailable because XAI_BASE_URL is not the approved endpoint."
        else:
            return AIProviderStatus(
                provider=selected, available=True, code="ready",
                message="Grok gates are satisfied; current provider pricing and remaining quota are not verified.",
            )
        return AIProviderStatus(provider=selected, available=False, code="ai_configuration_incomplete", message=message)
    return AIProviderStatus(provider="none", available=False, code="ai_configuration_invalid", message="The configured AI provider is invalid.")


class AIService:
    """Select exactly one configured provider; never perform automatic fallback."""

    def __init__(self) -> None:
        self._slots = asyncio.Semaphore(settings.max_concurrent_ai_requests)

    def status(self) -> AIProviderStatus:
        return _configuration_status()

    @property
    def model_name(self) -> str | None:
        if settings.ai_provider == "nvidia_nim":
            return settings.nvidia_nim_model
        if settings.ai_provider == "grok":
            return settings.xai_model
        return None

    async def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        status = self.status()
        if not status.available:
            raise AIConfigurationError(status.message)
        serialized_payload = json.dumps(user_payload, ensure_ascii=False)
        if len(system_prompt) + len(serialized_payload) > settings.max_ai_input_chars:
            raise AIConfigurationError("The AI request exceeds the configured input size limit.")

        from backend.services.grok_provider import GrokProvider
        from backend.services.nvidia_provider import NVIDIAProvider

        adapter = NVIDIAProvider() if status.provider == "nvidia_nim" else GrokProvider()
        try:
            async with asyncio.timeout(settings.ai_request_timeout_seconds):
                async with self._slots:
                    return await adapter.complete_json(system_prompt=system_prompt, user_payload=user_payload)
        except TimeoutError as exc:
            raise AIProviderTimeout(f"{status.provider} took too long to respond.") from exc

    async def generate_structured_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        """Named interface for callers that prefer an explicit structured-generation method."""
        return await self.complete_json(system_prompt=system_prompt, user_payload=user_payload)


# Preserve the existing ``provider.complete_json(...)`` service contract.
provider = AIService()

# Preserve the structure facade's public provider class import.
from backend.services.nvidia_provider import NVIDIAProvider


__all__ = [
    "AIAuthenticationError", "AIBillingError", "AIConfigurationError", "AIInvalidResponse",
    "AIModelUnavailable", "AIProviderError", "AIProviderStatus", "AIProviderTimeout",
    "AIProviderUnavailable", "AIRateLimitError", "AIQuotaError", "AIService", "NVIDIAProvider", "provider",
]
