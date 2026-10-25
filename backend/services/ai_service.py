"""Structure-compatible facade for the configured NVIDIA NIM provider."""

from backend.services.ai_provider import (
    AIAuthenticationError,
    AIConfigurationError,
    AIInvalidResponse,
    AIModelUnavailable,
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIRateLimitError,
    NVIDIAProvider,
    provider,
)

__all__ = [
    "AIAuthenticationError", "AIConfigurationError", "AIInvalidResponse",
    "AIModelUnavailable", "AIProviderError", "AIProviderTimeout",
    "AIProviderUnavailable", "AIRateLimitError", "NVIDIAProvider", "provider",
]
