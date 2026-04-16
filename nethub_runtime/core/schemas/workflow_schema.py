from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepSchema(BaseModel):
    step_id: str
    name: str
    task_type: str
    executor_type: str = "tool"
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    retry: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowSchema(BaseModel):
    workflow_id: str
    task_id: str
    mode: str = "normal"
    steps: list[WorkflowStepSchema] = Field(default_factory=list)
