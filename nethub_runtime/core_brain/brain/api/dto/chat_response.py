from __future__ import annotations

from pydantic import BaseModel


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    task_id: str
    intent: dict
    route: dict
    result: dict
    state_updates: dict
