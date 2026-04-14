
from fastapi import APIRouter, Request, Header, HTTPException
from api.public_api.services.bridge_service import BridgeService
import httpx
import os

router = APIRouter()

# POST /api/bridge/im/inbound

# LINE channel access token (set as env var or config)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")


@router.post("/im/inbound")
async def im_inbound(request: Request, x_line_signature: str = Header(None)):
    # 只处理 LINE 消息（必须有 X-Line-Signature）
    # if not x_line_signature:
    #     return {"error": "Not a LINE webhook, ignored."}

    data = await request.json()
    source_im = "line"
    external_user_id = data.get("userId", "unknown")
    external_chat_id = data.get("groupId", "unknown")
    external_message_id = data.get("messageId", "unknown")
    text = data.get("text", "")
    raw_payload = data
    msg = request.app.state.bridge_service.create_message(
        source_im, external_user_id, external_chat_id, external_message_id, text, raw_payload
    )

    # 收到回复后通过 LINE 官方 API 回复
    if "replyToken" in data:
        reply_token = data["replyToken"]
        reply_text = "收到您的消息！"
        if "result" in data and isinstance(data["result"], dict):
            reply_text = data["result"].get("reply", reply_text)
        if LINE_CHANNEL_ACCESS_TOKEN:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={
                        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "replyToken": reply_token,
                        "messages": [{"type": "text", "text": reply_text}]
                    }
                )
        else:
            print("[WARN] LINE_CHANNEL_ACCESS_TOKEN 未设置，无法自动回复 LINE。")

    return {"bridge_message_id": msg.bridge_message_id, "status": msg.status}
