
import base64
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request


router = APIRouter()
logger = logging.getLogger("api.public_api.routes.bridge_im")

def _verify_line_signature(body: bytes, signature: str | None) -> bool:
    import os

    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    if not channel_secret:
        return True
    if not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)

@router.post("/im/inbound")
async def im_inbound(request: Request, x_line_signature: str = Header(None)):
    logger.info("/im/inbound called, X-Line-Signature: %s", x_line_signature)
    body = await request.body()
    if not _verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="invalid LINE signature")

    data = await request.json()
    logger.info("/im/inbound payload: %s", data)

    results = []
    if "events" in data and data["events"]:
        for event in data["events"]:
            if event.get("type") != "message":
                continue
            if event.get("message", {}).get("type") != "text":
                continue
            source = event.get("source", {})
            external_user_id = source.get("userId", "unknown")
            external_chat_id = source.get("groupId") or source.get("roomId") or external_user_id
            external_message_id = event.get("message", {}).get("id", "unknown")
            text = event.get("message", {}).get("text", "")
            logger.info("Extracted LINE fields: userId=%s groupId=%s messageId=%s text=%s", external_user_id, external_chat_id, external_message_id, text)
            msg = request.app.state.bridge_service.create_message(
                "line", external_user_id, external_chat_id, external_message_id, text, event
            )
            if request.app.state.bridge_service.should_process_inline():
                result = await request.app.state.bridge_service.process_message(msg)
                status = request.app.state.bridge_service.get_message(msg.bridge_message_id).status
                reply = result.get("reply", "")
            else:
                result = {}
                status = "pending"
                reply = ""
            results.append({
                "bridge_message_id": msg.bridge_message_id,
                "status": status,
                "reply": reply,
            })
        if results:
            return {"ok": True, "processed": len(results), "results": results}
    logger.warning("/im/inbound received non-LINE or invalid payload: %s", data)
    return {"error": "not a valid LINE webhook"}
