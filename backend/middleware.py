"""Request limits applied before FastAPI parses multipart upload bodies."""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from backend.config import settings


ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]


class _BodyLimitExceeded(Exception):
    pass


class UploadRequestLimitMiddleware:
    """Cap multipart request bytes, including requests without Content-Length."""

    def __init__(self, app, *, multipart_overhead_bytes: int = 1024 * 1024):
        self.app = app
        self.multipart_overhead_bytes = multipart_overhead_bytes

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        is_upload = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/api/v1/documents/upload"
        )
        if not is_upload:
            await self.app(scope, receive, send)
            return

        limit = settings.max_upload_size_mb * 1024 * 1024 + self.multipart_overhead_bytes
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        declared_length = headers.get(b"content-length")
        if declared_length:
            try:
                if int(declared_length) > limit:
                    await JSONResponse(
                        {"detail": f"The upload request exceeds the {settings.max_upload_size_mb} MB file limit."},
                        status_code=413,
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyLimitExceeded:
            await JSONResponse(
                {"detail": f"The upload request exceeds the {settings.max_upload_size_mb} MB file limit."},
                status_code=413,
            )(scope, receive, send)
