from __future__ import annotations

from fastapi import FastAPI

from nethub_runtime.core_brain.brain.api.routers.chat import router as chat_router
from nethub_runtime.core_brain.brain.api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="core-brain")
    app.include_router(health_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    return app


app = create_app()
