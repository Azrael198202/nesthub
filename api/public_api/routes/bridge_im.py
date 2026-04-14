from fastapi import APIRouter, Request
from api.public_api.services.bridge_service import BridgeService

router = APIRouter()

# POST /api/bridge/im/inbound
@router.post("/im/inbound")
async def im_inbound(request: Request):
    data = await request.json()
    # For demo, assume LINE: extract userId, groupId, text, messageId
    source_im = "line"
    external_user_id = data.get("userId", "unknown")
    external_chat_id = data.get("groupId", "unknown")
    external_message_id = data.get("messageId", "unknown")
    text = data.get("text", "")
    raw_payload = data
    msg = request.app.state.bridge_service.create_message(
        source_im, external_user_id, external_chat_id, external_message_id, text, raw_payload
    )
    return {"bridge_message_id": msg.bridge_message_id, "status": msg.status}
