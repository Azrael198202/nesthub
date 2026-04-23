from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CoreBrainRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(default="default", min_length=1)
    task_id: str | None = None
    user_id: str = "tvbox"
    message: str = Field(min_length=1)
    mode: str = "chat"
    context_policy: str = "default"
    allow_external: bool = True
    stream: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    client: dict[str, str] = Field(default_factory=dict)
