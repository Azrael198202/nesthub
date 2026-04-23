from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RouteContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    provider: str | None = None
    fallback_model: str | None = None
    reason: str | None = None
