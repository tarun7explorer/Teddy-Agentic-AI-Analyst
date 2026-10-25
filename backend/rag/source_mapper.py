"""Source-citation verification facade shared by summary and chat responses."""

from backend.services.insight_service import validate_evidence

__all__ = ["validate_evidence"]
