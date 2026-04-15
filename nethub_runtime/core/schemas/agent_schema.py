from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentSchema(BaseModel):
    agent_id: str
    name: str
    role: str
    goals: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    model_strategy: dict[str, Any] = Field(default_factory=dict)
    tool_strategy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
