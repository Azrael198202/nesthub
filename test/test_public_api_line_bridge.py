from __future__ import annotations

import base64
import hashlib
import hmac

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