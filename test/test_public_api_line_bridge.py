from __future__ import annotations

import base64
import hashlib
import hmac
from pathlib import Path

from fastapi.testclient import TestClient

from api.public_api.app import app


def _line_payload(text: str = "你好，NestHub") -> dict:
    return {
        "destination": "test-destination",
        "events": [
            {
                "type": "message",
                "replyToken": "reply-token-123",
                "source": {"type": "user", "userId": "U123"},
                "timestamp": 1710000000000,
                "message": {"type": "text", "id": "mid-123", "text": text},
            }
        ],
    }


def test_line_webhook_is_processed_through_public_api(monkeypatch) -> None:
    delivered: list[dict] = []

    async def fake_invoke(msg):
        return {"reply": f"NestHub handled: {msg.text}", "artifacts": []}

    async def fake_deliver(msg, result):
        delivered.append({"msg": msg, "result": result})

    monkeypatch.delenv("LINE_CHANNEL_SECRET", raising=False)
    monkeypatch.setenv("NESTHUB_PUBLIC_API_PROCESS_INLINE", "true")
    monkeypatch.setattr(app.state.bridge_service, "_invoke_nesthub", fake_invoke)
    monkeypatch.setattr(app.state.bridge_service, "_deliver_line_response", fake_deliver)

    client = TestClient(app)
    response = client.post("/api/bridge/im/inbound", json=_line_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["results"][0]["reply"] == "NestHub handled: 你好，NestHub"
    message = app.state.bridge_service.get_message(payload["results"][0]["bridge_message_id"])
    assert message is not None
    assert message.status == "completed"
    assert delivered
    assert delivered[0]["result"]["reply"] == "NestHub handled: 你好，NestHub"


def test_line_webhook_is_queued_by_default_without_inline_processing(monkeypatch) -> None:
    monkeypatch.delenv("LINE_CHANNEL_SECRET", raising=False)
    monkeypatch.delenv("NESTHUB_PUBLIC_API_PROCESS_INLINE", raising=False)
    monkeypatch.delenv("NESTHUB_CORE_HANDLE_URL", raising=False)

    client = TestClient(app)
    response = client.post("/api/bridge/im/inbound", json=_line_payload("进入队列"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["results"][0]["status"] == "pending"
    assert payload["results"][0]["reply"] == ""
    message = app.state.bridge_service.get_message(payload["results"][0]["bridge_message_id"])
    assert message is not None
    assert message.status == "pending"


def test_line_webhook_rejects_invalid_signature(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "secret-123")
    client = TestClient(app)

    response = client.post(
        "/api/bridge/im/inbound",
        json=_line_payload(),
        headers={"X-Line-Signature": "invalid"},
    )

    assert response.status_code == 401


def test_line_webhook_accepts_valid_signature(monkeypatch) -> None:
    delivered: list[dict] = []
    secret = "secret-456"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)

    async def fake_invoke(msg):
        return {"reply": "ok", "artifacts": []}

    async def fake_deliver(msg, result):
        delivered.append({"msg": msg.bridge_message_id, "reply": result["reply"]})

    monkeypatch.setenv("NESTHUB_PUBLIC_API_PROCESS_INLINE", "true")
    monkeypatch.setattr(app.state.bridge_service, "_invoke_nesthub", fake_invoke)
    monkeypatch.setattr(app.state.bridge_service, "_deliver_line_response", fake_deliver)

    payload = _line_payload("测试签名")
    import json

    body = json.dumps(payload).encode("utf-8")
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/bridge/im/inbound",
        content=body,
        headers={"Content-Type": "application/json", "X-Line-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["processed"] == 1
    assert delivered[0]["reply"] == "ok"


def test_hub_artifact_upload_and_download(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setenv("NESTHUB_PUBLIC_API_BASE_URL", "https://public.example")

    response = client.post(
        "/api/bridge/hub/artifact",
        headers={"Authorization": "Bearer test-token"},
        json={
            "file_name": "hello_world_button.html",
            "artifact_type": "file",
            "artifact_id": "hello_world_button",
            "content_base64": base64.b64encode(b"<html>Hello</html>").decode("utf-8"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    download = payload["download"]
    assert download["download_url"].startswith("https://public.example/api/temp-files/")

    path = Path(download["download_url"].replace("https://public.example", ""))
    download_response = client.get(str(path))
    assert download_response.status_code == 200
    assert download_response.text == "<html>Hello</html>"


def test_line_reply_text_includes_download_links() -> None:
    text = app.state.bridge_service._compose_line_reply_text(
        {
            "reply": "文件已经准备好。",
            "downloads": [
                {
                    "file_name": "hello_world_button.html",
                    "download_url": "https://public.example/api/temp-files/abc123/hello_world_button.html",
                }
            ],
        }
    )

    assert "文件已经准备好。" in text
    assert "hello_world_button.html" in text
    assert "https://public.example/api/temp-files/abc123/hello_world_button.html" in text