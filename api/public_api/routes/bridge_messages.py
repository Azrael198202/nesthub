from fastapi import APIRouter, Request
from api.public_api.services.bridge_service import BridgeService

router = APIRouter()

# GET /api/bridge/messages/{bridge_message_id}
@router.get("/messages/{bridge_message_id}")
async def get_message(request: Request, bridge_message_id: str):
    msg = request.app.state.bridge_service.get_message(bridge_message_id)
    if not msg:
        return {"error": "not found"}
    return msg.dict()
