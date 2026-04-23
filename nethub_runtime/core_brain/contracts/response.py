from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CoreBrainResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    intent: dict[str, Any]
    route: dict[str, Any]
    workflow_plan: dict[str, Any]
    execution_result: dict[str, Any]
    state_updates: dict[str, Any]
    result: dict[str, Any]
    artifacts: list[dict[str, Any]]
    task: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    blueprints: list[dict[str, Any]] | None = None
