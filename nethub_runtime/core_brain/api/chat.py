from __future__ import annotations

from fastapi import APIRouter, Depends

from nethub_runtime.core_brain.contracts.request import CoreBrainRequest
from nethub_runtime.core_brain.contracts.response import CoreBrainResponse
from nethub_runtime.core_brain.engine import CoreBrainEngine

router = APIRouter()
_ENGINE = CoreBrainEngine()


def get_engine() -> CoreBrainEngine:
    return _ENGINE


async def _run(req: CoreBrainRequest, engine: CoreBrainEngine) -> dict:
    result = await engine.handle(
        req.message,
        context={
            "session_id": req.session_id,
            "task_id": req.task_id,
            "metadata": {"user_id": req.user_id, "allow_external": req.allow_external, **req.metadata},
        },
        fmt="dict",
    )
    payload = {
        **result,
        "artifacts": list(result.get("artifacts") or []),
    }
    return CoreBrainResponse.model_validate(payload).model_dump(mode="python")


@router.post("/chat")
async def chat(req: CoreBrainRequest, engine: CoreBrainEngine = Depends(get_engine)) -> dict:
    return await _run(req, engine)


@router.post("/core-brain/chat")
async def core_brain_chat(req: CoreBrainRequest, engine: CoreBrainEngine = Depends(get_engine)) -> dict:
    return await _run(req, engine)


@router.post("/core/chat")
async def compat_core_chat(req: CoreBrainRequest, engine: CoreBrainEngine = Depends(get_engine)) -> dict:
    return await _run(req, engine)
