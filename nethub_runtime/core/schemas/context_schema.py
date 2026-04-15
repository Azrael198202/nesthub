from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class CoreContextSchema(BaseModel):
    session_id: str
    trace_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    locale: str = "ja-JP"
    timezone: str = "Asia/Tokyo"
    session_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
