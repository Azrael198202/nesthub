from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidationResultContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_goal_met: bool
    schema_valid: bool
    intent_alignment: bool | None
    messages: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
