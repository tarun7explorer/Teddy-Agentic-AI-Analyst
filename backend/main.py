"""FastAPI application and static frontend entry point for Teddy."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.api.upload import router as documents_router
from backend.config import settings
from backend.middleware import UploadRequestLimitMiddleware


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

app = FastAPI(
    title=settings.app_name,
    description="Document extraction, source-grounded analysis, analytics, chat, and exports.",
    version="0.1.0",
    debug=settings.debug,
)


app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(health_router)
app.add_middleware(UploadRequestLimitMiddleware)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
