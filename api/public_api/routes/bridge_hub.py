from __future__ import annotations

import base64

from fastapi import APIRouter, Request, Header, HTTPException
import httpx
import os
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

router = APIRouter()


def _require_bearer_token(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _public_base_url(request: Request) -> str:
    configured = os.getenv("NESTHUB_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")

# GET /api/bridge/hub/pending
@router.get("/hub/pending")
async def hub_pending(request: Request, authorization: str = Header(None)):
    _require_bearer_token(authorization)
    # TODO: check token value
    pending = request.app.state.bridge_service.get_pending()
    return [m.dict() for m in pending]

# POST /api/bridge/hub/claim
@router.post("/hub/claim")
async def hub_claim(request: Request, authorization: str = Header(None)):
    _require_bearer_token(authorization)
    data = await request.json()
    bridge_message_id = data.get("bridge_message_id")
    msg = request.app.state.bridge_service.claim_message(bridge_message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or not pending")
    return msg.dict()

@router.post("/hub/artifact")
async def hub_artifact_upload(request: Request, authorization: str = Header(None)):
    _require_bearer_token(authorization)
    data = await request.json()
    content_b64 = str(data.get("content_base64") or "").strip()
    file_name = str(data.get("file_name") or "download.bin").strip()
    if not content_b64:
        raise HTTPException(status_code=400, detail="content_base64 is required")
    try:
        content = base64.b64decode(content_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid content_base64: {exc}") from exc
    staged = request.app.state.bridge_service.stage_artifact_bytes(
        file_name=file_name,
        content=content,
        content_type=str(data.get("content_type") or "").strip() or None,
        base_url=_public_base_url(request),
        metadata={
            "artifact_type": data.get("artifact_type", "file"),
            "artifact_id": data.get("artifact_id", ""),
            "source": data.get("source", "bridge_upload"),
        },
    )
    return {"ok": True, "download": staged}


# POST /api/bridge/hub/result

@router.post("/hub/result")
async def hub_result(request: Request, authorization: str = Header(None)):
    _require_bearer_token(authorization)
    data = await request.json()
    bridge_message_id = data.get("bridge_message_id")
    result = data.get("result", {})
    if isinstance(result, dict) and not result.get("downloads") and result.get("artifacts"):
        result["downloads"] = request.app.state.bridge_service.stage_local_result_artifacts(
            result.get("artifacts") or [],
            base_url=_public_base_url(request),
        )
    msg = request.app.state.bridge_service.complete_message(bridge_message_id, result)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or not claimed")

    # 如果是 LINE 消息，主动推送
    if msg.source_im == "line" and msg.external_user_id != "unknown":
        push_text = request.app.state.bridge_service._compose_line_reply_text(result)
        if LINE_CHANNEL_ACCESS_TOKEN:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={
                        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "to": msg.external_user_id,
                        "messages": [{"type": "text", "text": push_text}]
                    }
                )
        else:
            print("[WARN] LINE_CHANNEL_ACCESS_TOKEN 未设置，无法主动推送 LINE 消息。")

    return msg.dict()
