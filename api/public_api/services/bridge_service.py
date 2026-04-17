import os
import uuid
from typing import Any

import httpx

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

    async def process_message(self, msg: BridgeMessage) -> dict[str, Any]:
        claimed = self.store.claim_message(msg.bridge_message_id)
        if claimed is None:
            existing = self.store.get_message(msg.bridge_message_id)
            if existing and existing.result:
                return existing.result
            return {"reply": "Message is no longer pending."}

        result = await self._invoke_nesthub(claimed)
        self.store.complete_message(claimed.bridge_message_id, result)
        if claimed.source_im == "line":
            await self._deliver_line_response(claimed, result)
        return result

    async def _invoke_nesthub(self, msg: BridgeMessage) -> dict[str, Any]:
        handle_url = os.getenv("NESTHUB_CORE_HANDLE_URL", "http://127.0.0.1:8000/core/handle").strip()
        payload = {
            "input_text": msg.text,
            "context": {
                "metadata": {
                    "source_im": msg.source_im,
                    "external_user_id": msg.external_user_id,
                    "external_chat_id": msg.external_chat_id,
                    "external_message_id": msg.external_message_id,
                    "bridge_message_id": msg.bridge_message_id,
                }
            },
            "output_format": "dict",
            "use_langraph": True,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(handle_url, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {"reply": f"NestHub bridge error: {exc}"}

        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            return {"reply": "NestHub returned an invalid response."}

        reply = self._extract_reply_text(result)
        return {
            "reply": reply,
            "result": result,
            "artifacts": result.get("artifacts", []),
        }

    def _extract_reply_text(self, result: dict[str, Any]) -> str:
        execution_result = result.get("execution_result") or {}
        if execution_result.get("execution_type") == "agent":
            agent_result = execution_result.get("agent_result") or {}
            final_answer = str(agent_result.get("final_answer") or "").strip()
            if final_answer:
                return final_answer

        final_output = execution_result.get("final_output") or {}
        for key in ("manage_information_agent", "query_information_knowledge", "file_generate", "generate_workflow_artifact", "single_step"):
            payload = final_output.get(key) or {}
            for field in ("message", "answer", "summary", "artifact_path"):
                value = str(payload.get(field) or "").strip()
                if value:
                    return f"Generated artifact: {value}" if field == "artifact_path" else value

        task = result.get("task") or {}
        return f"NestHub completed {task.get('intent', 'the request')}."

    async def _deliver_line_response(self, msg: BridgeMessage, result: dict[str, Any]) -> None:
        access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        if not access_token:
            return

        event = msg.raw_payload or {}
        reply_text = str(result.get("reply") or "收到您的消息！")[:5000]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            reply_token = str(event.get("replyToken") or "").strip()
            if reply_token:
                response = await client.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers=headers,
                    json={
                        "replyToken": reply_token,
                        "messages": [{"type": "text", "text": reply_text}],
                    },
                )
                if response.is_success:
                    return

            if msg.external_user_id and msg.external_user_id != "unknown":
                await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers=headers,
                    json={
                        "to": msg.external_user_id,
                        "messages": [{"type": "text", "text": reply_text}],
                    },
                )
