from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubTask(BaseModel):
    subtask_id: str
    name: str
    goal: str
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSchema(BaseModel):
    task_id: str
    intent: str
    input_text: str
    domain: str = "general"
    constraints: dict[str, Any] = Field(default_factory=dict)
    output_requirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
