from __future__ import annotations

from fastapi import APIRouter, Depends

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.engine import CoreBrainEngine

router = APIRouter()
_ENGINE = CoreBrainEngine()


def get_engine() -> CoreBrainEngine:
    return _ENGINE


@router.post("/core-brain/chat")
async def core_brain_chat(req: ChatRequest, engine: CoreBrainEngine = Depends(get_engine)) -> dict:
    return await engine.facade.handle_chat(req)


@router.post("/core/chat")
async def compat_core_chat(req: ChatRequest, engine: CoreBrainEngine = Depends(get_engine)) -> dict:
    return await engine.facade.handle_chat(req)
