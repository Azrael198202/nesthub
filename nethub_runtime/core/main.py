"""
AI Core main entrypoint. Instantiates the core engine and exposes FastAPI app.
"""
from fastapi import FastAPI

from nethub_runtime.core.routers.core_api import router as core_router

app = FastAPI(title="NestHub AI Core")
app.include_router(core_router, prefix="/core")
