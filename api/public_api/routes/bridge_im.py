
import base64
import hashlib
import hmac
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request


router = APIRouter()
logger = logging.getLogger("api.public_api.routes.bridge_im")

# LINE message types we handle
_SUPPORTED_MSG_TYPES = {"text", "image", "file"}


def _derive_input_type(content_type: str) -> str:
    """Map a MIME type to a simplified input_type for NestHub intent routing."""
    ct = content_type.lower()
    if ct.startswith("image/"):
        return "image"
    if ct in (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ):
        return "document"
    return "file"


def _public_base_url(request: Request) -> str:
    configured = os.getenv("NESTHUB_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")

def _verify_line_signature(body: bytes, signature: str | None) -> bool:
    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    if not channel_secret:
        return True
    if not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def _download_line_content(message_id: str, access_token: str) -> tuple[bytes, str] | None:
    """Download a file/image from LINE Content API.

    Returns ``(content_bytes, content_type)`` or ``None`` on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://api-data.line.me/v2/bot/message/{message_id}/content",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
            return resp.content, content_type
    except Exception as exc:
        logger.warning("Failed to download LINE content %s: %s", message_id, exc)
        return None


def _line_file_name(message: dict[str, Any], msg_type: str, message_id: str) -> str:
    """Determine a sensible file name from a LINE message."""
    if msg_type == "file":
        return str(message.get("fileName") or f"file_{message_id}.bin")
    # image — LINE does not provide a file name
    return f"image_{message_id}.jpg"


@router.post("/im/inbound")
async def im_inbound(request: Request, x_line_signature: str = Header(None)):
    logger.info("/im/inbound called, X-Line-Signature: %s", x_line_signature)
    body = await request.body()
    if not _verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="invalid LINE signature")

    data = await request.json()
    logger.info("/im/inbound payload: %s", data)

    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    base_url = _public_base_url(request)

    results = []
    if "events" in data and data["events"]:
        for event in data["events"]:
            if event.get("type") != "message":
                continue
            message = event.get("message", {})
            msg_type = message.get("type")
            if msg_type not in _SUPPORTED_MSG_TYPES:
                continue

            source = event.get("source", {})
            external_user_id = source.get("userId", "unknown")
            external_chat_id = source.get("groupId") or source.get("roomId") or external_user_id
            external_message_id = message.get("id", "unknown")

            text = ""
            attachments: list[dict[str, Any]] = []

            if msg_type == "text":
                text = message.get("text", "")
                logger.info(
                    "Extracted LINE fields: userId=%s groupId=%s messageId=%s text=%s",
                    external_user_id, external_chat_id, external_message_id, text,
                )
            else:
                # image or file — download from LINE Content API and stage in temp store
                file_name = _line_file_name(message, msg_type, external_message_id)
                logger.info(
                    "LINE %s upload: userId=%s messageId=%s fileName=%s",
                    msg_type, external_user_id, external_message_id, file_name,
                )
                if access_token:
                    result = await _download_line_content(external_message_id, access_token)
                    if result:
                        content_bytes, content_type = result
                        record = request.app.state.temp_file_store.save_bytes(
                            file_name=file_name,
                            content=content_bytes,
                            content_type=content_type,
                            metadata={
                                "source": "line_upload",
                                "message_type": msg_type,
                                "external_user_id": external_user_id,
                                "external_message_id": external_message_id,
                            },
                        )
                        download_url = f"{base_url}/api/temp-files/{record.file_id}/{record.file_name}"
                        attachments.append({
                            "file_id": record.file_id,
                            "file_name": record.file_name,
                            "content_type": record.content_type,
                            "download_url": download_url,
                            "stored_path": str(record.stored_path),
                            "input_type": _derive_input_type(record.content_type),
                            "source_message_type": msg_type,
                        })
                        text = f"处理上传的文件: {file_name}"
                        logger.info("Staged LINE upload as temp file: %s → %s", file_name, download_url)
                    else:
                        text = f"收到文件: {file_name}（无法下载）"
                else:
                    text = f"收到文件: {file_name}（LINE token 未配置）"

            msg = request.app.state.bridge_service.create_message(
                "line", external_user_id, external_chat_id, external_message_id,
                text, event, attachments=attachments,
            )
            if request.app.state.bridge_service.should_process_inline():
                result = await request.app.state.bridge_service.process_message(
                    msg, base_url=base_url
                )
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

