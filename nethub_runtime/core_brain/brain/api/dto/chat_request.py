from __future__ import annotations

from pydantic import BaseModel, Field


class ClientInfo(BaseModel):
    name: str = "unknown"
    version: str = "0.0.0"


class ChatRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1)
    task_id: str | None = None
    user_id: str = "tvbox"
    message: str = Field(min_length=1)
    mode: str = "chat"
    context_policy: str = "default"
    allow_external: bool = True
    stream: bool = False
    client: ClientInfo = ClientInfo()
