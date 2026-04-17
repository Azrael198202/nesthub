from typing import Optional, Dict, Any
from datetime import UTC, datetime
from pydantic import BaseModel, Field

class BridgeMessage(BaseModel):
    bridge_message_id: str
    source_im: str
    external_user_id: str
    external_chat_id: str
    external_message_id: str
    text: str
    raw_payload: Dict[str, Any]
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    failed: bool = False
