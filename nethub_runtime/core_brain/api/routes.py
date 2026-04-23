from __future__ import annotations

from fastapi import APIRouter

from nethub_runtime.core_brain.api.chat import router as chat_router
from nethub_runtime.core_brain.api.health import router as health_router

router = APIRouter()
router.include_router(health_router, prefix="/api")
router.include_router(chat_router, prefix="/api")
