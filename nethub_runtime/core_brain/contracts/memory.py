from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryBundleContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_context: dict[str, Any]
    session_context: list[dict[str, Any]] = Field(default_factory=list)
    task_context: dict[str, Any] = Field(default_factory=dict)
    long_term_context: list[str] = Field(default_factory=list)
    execution_context: dict[str, Any] = Field(default_factory=dict)
