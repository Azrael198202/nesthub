
from fastapi import APIRouter, Request, Header, HTTPException
from api.public_api.services.bridge_service import BridgeService
import httpx
import os
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

router = APIRouter()

# GET /api/bridge/hub/pending
@router.get("/hub/pending")
async def hub_pending(request: Request, authorization: str = Header(None)):
    # Simple token check (in prod, use config/env)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # TODO: check token value
    pending = request.app.state.bridge_service.get_pending()
    return [m.dict() for m in pending]

# POST /api/bridge/hub/claim
@router.post("/hub/claim")
async def hub_claim(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await request.json()
    bridge_message_id = data.get("bridge_message_id")
    msg = request.app.state.bridge_service.claim_message(bridge_message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or not pending")
    return msg.dict()

# POST /api/bridge/hub/result

@router.post("/hub/result")
async def hub_result(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await request.json()
    bridge_message_id = data.get("bridge_message_id")
    result = data.get("result", {})
    msg = request.app.state.bridge_service.complete_message(bridge_message_id, result)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or not claimed")

    # 如果是 LINE 消息，主动推送
    if msg.source_im == "line" and msg.external_user_id != "unknown":
        push_text = result.get("reply", "收到您的消息！")
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
