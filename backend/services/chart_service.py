"""Analytics facade; calculations remain implemented in ``backend.analytics``."""

from backend.analytics.data_profiler import profile_document, profile_tables

__all__ = ["profile_document", "profile_tables"]
