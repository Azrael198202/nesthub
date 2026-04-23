from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    blueprint_id: str | None = None
    workflow_id: str | None = None
    status: str = Field(min_length=1)
