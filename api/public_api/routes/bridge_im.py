
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from api.public_api.routes.debug import append_event


router = APIRouter()
logger = logging.getLogger("api.public_api.routes.bridge_im")


def _received_dir() -> Path:
    """Return (and create) the public_api received directory for LINE uploads."""
    configured = os.getenv("NESTHUB_PUBLIC_API_RECEIVED_DIR", "").strip()
    if configured:
        base = Path(configured)
    else:
        # <workspace_root>/api/public_api/received/
        base = Path(__file__).resolve().parents[1] / "received"
    base.mkdir(parents=True, exist_ok=True)
    return base

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
                # image or file — download from LINE Content API and save to received/
                file_name = _line_file_name(message, msg_type, external_message_id)
                logger.info(
                    "LINE %s upload: userId=%s messageId=%s fileName=%s",
                    msg_type, external_user_id, external_message_id, file_name,
                )
                append_event(request, {
                    "action": "line_file_webhook_received",
                    "status": "pending_download",
                    "msg_type": msg_type,
                    "file_name": file_name,
                    "message_id": external_message_id,
                    "user_id": external_user_id,
                    "has_access_token": bool(access_token),
                })
                if access_token:
                    result = await _download_line_content(external_message_id, access_token)
                    if result:
                        content_bytes, content_type = result
                        # ── Step 1: Save to public_api/received/ (persistent) ──
                        date_prefix = datetime.now(UTC).strftime("%Y%m%d")
                        dest_dir = _received_dir() / date_prefix
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = dest_dir / file_name
                        # Avoid overwriting if same filename arrives twice
                        if dest_path.exists():
                            stem = Path(file_name).stem
                            suffix = Path(file_name).suffix
                            dest_path = dest_dir / f"{stem}_{external_message_id}{suffix}"
                        dest_path.write_bytes(content_bytes)
                        logger.info(
                            "Saved LINE upload to received/: %s (%d bytes)",
                            dest_path, len(content_bytes),
                        )
                        # ── Step 2: Build attachment pointing at the saved path ──
                        input_type_label = _derive_input_type(content_type)
                        download_url = (
                            f"{base_url}/api/received/{date_prefix}/{dest_path.name}"
                        )
                        attachments.append({
                            "file_name": file_name,
                            "content_type": content_type,
                            "stored_path": str(dest_path),   # same-host direct read
                            "download_url": download_url,    # cross-host HTTP download
                            "input_type": input_type_label,
                            "source_message_type": msg_type,
                            "external_message_id": external_message_id,
                        })
                        append_event(request, {
                            "action": "line_file_saved_to_received",
                            "status": "ok",
                            "file_name": file_name,
                            "content_type": content_type,
                            "input_type": input_type_label,
                            "stored_path": str(dest_path),
                            "download_url": download_url,
                            "size_bytes": len(content_bytes),
                            "message_id": external_message_id,
                        })
                        if input_type_label == "image":
                            text = f"识别图片内容: {file_name}"
                        else:
                            text = f"分析文档: {file_name}"
                    else:
                        append_event(request, {
                            "action": "line_content_api_download",
                            "status": "failed",
                            "file_name": file_name,
                            "message_id": external_message_id,
                            "error": "LINE Content API returned no data",
                        })
                        text = f"收到文件: {file_name}（无法下载）"
                else:
                    append_event(request, {
                        "action": "line_content_api_download",
                        "status": "skipped",
                        "file_name": file_name,
                        "message_id": external_message_id,
                        "error": "LINE_CHANNEL_ACCESS_TOKEN not configured",
                    })
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
                append_event(request, {
                    "action": "bridge_message_processed",
                    "status": status,
                    "bridge_message_id": msg.bridge_message_id,
                    "has_attachments": bool(attachments),
                    "reply_preview": reply[:80] if reply else "",
                })
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

