from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nethub_runtime.core.enums import AgentClass, AgentLayer, WorkflowComponentType


class AgentFrameworkProfile(BaseModel):
    agent_class: AgentClass
    agent_layer: AgentLayer
    profile_name: str
    entity_label: str
    supports_knowledge_base: bool = False
    supports_direct_execution: bool = False
    supports_analysis: bool = False
    preferred_capture_mode: str = "guided_collection"
    workflow_roles: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowComponentSchema(BaseModel):
    component_type: WorkflowComponentType
    name: str
    responsibility: str
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowCompositionSchema(BaseModel):
    workflow_name: str
    objective: str
    knowledge_agents: list[str] = Field(default_factory=list)
    execution_agents: list[str] = Field(default_factory=list)
    analysis_agents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    analyzers: list[str] = Field(default_factory=list)
    io_operations: list[str] = Field(default_factory=list)
    components: list[WorkflowComponentSchema] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
