from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlueprintSchema(BaseModel):
    blueprint_id: str
    name: str
    domain: str
    intent: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
