from typing import List, Dict, Optional
from threading import Lock
from api.public_api.models.bridge_message import BridgeMessage

class MemoryStore:
    def __init__(self):
        self._messages: Dict[str, BridgeMessage] = {}
        self._lock = Lock()

    def add_message(self, msg: BridgeMessage):
        with self._lock:
            self._messages[msg.bridge_message_id] = msg

    def get_pending(self) -> List[BridgeMessage]:
        with self._lock:
            return [m for m in self._messages.values() if m.status == "pending"]

    def claim_message(self, bridge_message_id: str) -> Optional[BridgeMessage]:
        with self._lock:
            msg = self._messages.get(bridge_message_id)
            if msg and msg.status == "pending":
                msg.status = "claimed"
                from datetime import datetime
                msg.claimed_at = datetime.utcnow()
                return msg
            return None

    def complete_message(self, bridge_message_id: str, result: dict):
        with self._lock:
            msg = self._messages.get(bridge_message_id)
            if msg and msg.status == "claimed":
                msg.status = "completed"
                from datetime import datetime
                msg.completed_at = datetime.utcnow()
                msg.result = result
                return msg
            return None

    def get_message(self, bridge_message_id: str) -> Optional[BridgeMessage]:
        with self._lock:
            return self._messages.get(bridge_message_id)
