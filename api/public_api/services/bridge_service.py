import uuid
from api.public_api.models.bridge_message import BridgeMessage
from api.public_api.storage.memory_store import MemoryStore

class BridgeService:
    def __init__(self, store: MemoryStore):
        self.store = store

    def create_message(self, source_im: str, external_user_id: str, external_chat_id: str, external_message_id: str, text: str, raw_payload: dict) -> BridgeMessage:
        msg = BridgeMessage(
            bridge_message_id=str(uuid.uuid4()),
            source_im=source_im,
            external_user_id=external_user_id,
            external_chat_id=external_chat_id,
            external_message_id=external_message_id,
            text=text,
            raw_payload=raw_payload,
        )
        self.store.add_message(msg)
        return msg

    def get_pending(self):
        return self.store.get_pending()

    def claim_message(self, bridge_message_id: str):
        return self.store.claim_message(bridge_message_id)

    def complete_message(self, bridge_message_id: str, result: dict):
        return self.store.complete_message(bridge_message_id, result)

    def get_message(self, bridge_message_id: str):
        return self.store.get_message(bridge_message_id)
