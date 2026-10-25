import asyncio

from backend.config import settings
from backend.middleware import UploadRequestLimitMiddleware


def test_declared_large_upload_request_is_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    called = False

    async def app(_scope, _receive, _send):
        nonlocal called
        called = True

    messages = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/documents/upload",
            "headers": [(b"content-length", str(2 * 1024 * 1024 + 1).encode())],
    }
    asyncio.run(UploadRequestLimitMiddleware(app)(scope, receive, send))

    assert not called
    assert messages[0]["status"] == 413
    assert b"upload request exceeds" in messages[1]["body"].lower()


def test_chunked_large_upload_request_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)

    async def app(_scope, receive, _send):
        while (message := await receive()).get("type") == "http.request":
            pass

    messages = []
    bodies = iter([
        {"type": "http.request", "body": b"x" * (1024 * 1024 + 1)},
        {"type": "http.request", "body": b"x" * (1024 * 1024 + 1)},
    ])

    async def receive():
        return next(bodies)

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/v1/documents/upload", "headers": []}
    asyncio.run(UploadRequestLimitMiddleware(app)(scope, receive, send))

    assert messages[0]["status"] == 413
