from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nethub_runtime.core.services.core_engine import AICore

router = APIRouter()


class HandleRequest(BaseModel):
    input_text: str
    context: dict[str, Any] = Field(default_factory=dict)
    output_format: str = "dict"
    use_langraph: bool = True


class HandleResponse(BaseModel):
    result: Any


class ReloadPluginsResponse(BaseModel):
    result: dict[str, Any]


class SemanticMemoryResponse(BaseModel):
    result: dict[str, Any]


class RuntimeMemoryResponse(BaseModel):
    result: dict[str, Any]

core_engine = AICore()

@router.post("/handle")
async def handle(payload: HandleRequest) -> HandleResponse:
    result = await core_engine.handle(
        payload.input_text,
        payload.context,
        payload.output_format,
        payload.use_langraph,
    )
    return HandleResponse(result=result)


@router.post("/handle/stream")
async def handle_stream(payload: HandleRequest) -> StreamingResponse:
    """Server-Sent Events stream of pipeline progress events.

    Each event is a JSON line prefixed with ``data: ``, followed by two
    newlines (standard SSE format).  Clients can consume with ``EventSource``
    or any SSE-capable HTTP client.

    Event types mirror ``AICore.handle_stream()``::

        intent_analyzed  – intent resolved
        workflow_planned – step list known
        step_completed   – one workflow step finished
        repair_started   – self-repair iteration started
        final            – full result payload
        lifecycle_end    – stream finished
        lifecycle_error  – unhandled error
    """
    async def _sse_generator() -> AsyncGenerator[str, None]:
        async for event in core_engine.handle_stream(
            payload.input_text,
            payload.context,
            payload.output_format,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/admin/reload-plugins")
async def reload_plugins() -> ReloadPluginsResponse:
    result = core_engine.reload_plugins()
    return ReloadPluginsResponse(result=result)


@router.get("/admin/semantic-memory")
async def get_semantic_memory(
    policy_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> SemanticMemoryResponse:
    return SemanticMemoryResponse(result=core_engine.inspect_semantic_memory(policy_key=policy_key, status=status))


@router.get("/admin/runtime-memory")
async def get_runtime_memory(
    query: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    top_k: int = Query(default=5, ge=1, le=20),
) -> RuntimeMemoryResponse:
    return RuntimeMemoryResponse(
        result=core_engine.inspect_runtime_memory(query=query, namespace=namespace, top_k=top_k)
    )
