"""Citation verification facade used by summaries and document chat."""

from backend.services.insight_service import validate_evidence

__all__ = ["validate_evidence"]
