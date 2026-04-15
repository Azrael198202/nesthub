

from fastapi import APIRouter, Request, Header, HTTPException
from api.public_api.services.bridge_service import BridgeService
import httpx
import os
import logging


router = APIRouter()
logger = logging.getLogger("api.public_api.routes.bridge_im")

# POST /api/bridge/im/inbound

# LINE channel access token (set as env var or config)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")



@router.post("/im/inbound")
async def im_inbound(request: Request, x_line_signature: str = Header(None)):
    logger.info("/im/inbound called, X-Line-Signature: %s", x_line_signature)
    data = await request.json()
    logger.info("/im/inbound payload: %s", data)

    # 只处理 LINE 消息
    if "events" in data and data["events"]:
        event = data["events"][0]
        source = event.get("source", {})
        external_user_id = source.get("userId", "unknown")
        external_chat_id = source.get("groupId", "unknown")
        external_message_id = event.get("message", {}).get("id", "unknown")
        text = event.get("message", {}).get("text", "")
        logger.info("Extracted LINE fields: userId=%s groupId=%s messageId=%s text=%s", external_user_id, external_chat_id, external_message_id, text)
        raw_payload = data
        msg = request.app.state.bridge_service.create_message(
            "line", external_user_id, external_chat_id, external_message_id, text, raw_payload
        )
        logger.info("Created bridge message: %s", msg)
        return {"bridge_message_id": msg.bridge_message_id, "status": msg.status}
    logger.warning("/im/inbound received non-LINE or invalid payload: %s", data)
    return {"error": "not a valid LINE webhook"}
