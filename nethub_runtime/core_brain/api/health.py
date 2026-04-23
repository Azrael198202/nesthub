from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/core-brain/health")
async def core_brain_health() -> dict[str, str]:
    return {"status": "ok", "service": "core-brain"}
