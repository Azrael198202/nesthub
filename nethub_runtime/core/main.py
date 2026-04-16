"""
AI Core main entrypoint. Instantiates the core engine and exposes FastAPI app.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nethub_runtime.core.routers.core_api import router as core_router

app = FastAPI(title="NestHub AI Core")
app.include_router(core_router, prefix="/core")

SEMANTIC_MEMORY_DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "examples" / "semantic-memory-dashboard"
if SEMANTIC_MEMORY_DASHBOARD_DIR.exists():
	app.mount(
		"/examples/semantic-memory-dashboard",
		StaticFiles(directory=str(SEMANTIC_MEMORY_DASHBOARD_DIR), html=True),
		name="semantic-memory-dashboard",
	)
