"""Document API router.

The current MVP keeps upload, result, analysis, and export routes together in
``documents.py`` because they share one document-store dependency. This module
is the structure-defined router entry point and re-exports that same router.
"""

from backend.api.documents import router

__all__ = ["router"]
