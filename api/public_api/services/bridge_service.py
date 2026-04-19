import json
import os
import uuid
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from api.public_api.models.bridge_message import BridgeMessage
from api.public_api.storage.memory_store import MemoryStore
from api.public_api.storage.temp_file_store import TempFileStore
from nethub_runtime.core.services.progress_formatter import ProgressFormatter

class BridgeService:
    def __init__(self, store: MemoryStore, temp_file_store: TempFileStore):
        self.store = store
        self.temp_file_store = temp_file_store

    def create_message(self, source_im: str, external_user_id: str, external_chat_id: str, external_message_id: str, text: str, raw_payload: dict, *, attachments: list[dict] | None = None) -> BridgeMessage:
        msg = BridgeMessage(
            bridge_message_id=str(uuid.uuid4()),
            source_im=source_im,
            external_user_id=external_user_id,
            external_chat_id=external_chat_id,
            external_message_id=external_message_id,
            text=text,
            raw_payload=raw_payload,
            attachments=attachments or [],
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

    async def process_message(self, msg: BridgeMessage, *, base_url: str | None = None) -> dict[str, Any]:
        claimed = self.store.claim_message(msg.bridge_message_id)
        if claimed is None:
            existing = self.store.get_message(msg.bridge_message_id)
            if existing and existing.result:
                return existing.result
            return {"reply": "Message is no longer pending."}

        # Use streaming path for LINE so we can push incremental progress
        if claimed.source_im == "line" and claimed.external_user_id:
            result = await self._invoke_nesthub_stream(claimed, base_url=base_url)
        else:
            result = await self._invoke_nesthub(claimed, base_url=base_url)

        self.store.complete_message(claimed.bridge_message_id, result)
        if claimed.source_im == "line" and not (claimed.source_im == "line" and claimed.external_user_id):
            # Non-streaming LINE fallback — deliver final response
            await self._deliver_line_response(claimed, result)
        return result

    @staticmethod
    def _nesthub_base_url() -> str:
        return os.getenv("NETHUB_LLM_ROUTER_ENDPOINT", "").strip().rstrip("/")

    def should_process_inline(self) -> bool:
        inline_flag = os.getenv("NESTHUB_PUBLIC_API_PROCESS_INLINE", "").strip().lower()
        if inline_flag in {"1", "true", "yes", "on"}:
            return True
        return bool(self._nesthub_base_url())

    async def _invoke_nesthub(self, msg: BridgeMessage, *, base_url: str | None = None) -> dict[str, Any]:
        base = self._nesthub_base_url()
        if not base:
            return {"reply": "NestHub core handle url is not configured."}
        handle_url = f"{base}/handle"
        payload = {
            "input_text": msg.text,
            "context": {
                "metadata": {
                    "source_im": msg.source_im,
                    "external_user_id": msg.external_user_id,
                    "external_chat_id": msg.external_chat_id,
                    "external_message_id": msg.external_message_id,
                    "bridge_message_id": msg.bridge_message_id,
                    "attachments": msg.attachments,
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

        downloads = self.stage_result_downloads(result, base_url=base_url)
        reply = self._extract_reply_text(result)
        return {
            "reply": reply,
            "result": result,
            "artifacts": result.get("artifacts", []),
            "downloads": downloads,
        }

    async def _invoke_nesthub_stream(self, msg: BridgeMessage, *, base_url: str | None = None) -> dict[str, Any]:
        """Stream NestHub pipeline events and push LINE progress updates after each stage.

        Uses the ``/handle/stream`` SSE endpoint.  For each meaningful event a
        progress snapshot is pushed to the LINE user so they see a live todo-list
        that updates step by step.
        """
        base = self._nesthub_base_url()
        if not base:
            return {"reply": "NestHub core handle url is not configured."}

        stream_url = f"{base}/handle/stream"
        payload = {
            "input_text": msg.text,
            "context": {
                "metadata": {
                    "source_im": msg.source_im,
                    "external_user_id": msg.external_user_id,
                    "external_chat_id": msg.external_chat_id,
                    "external_message_id": msg.external_message_id,
                    "bridge_message_id": msg.bridge_message_id,
                    "attachments": msg.attachments,
                }
            },
            "output_format": "dict",
            "use_langraph": True,
        }

        access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        line_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        user_id = msg.external_user_id
        formatter = ProgressFormatter()
        final_result: dict[str, Any] | None = None

        # We use a push message ID placeholder so LINE shows a single "conversation"
        # (LINE does not support editing messages, so we push new updates instead)
        last_push_text: str | None = None

        async def _push_progress(text: str) -> None:
            nonlocal last_push_text
            if not access_token or not user_id or text == last_push_text:
                return
            last_push_text = text
            try:
                async with httpx.AsyncClient(timeout=10.0) as push_client:
                    await push_client.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers=line_headers,
                        json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
                    )
            except Exception:
                pass  # Progress push is best-effort; do not abort pipeline

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", stream_url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        progress_text = formatter.format_event(event)
                        if progress_text:
                            await _push_progress(progress_text)

                        if event.get("event") == "final":
                            final_result = event.get("result") or {}

        except Exception as exc:
            return {"reply": f"NestHub bridge stream error: {exc}"}

        if not isinstance(final_result, dict):
            return {"reply": "NestHub returned an invalid response."}

        downloads = self.stage_result_downloads(final_result, base_url=base_url)
        reply = self._extract_reply_text(final_result)

        # Push the final response (with downloads if any) via LINE
        final_payload = {
            "reply": reply,
            "result": final_result,
            "artifacts": final_result.get("artifacts", []),
            "downloads": downloads,
        }
        final_line_messages = self._build_line_messages(final_payload)
        if access_token and user_id:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    await client.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers=line_headers,
                        json={"to": user_id, "messages": final_line_messages},
                    )
            except Exception:
                pass

        return final_payload

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

    def stage_result_downloads(self, result: dict[str, Any], base_url: str | None = None) -> list[dict[str, Any]]:
        downloads = self.stage_local_result_artifacts(result.get("artifacts") or [], base_url=base_url)
        if downloads:
            return downloads

        final_output = ((result.get("execution_result") or {}).get("final_output") or {}) if isinstance(result, dict) else {}
        candidates = [
            final_output.get("file_read") or {},
            final_output.get("file_generate") or {},
        ]
        for payload in candidates:
            file_name = str(payload.get("file_name") or "").strip()
            content = payload.get("content")
            if not file_name or not isinstance(content, str) or not content:
                continue
            content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
            downloads.append(
                self.stage_artifact_bytes(
                    file_name=file_name,
                    content=content.encode("utf-8"),
                    content_type=content_type,
                    base_url=base_url,
                    metadata={
                        "artifact_type": str(payload.get("artifact_type") or "file"),
                        "artifact_id": str(Path(file_name).stem),
                        "source": "inline_result_content",
                    },
                )
            )

        # Handle image_generate step — artifact stored on disk at artifact_path
        if not downloads:
            img_payload = final_output.get("image_generate") or {}
            img_path_str = str(img_payload.get("artifact_path") or "").strip()
            if img_path_str:
                img_path = Path(img_path_str)
                # Try as-is, then relative to workspace root
                candidates = [img_path]
                if not img_path.is_absolute():
                    candidates.append(Path(os.getcwd()) / img_path)
                    workspace = os.getenv("NESTHUB_WORKSPACE_PATH", "").strip()
                    if workspace:
                        candidates.append(Path(workspace) / img_path)
                for candidate in candidates:
                    if candidate.exists() and candidate.is_file():
                        content_type = mimetypes.guess_type(candidate.name)[0] or "image/png"
                        downloads.append(
                            self.stage_artifact_bytes(
                                file_name=candidate.name,
                                content=candidate.read_bytes(),
                                content_type=content_type,
                                base_url=base_url,
                                metadata={
                                    "artifact_type": "image",
                                    "artifact_id": candidate.stem,
                                    "source": "image_generate",
                                },
                            )
                        )
                        break

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

        # image_generate step
        img_payload = final_output.get("image_generate") or {}
        img_status = str(img_payload.get("status") or "").strip()
        if img_status == "generated":
            img_path = str(img_payload.get("artifact_path") or "").strip()
            return f"图片已生成：{img_path}" if img_path else "图片已生成。"
        if img_status and img_status != "":
            return f"图片生成状态：{img_status}"

        task = result.get("task") or {}
        return f"NestHub completed {task.get('intent', 'the request')}."

    def _build_line_messages(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Build LINE message objects (text + optional image) from result."""
        downloads = result.get("downloads") or []
        image_downloads = [
            d for d in downloads
            if str(d.get("content_type") or "").startswith("image/")
        ]
        messages: list[dict[str, Any]] = []

        if image_downloads:
            # Send image message(s) first
            for img in image_downloads:
                url = str(img.get("download_url") or "").strip()
                if not url:
                    continue
                messages.append({
                    "type": "image",
                    "originalContentUrl": url,
                    "previewImageUrl": url,
                })
            # Follow with a brief text caption (LINE allows up to 5 messages per reply)
            caption = str(result.get("reply") or "图片已生成。").strip()[:5000]
            messages.append({"type": "text", "text": caption})
        else:
            reply_text = self._compose_line_reply_text(result)[:5000]
            messages.append({"type": "text", "text": reply_text or "收到您的消息！"})

        return messages[:5]  # LINE reply API: max 5 messages

    async def _deliver_line_response(self, msg: BridgeMessage, result: dict[str, Any]) -> None:
        access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        if not access_token:
            return

        event = msg.raw_payload or {}
        messages = self._build_line_messages(result)
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
                    json={"replyToken": reply_token, "messages": messages},
                )
                if response.is_success:
                    return

            if msg.external_user_id and msg.external_user_id != "unknown":
                await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers=headers,
                    json={"to": msg.external_user_id, "messages": messages},
                )

    def _compose_line_reply_text(self, result: dict[str, Any]) -> str:
        reply_text = str(result.get("reply") or "收到您的消息！").strip()
        downloads = result.get("downloads") or []
        if not isinstance(downloads, list) or not downloads:
            return reply_text or "收到您的消息！"
        lines = ["已为您准备下载链接："]
        for item in downloads:
            url = str(item.get("download_url") or "").strip()
            name = str(item.get("file_name") or "download").strip()
            if url:
                lines.append(f"{name}: {url}")
        return "\n".join(line for line in lines if line).strip()
