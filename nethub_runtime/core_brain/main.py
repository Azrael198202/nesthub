from __future__ import annotations

from fastapi import FastAPI

from nethub_runtime.core_brain.api.routes import router as core_brain_router


def create_app() -> FastAPI:
    app = FastAPI(title="core-brain")
    app.include_router(core_brain_router)
    return app


app = create_app()
