import asyncio

import httpx
import pytest
from pydantic import ValidationError

from backend.config import NVIDIA_APPROVED_BASE_URL, Settings, settings
from backend.services import ai_provider, ai_service
from backend.services import chat_service, summary_service
from backend.services.ai_service import (
    AIBillingError,
    AIConfigurationError,
    AIInvalidResponse,
    AIAuthenticationError,
    AIModelUnavailable,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIQuotaError,
    AIRateLimitError,
    parse_structured_response,
    provider,
)
from backend.services import grok_provider
from backend.services.grok_provider import GrokProvider
from backend.services.nvidia_provider import NVIDIAProvider


def _enable_nvidia(monkeypatch):
    monkeypatch.setattr(settings, "allow_paid_apis", False)
    monkeypatch.setattr(settings, "ai_provider", "nvidia_nim")
    monkeypatch.setattr(settings, "nvidia_nim_free_access_confirmed", True)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_nim_model", "test-model")
    monkeypatch.setattr(settings, "nvidia_nim_api_base_url", NVIDIA_APPROVED_BASE_URL)


def _enable_grok(monkeypatch):
    monkeypatch.setattr(settings, "allow_paid_apis", False)
    monkeypatch.setattr(settings, "ai_provider", "grok")
    monkeypatch.setattr(settings, "enable_grok", True)
    monkeypatch.setattr(settings, "grok_free_api_access_confirmed", True)
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    monkeypatch.setattr(settings, "xai_model", "test-grok-model")
    monkeypatch.setattr(settings, "xai_base_url", None)


def test_fresh_settings_are_free_only_and_ai_off_by_default():
    fresh = Settings(_env_file=None, _env_prefix="TEDDY_PHASE2_UNUSED_")
    assert fresh.ai_provider == "none"
    assert fresh.allow_paid_apis is False
    assert fresh.nvidia_nim_api_key is None
    assert fresh.nvidia_nim_model is None
    assert fresh.enable_grok is False
    assert fresh.grok_free_api_access_confirmed is False
    assert fresh.xai_api_key is None
    assert fresh.ai_request_timeout_seconds == 30
    assert fresh.ai_max_retries == 1
    assert fresh.agent_max_steps == 8


def test_default_provider_is_disabled_and_makes_no_external_call(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "none")
    monkeypatch.setattr(settings, "allow_paid_apis", False)
    calls = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: calls.append("called"))

    status = provider.status()
    with pytest.raises(AIConfigurationError, match="AI is disabled"):
        asyncio.run(provider.complete_json(system_prompt="system", user_payload={"q": "x"}))

    assert status.available is False
    assert status.code == "ai_disabled"
    assert calls == []


def test_paid_access_is_blocked_even_if_runtime_setting_is_mutated(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "nvidia_nim")
    monkeypatch.setattr(settings, "allow_paid_apis", True)
    with pytest.raises(AIConfigurationError, match="Paid API usage is disabled"):
        asyncio.run(provider.complete_json(system_prompt="system", user_payload={}))


def test_invalid_paid_or_provider_combinations_are_rejected_during_settings_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allow_paid_apis=True)
    with pytest.raises(ValidationError, match="NVIDIA_NIM_FREE_ACCESS_CONFIRMED"):
        Settings(_env_file=None, ai_provider="nvidia_nim")
    with pytest.raises(ValidationError, match="ENABLE_GROK"):
        Settings(_env_file=None, ai_provider="grok")


def test_nvidia_requires_every_explicit_gate_and_configuration(monkeypatch):
    _enable_nvidia(monkeypatch)
    for name, value in [
        ("nvidia_nim_free_access_confirmed", False),
        ("nvidia_nim_api_key", ""),
        ("nvidia_nim_model", None),
        ("nvidia_nim_api_base_url", "https://unexpected.example/v1"),
    ]:
        monkeypatch.setattr(settings, name, value)
        assert provider.status().available is False
        with pytest.raises(AIConfigurationError):
            asyncio.run(provider.complete_json(system_prompt="system", user_payload={}))
    monkeypatch.setattr(settings, "nvidia_nim_free_access_confirmed", True)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_nim_model", "test-model")
    monkeypatch.setattr(settings, "nvidia_nim_api_base_url", NVIDIA_APPROVED_BASE_URL)
    assert provider.status().available is True


def test_grok_requires_both_opt_ins_and_complete_configuration(monkeypatch):
    _enable_grok(monkeypatch)
    for name, value in [
        ("enable_grok", False),
        ("grok_free_api_access_confirmed", False),
        ("xai_api_key", None),
        ("xai_model", None),
        ("xai_base_url", "https://unexpected.example/v1"),
    ]:
        monkeypatch.setattr(settings, name, value)
        assert provider.status().available is False
        with pytest.raises(AIConfigurationError):
            asyncio.run(provider.complete_json(system_prompt="system", user_payload={}))
    monkeypatch.setattr(settings, "enable_grok", True)
    monkeypatch.setattr(settings, "grok_free_api_access_confirmed", True)
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    monkeypatch.setattr(settings, "xai_model", "test-grok-model")
    monkeypatch.setattr(settings, "xai_base_url", None)
    assert provider.status().available is True


def test_no_fallback_on_billing_or_quota_response(monkeypatch):
    _enable_grok(monkeypatch)
    calls = []

    async def fake_post(**kwargs):
        calls.append(kwargs["provider_name"])
        return httpx.Response(
            402,
            json={"error": {"message": "secret/raw provider text", "code": "payment_required"}},
            request=httpx.Request("POST", "https://api.x.ai/v1/chat/completions"),
        )

    monkeypatch.setattr(grok_provider, "post_completion", fake_post)
    with pytest.raises(AIBillingError) as error:
        asyncio.run(provider.complete_json(system_prompt="system", user_payload={}))
    assert calls == ["Grok"]
    assert "secret/raw" not in str(error.value)

    with pytest.raises(AIQuotaError):
        parse_structured_response(
            httpx.Response(429, json={"error": {"code": "insufficient_quota"}}), "Grok",
        )


def test_timeout_is_normalized_without_leaking_details(monkeypatch):
    _enable_nvidia(monkeypatch)

    async def timeout(_self, **_kwargs):
        raise TimeoutError("private transport detail")

    monkeypatch.setattr("backend.services.nvidia_provider.NVIDIAProvider.complete_json", timeout)
    with pytest.raises(AIProviderTimeout) as error:
        asyncio.run(provider.complete_json(system_prompt="system", user_payload={}))
    assert "private transport detail" not in str(error.value)


def test_connect_retry_is_bounded_and_quota_response_is_not_retried(monkeypatch):
    attempts = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ConnectError("private network detail")
            return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(settings, "ai_max_retries", 1)
    response = asyncio.run(ai_service.post_completion(
        url=f"{NVIDIA_APPROVED_BASE_URL}/chat/completions",
        headers={}, body={}, provider_name="NVIDIA NIM",
    ))
    assert len(attempts) == 2
    with pytest.raises(AIQuotaError):
        parse_structured_response(response, "NVIDIA NIM")
    assert len(attempts) == 2


def test_post_helper_rejects_unapproved_endpoint_without_network(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: calls.append("called"))
    with pytest.raises(AIConfigurationError, match="endpoint is not approved"):
        asyncio.run(ai_service.post_completion(
            url="https://arbitrary.example/v1/chat/completions",
            headers={}, body={}, provider_name="NVIDIA NIM",
        ))
    assert calls == []


def test_rate_limit_response_has_no_retry_or_provider_switch(monkeypatch):
    _enable_nvidia(monkeypatch)
    attempts = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            attempts.append(1)
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(AIRateLimitError):
        asyncio.run(provider.complete_json(system_prompt="system", user_payload={"ok": True}))
    assert attempts == [1]
    assert settings.ai_provider == "nvidia_nim"


def test_existing_provider_imports_remain_compatible():
    from backend.services.ai_service import NVIDIAProvider as CanonicalNVIDIAProvider

    assert ai_provider.provider is ai_service.provider
    assert summary_service.provider is ai_service.provider
    assert chat_service.provider is ai_service.provider
    assert ai_provider.NVIDIAProvider.__name__ == "NVIDIAProvider"
    assert CanonicalNVIDIAProvider is ai_provider.NVIDIAProvider
    assert callable(ai_provider.provider.complete_json)


def test_provider_output_size_is_bounded():
    response = httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})
    assert parse_structured_response(response, "test") == {"ok": True}


def test_adapters_cannot_bypass_provider_selection_gate(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "none")
    monkeypatch.setattr(settings, "nvidia_nim_free_access_confirmed", True)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_nim_model", "test-model")
    monkeypatch.setattr(settings, "nvidia_nim_api_base_url", NVIDIA_APPROVED_BASE_URL)
    monkeypatch.setattr(settings, "enable_grok", True)
    monkeypatch.setattr(settings, "grok_free_api_access_confirmed", True)
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    monkeypatch.setattr(settings, "xai_model", "test-grok-model")
    calls = []
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kwargs: calls.append("called"))

    with pytest.raises(AIConfigurationError):
        asyncio.run(NVIDIAProvider().complete_json(system_prompt="system", user_payload={}))
    with pytest.raises(AIConfigurationError):
        asyncio.run(GrokProvider().complete_json(system_prompt="system", user_payload={}))
    assert calls == []


def test_provider_output_character_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "ai_max_output_chars", 5)
    response = httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})
    with pytest.raises(AIInvalidResponse, match="oversized"):
        parse_structured_response(response, "test")


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, AIAuthenticationError),
        (404, AIModelUnavailable),
        (500, AIProviderUnavailable),
    ],
)
def test_provider_http_errors_are_normalized_without_raw_response(status_code, expected_error):
    response = httpx.Response(
        status_code,
        json={"error": {"message": "private provider detail"}},
    )
    with pytest.raises(expected_error) as error:
        parse_structured_response(response, "NVIDIA NIM")
    assert "private provider detail" not in str(error.value)


def test_malformed_provider_response_is_normalized():
    response = httpx.Response(200, json={"choices": []})
    with pytest.raises(AIInvalidResponse, match="malformed") as error:
        parse_structured_response(response, "NVIDIA NIM")
    assert "choices" not in str(error.value)
