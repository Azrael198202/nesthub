from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from nethub_runtime.core.services.core_engine import AICore

router = APIRouter()


class HandleRequest(BaseModel):
    input_text: str
    context: dict[str, Any] = Field(default_factory=dict)
    output_format: str = "dict"


class HandleResponse(BaseModel):
    result: Any


class ReloadPluginsResponse(BaseModel):
    result: dict[str, Any]

core_engine = AICore()

@router.post("/handle")
async def handle(payload: HandleRequest) -> HandleResponse:
    result = await core_engine.handle(payload.input_text, payload.context, payload.output_format)
    return HandleResponse(result=result)


@router.post("/admin/reload-plugins")
async def reload_plugins() -> ReloadPluginsResponse:
    result = core_engine.reload_plugins()
    return ReloadPluginsResponse(result=result)
