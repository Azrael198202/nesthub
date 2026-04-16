from __future__ import annotations

def run(payload: dict | None = None) -> dict:
    payload = payload or {}
    return {"ok": True, "feature_id": "feature_auto_demo", "payload": payload}
