from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


SnakeName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]


class ContextRefsContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    task_session_id: str | None = None
    memory_refs: list[str] = Field(default_factory=list)


class IntentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(min_length=1)
    intent_type: Literal["normal_intent", "agent_creation_intent"]
    name: SnakeName
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, Any]
    constraints: dict[str, Any]
    expected_outcome: list[str] = Field(min_length=1)
    requires_clarification: bool
    clarification_questions: list[str]
    source_text: str = Field(min_length=1)
    context_refs: ContextRefsContract | None = None
    metadata: dict[str, Any] | None = None


class RetryPolicyContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(ge=0)
    fallback_allowed: bool


class ValidationRuleContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal[
        "schema_validation",
        "step_output_validation",
        "intent_fulfillment_validation",
        "custom_validation",
    ]
    schema_name: str | None = None
    required_fields: list[str] | None = None
    required_outcomes: list[str] | None = None


class WorkflowTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    step_index: int = Field(ge=1)
    name: SnakeName
    task_type: Literal[
        "requirement_collection",
        "entity_resolution",
        "intent_analysis",
        "route_selection",
        "blueprint_generation",
        "workflow_generation",
        "tool_resolution",
        "spec_generation",
        "code_generation",
        "calendar_action",
        "artifact_registration",
        "agent_instantiation",
        "validation",
        "custom_task",
    ]
    objective: str = Field(min_length=1)
    assigned_agent_type: str = Field(min_length=1)
    assigned_agent_id: str | None = None
    required_tools: list[str]
    input_schema: str = Field(min_length=1)
    output_schema: str = Field(min_length=1)
    depends_on: list[str]
    retry_policy: RetryPolicyContract
    validation_rule: ValidationRuleContract
    status: Literal["pending", "running", "success", "failed", "skipped", "blocked"]
    notes: str | None = None


class FinalValidationRuleContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["intent_fulfillment_validation", "custom_validation"]
    required_outcomes: list[str] = Field(min_length=1)


class WorkflowContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    workflow_type: Literal["business_execution", "agent_creation"]
    source_intent_id: str = Field(min_length=1)
    name: SnakeName
    status: Literal["draft", "registered", "active", "paused", "completed", "failed", "archived"]
    version: SemVer
    goal: str = Field(min_length=1)
    steps: list[WorkflowTaskContract] = Field(min_length=1)
    final_validation_rule: FinalValidationRuleContract
    metadata: dict[str, Any] | None = None


class ToolContractRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(min_length=1)


class ToolRequirementContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    required: bool
    resolution_strategy: list[Literal["prebuilt", "external_adapter", "generated_code"]] = Field(min_length=1)
    min_version: str | None = None


class ExecutionPoliciesContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(ge=0)
    trace_required: bool
    step_validation_required: bool
    fallback_agent_role: str | None


class CollaborationRulesContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_delegate_to: list[str]
    can_receive_from: list[str]


class BlueprintContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blueprint_id: str = Field(min_length=1)
    blueprint_type: Literal["agent_blueprint", "tool_blueprint", "workflow_blueprint"]
    version: SemVer
    agent_role: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supported_intents: list[str] = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    tool_requirements: list[ToolRequirementContract]
    input_contract: ToolContractRef
    output_contract: ToolContractRef
    execution_policies: ExecutionPoliciesContract
    collaboration_rules: CollaborationRulesContract
    status: Literal["draft", "registered", "active", "deprecated", "archived"]
    metadata: dict[str, Any] | None = None


class ToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: SnakeName
    tool_type: Literal["runtime_tool", "integration_tool", "system_tool"]
    description: str = Field(min_length=1)
    input_contract: ToolContractRef
    output_contract: ToolContractRef
    implementation_type: Literal["prebuilt", "generated_code", "external_adapter"]
    execution_mode: Literal["local_runtime", "remote_api", "sandbox_runtime"]
    dependencies: list[str]
    entrypoint: str | None = None
    artifact_manifest_ref: str | None = None
    status: Literal["draft", "registered", "active", "failed", "archived"]
    version: SemVer
    metadata: dict[str, Any] | None = None


class ToolCallTraceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    status: Literal["success", "failed", "skipped"]
    input_ref: str | None
    output_ref: str | None
    error_reason: str | None


class TraceValidationResultContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_goal_met: bool
    schema_valid: bool
    intent_alignment: bool | None
    messages: list[str]


class TraceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    step_index: int = Field(ge=1)
    intent_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    blueprint_id: str | None
    tool_calls: list[ToolCallTraceContract]
    task_input: dict[str, Any]
    task_output: dict[str, Any]
    validation_result: TraceValidationResultContract
    retry_count: int = Field(ge=0)
    fallback_used: bool
    status: Literal["success", "failed", "running", "pending", "skipped"]
    error_reason: str | None
    started_at: str | None
    finished_at: str | None
    metadata: dict[str, Any] | None = None
