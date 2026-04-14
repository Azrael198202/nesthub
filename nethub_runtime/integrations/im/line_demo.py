import httpx
import os

BRIDGE_API = os.getenv("BRIDGE_API", "http://localhost:8080/api/bridge")
BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "test-token")

async def poll_and_reply():
    async with httpx.AsyncClient() as client:
        # 拉取待处理消息
        resp = await client.get(f"{BRIDGE_API}/hub/pending", headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
        resp.raise_for_status()
        pending = resp.json()
        for msg in pending:
            bridge_message_id = msg["bridge_message_id"]
            # claim 消息
            await client.post(f"{BRIDGE_API}/hub/claim", json={"bridge_message_id": bridge_message_id}, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
            # 回复结果
            await client.post(f"{BRIDGE_API}/hub/result", json={"bridge_message_id": bridge_message_id, "result": {"reply": "received"}}, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})

if __name__ == "__main__":
    import asyncio
    asyncio.run(poll_and_reply())
