"""Compatibility facade for the canonical AI service and NVIDIA adapter."""

# Keep ``httpx`` exported because older tests/integrations patch this module's
# AsyncClient. It is the same module object used by ai_service.post_completion.
import httpx

from backend.services.ai_service import (
    AIAuthenticationError,
    AIBillingError,
    AIConfigurationError,
    AIInvalidResponse,
    AIModelUnavailable,
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIRateLimitError,
    AIQuotaError,
    provider,
)
from backend.services.nvidia_provider import NVIDIAProvider

__all__ = [
    "AIAuthenticationError", "AIBillingError", "AIConfigurationError", "AIInvalidResponse",
    "AIModelUnavailable", "AIProviderError", "AIProviderTimeout", "AIProviderUnavailable",
    "AIRateLimitError", "AIQuotaError", "NVIDIAProvider", "httpx", "provider",
]
