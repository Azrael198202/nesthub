
import httpx
import os
import yaml

def load_bridge_config():
    config_path = os.path.join(os.path.dirname(__file__), "../../config/bridge_external.yaml")
    config_path = os.path.abspath(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    bridge_api = config.get("bridge_api")
    bridge_token = config.get("bridge_token")
    if not bridge_token:
        token_env = config.get("bridge_token_env")
        if token_env:
            bridge_token = os.getenv(token_env)
    poll_interval = config.get("poll_interval_seconds", 5)
    return bridge_api, bridge_token, poll_interval

BRIDGE_API, BRIDGE_TOKEN, POLL_INTERVAL = load_bridge_config()


import asyncio

async def poll_and_reply():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{BRIDGE_API}/hub/pending", headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
                resp.raise_for_status()
                pending = resp.json()
                for msg in pending:
                    bridge_message_id = msg["bridge_message_id"]
                    # claim 消息
                    await client.post(f"{BRIDGE_API}/hub/claim", json={"bridge_message_id": bridge_message_id}, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
                    # 回复结果
                    await client.post(f"{BRIDGE_API}/hub/result", json={"bridge_message_id": bridge_message_id, "result": {"reply": "received"}}, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
            except Exception as e:
                print(f"[line_demo] Polling error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(poll_and_reply())
