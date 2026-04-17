import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from api.public_api.models.bridge_message import BridgeMessage
from api.public_api.storage.memory_store import MemoryStore
from api.public_api.storage.temp_file_store import TempFileStore

class BridgeService:
    def __init__(self, store: MemoryStore, temp_file_store: TempFileStore):
        self.store = store
        self.temp_file_store = temp_file_store

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

    def should_process_inline(self) -> bool:
        handle_url = os.getenv("NESTHUB_CORE_HANDLE_URL", "").strip()
        inline_flag = os.getenv("NESTHUB_PUBLIC_API_PROCESS_INLINE", "").strip().lower()
        if inline_flag in {"1", "true", "yes", "on"}:
            return True
        return bool(handle_url)

    async def _invoke_nesthub(self, msg: BridgeMessage) -> dict[str, Any]:
        handle_url = os.getenv("NESTHUB_CORE_HANDLE_URL", "").strip()
        if not handle_url:
            return {"reply": "NestHub core handle url is not configured."}
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

    def build_public_download_url(self, file_id: str, file_name: str, base_url: str | None = None) -> str:
        root = (base_url or os.getenv("NESTHUB_PUBLIC_API_BASE_URL") or "").strip().rstrip("/")
        path = f"/api/temp-files/{file_id}/{file_name}"
        return f"{root}{path}" if root else path

    def stage_artifact_bytes(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        base_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.temp_file_store.save_bytes(
            file_name=file_name,
            content=content,
            content_type=content_type,
            metadata=metadata,
        )
        return {
            "file_id": record.file_id,
            "file_name": record.file_name,
            "content_type": record.content_type,
            "expires_at": record.expires_at.isoformat(),
            "download_url": self.build_public_download_url(record.file_id, record.file_name, base_url=base_url),
            "metadata": record.metadata,
        }

    def stage_local_result_artifacts(self, artifacts: list[dict[str, Any]], base_url: str | None = None) -> list[dict[str, Any]]:
        downloads: list[dict[str, Any]] = []
        for artifact in artifacts or []:
            path_value = str(artifact.get("path") or "").strip()
            if not path_value:
                continue
            path = Path(path_value)
            if not path.exists() or not path.is_file():
                continue
            downloads.append(
                self.stage_artifact_bytes(
                    file_name=str(artifact.get("name") or path.name),
                    content=path.read_bytes(),
                    base_url=base_url,
                    metadata={
                        "artifact_type": artifact.get("artifact_type", "file"),
                        "artifact_id": artifact.get("artifact_id", path.stem),
                        "source": artifact.get("source", "runtime"),
                    },
                )
            )
        return downloads

    def _extract_reply_text(self, result: dict[str, Any]) -> str:
        execution_result = result.get("execution_result") or {}
        if execution_result.get("execution_type") == "agent":
            agent_result = execution_result.get("agent_result") or {}
            final_answer = str(agent_result.get("final_answer") or "").strip()
            if final_answer:
                return final_answer

        final_output = execution_result.get("final_output") or {}
        for key in ("manage_information_agent", "query_information_knowledge", "file_read", "file_generate", "generate_workflow_artifact", "single_step"):
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
        reply_text = self._compose_line_reply_text(result)[:5000]
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

    def _compose_line_reply_text(self, result: dict[str, Any]) -> str:
        reply_text = str(result.get("reply") or "收到您的消息！").strip()
        downloads = result.get("downloads") or []
        if not isinstance(downloads, list) or not downloads:
            return reply_text or "收到您的消息！"
        lines = [reply_text or "已为您准备下载链接：", ""]
        for item in downloads:
            url = str(item.get("download_url") or "").strip()
            name = str(item.get("file_name") or "download").strip()
            if url:
                lines.append(f"{name}: {url}")
        return "\n".join(line for line in lines if line).strip()
