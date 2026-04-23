# core-brain-agent-creation-and-tool-builder.md

Updated: 2026-04-23

## 0. Purpose

This document is the implementation-grade specification for:

1. `agent_creation_intent -> blueprint + tool + workflow + registration`
2. `tool_builder` full lifecycle design

This document is intended for:

- Codex
- Claude Code
- developers working on `nethub_runtime`

This document must be used together with:

- `core-brain-implementation-v2.md`
- `core-brain-refactor-patch.md`
- `core-brain-codex-execution-checklist.md`
- `core-brain-json-rules.md`

All code comments must be written in English.

---

## 1. Root Principle

Agent creation is itself a governed workflow.

It must follow the same execution discipline as normal business execution:

```text
intent -> workflow -> task -> trace -> validation
```

That means:

- creating a new assistant is not a shortcut action
- creating a new tool is not a shortcut action
- blueprint generation must be validated
- tool generation must be validated
- registration must be observable
- activation must be explicit

---

## 2. Terminology

### 2.1 UI term vs runtime term

Recommended naming:

- User-facing term: `Assistant`
- Internal runtime term: `Agent`

Reason:

- `Assistant` is easier for users to understand
- `Agent` is still required internally because it is a runtime object with state, assignment, and lifecycle

### 2.2 Core object mapping

- Intent = target
- Workflow = path
- Task = smallest traceable execution unit
- Blueprint = role definition
- Agent = runtime executor
- Tool = executable capability unit
- Trace = execution evidence
- Validation = correctness gate

---

## 3. Agent Creation Intent

### 3.1 Definition

`agent_creation_intent` is a meta-intent.
It means the user is asking the system to create a new reusable runtime capability.

Examples:

- Create a schedule assistant
- Create a household finance assistant
- Create a calendar tool
- Create an agent that manages reminders
- Build an assistant for my project workflows

This is different from normal business intent such as:

- manage_schedule
- record_expense
- summarize_document

### 3.2 Minimal agent creation intent JSON

```json
{
  "intent_id": "intent_1001",
  "intent_type": "agent_creation_intent",
  "name": "create_schedule_agent",
  "description": "Create a new runtime capability for schedule management.",
  "confidence": 0.95,
  "entities": {
    "agent_role": "schedule_manager",
    "target_domain": "family_schedule",
    "required_capabilities": [
      "create_event",
      "update_event",
      "delete_event",
      "query_event",
      "create_reminder"
    ],
    "required_tools": [
      "calendar_tool",
      "reminder_tool"
    ]
  },
  "constraints": {
    "language": "multilingual",
    "runtime_mode": "dynamic_creation"
  },
  "expected_outcome": [
    "blueprint_created",
    "creation_workflow_created",
    "agent_registered"
  ],
  "requires_clarification": true,
  "clarification_questions": [
    "Should this assistant support family shared schedules?",
    "Which calendar backend should be supported?"
  ],
  "source_text": "Create a schedule assistant for my family."
}
```

### 3.3 Mandatory rules

- `intent_type` must equal `agent_creation_intent`
- `expected_outcome` must be explicit
- `required_capabilities` must be normalized into structured data
- missing requirements must trigger clarification
- final success must be validated against `expected_outcome`

---

## 4. Full Agent Creation Pipeline

### 4.1 High-level pipeline

```text
User Input
-> Request Normalization
-> Intent Classification
-> Detect agent_creation_intent
-> Requirement Collection
-> Blueprint Generation
-> Agent-Creation Workflow Generation
-> Tool Resolution
   -> prebuilt
   -> external_adapter
   -> generated_code
-> Artifact Validation
-> Artifact Registration
-> Optional Runtime Agent Instantiation
-> Response Assembly
```

### 4.2 Runtime order inside core_brain

Recommended internal order:

```text
chat/
context/
routing/
planning/
workflows/
agents/
tools/
execution/
trace/
validation/
memory/
artifacts/
```

This order is recommended because it matches runtime execution and makes tracing easier.

---

## 5. Stage-by-Stage Design

## Stage 1. Request normalization

### Stage 1. Goal

Normalize UI/API input into typed request contract.

### Stage 1. Input

- raw text
- session id
- locale
- attachments if any

### Stage 1. Output

```json
{
  "request_id": "req_001",
  "session_id": "session_001",
  "text": "Create a schedule assistant for my family.",
  "locale": "en",
  "attachments": []
}
```

### Stage 1. Notes

- Do not perform business logic here
- This stage only normalizes input

---

## Stage 2. Intent classification

### Stage 2.Goal

Determine whether the request is a normal business intent or an agent creation intent.

### Stage 2.Output

```json
{
  "intent_id": "intent_1001",
  "intent_type": "agent_creation_intent",
  "name": "create_schedule_agent",
  "confidence": 0.95
}
```

### Stage 2. Rules

- If confidence is low, escalate to stronger external model
- If result is invalid JSON, escalate to stronger external model
- If classification is ambiguous, ask clarification questions

### Stage 2. Model routing rule

Recommended:

- local model first for speed
- external strong model fallback for low confidence or invalid output

---

## Stage 3. Requirement collection

### Stage 3.Goal

Collect all missing information required to create the new assistant or tool.

### Stage 3.Requirement categories

At minimum, collect:

1. role name
2. target domain
3. supported capabilities
4. required tools
5. input contract expectations
6. output contract expectations
7. execution policies
8. collaboration needs
9. activation mode
10. storage and integration constraints

### Stage 3.Output example

```json
{
  "requirement_id": "req_1001",
  "intent_id": "intent_1001",
  "agent_role": "schedule_manager",
  "target_domain": "family_schedule",
  "required_capabilities": [
    "create_event",
    "update_event",
    "delete_event",
    "query_event",
    "create_reminder"
  ],
  "required_tools": [
    "calendar_tool",
    "reminder_tool"
  ],
  "input_contract_expectations": {
    "required_fields": [
      "person",
      "date",
      "event"
    ]
  },
  "output_contract_expectations": {
    "required_fields": [
      "event_id",
      "status"
    ]
  },
  "execution_policy_expectations": {
    "max_retries": 2,
    "trace_required": true
  },
  "activation_mode": "register_and_activate",
  "completeness": 0.90,
  "missing_fields": [
    "calendar_backend"
  ]
}
```

### Stage 3.Rules

- Do not generate blueprint if requirement completeness is below threshold
- Requirement collection may become a sub-dialog
- Requirement collection itself must be traceable

---

## Stage 4. Blueprint generation

### Stage 4. Goal

Generate the structured runtime definition of the new agent type.

### Stage 4. Output example

```json
{
  "blueprint_id": "bp_schedule_manager_v1",
  "blueprint_type": "agent_blueprint",
  "version": "1.0.0",
  "agent_role": "schedule_manager",
  "display_name": "Schedule Assistant",
  "description": "Manage family schedule, events, and reminders.",
  "supported_intents": [
    "manage_schedule",
    "create_reminder",
    "update_schedule",
    "delete_schedule"
  ],
  "capabilities": [
    "resolve_schedule_request",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "create_reminder"
  ],
  "tool_requirements": [
    {
      "tool_name": "calendar_tool",
      "required": true,
      "resolution_strategy": [
        "prebuilt",
        "external_adapter",
        "generated_code"
      ]
    },
    {
      "tool_name": "reminder_tool",
      "required": true,
      "resolution_strategy": [
        "prebuilt",
        "generated_code"
      ]
    }
  ],
  "input_contract": {
    "schema_name": "schedule_task_input"
  },
  "output_contract": {
    "schema_name": "schedule_task_output"
  },
  "execution_policies": {
    "max_retries": 2,
    "trace_required": true,
    "step_validation_required": true,
    "fallback_agent_role": "planner_agent"
  },
  "collaboration_rules": {
    "can_delegate_to": [
      "planner_agent",
      "tool_manager_agent"
    ],
    "can_receive_from": [
      "planner_agent"
    ]
  },
  "status": "draft"
}
```

### Stage 4. Rules

- Blueprint defines an agent type, not an agent instance
- Blueprint must be versioned
- Blueprint must declare tool requirements
- Blueprint must declare execution policies
- Blueprint must be schema-valid before registration

---

## Stage 5. Agent-Creation Workflow generation

### Stage 5. Goal

Generate the workflow that creates the new agent capability.

### Stage 5. Output example

```json
{
  "workflow_id": "wf_create_schedule_agent_001",
  "workflow_type": "agent_creation",
  "source_intent_id": "intent_1001",
  "name": "create_schedule_agent_workflow",
  "status": "draft",
  "version": "1.0.0",
  "goal": "Create and register a schedule manager runtime capability.",
  "steps": [
    {
      "task_id": "task_001",
      "step_index": 1,
      "name": "collect_requirements",
      "task_type": "requirement_collection",
      "objective": "Collect missing requirements for the agent.",
      "assigned_agent_type": "planner_agent",
      "required_tools": [],
      "input_schema": "agent_requirement_input",
      "output_schema": "agent_requirement_output",
      "depends_on": [],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": false
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": [
          "agent_role",
          "required_capabilities"
        ]
      },
      "status": "pending"
    },
    {
      "task_id": "task_002",
      "step_index": 2,
      "name": "generate_blueprint",
      "task_type": "blueprint_generation",
      "objective": "Generate blueprint for the new agent.",
      "assigned_agent_type": "blueprint_designer_agent",
      "required_tools": [],
      "input_schema": "blueprint_generation_input",
      "output_schema": "blueprint_output",
      "depends_on": [
        "task_001"
      ],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "schema_validation",
        "schema_name": "blueprint_schema"
      },
      "status": "pending"
    },
    {
      "task_id": "task_003",
      "step_index": 3,
      "name": "resolve_tools",
      "task_type": "tool_resolution",
      "objective": "Resolve required tools for the blueprint.",
      "assigned_agent_type": "tool_manager_agent",
      "required_tools": [],
      "input_schema": "tool_resolution_input",
      "output_schema": "tool_resolution_output",
      "depends_on": [
        "task_002"
      ],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": [
          "resolved_tools"
        ]
      },
      "status": "pending"
    },
    {
      "task_id": "task_004",
      "step_index": 4,
      "name": "register_artifacts",
      "task_type": "artifact_registration",
      "objective": "Register blueprint, workflow, and tool artifacts.",
      "assigned_agent_type": "artifact_manager_agent",
      "required_tools": [],
      "input_schema": "artifact_registration_input",
      "output_schema": "artifact_registration_output",
      "depends_on": [
        "task_003"
      ],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": [
          "registered_artifact_ids"
        ]
      },
      "status": "pending"
    },
    {
      "task_id": "task_005",
      "step_index": 5,
      "name": "instantiate_agent",
      "task_type": "agent_instantiation",
      "objective": "Instantiate runtime agent if activation is requested.",
      "assigned_agent_type": "agent_manager_agent",
      "required_tools": [],
      "input_schema": "agent_instantiation_input",
      "output_schema": "agent_instantiation_output",
      "depends_on": [
        "task_004"
      ],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": [
          "agent_id"
        ]
      },
      "status": "pending"
    }
  ],
  "final_validation_rule": {
    "type": "intent_fulfillment_validation",
    "required_outcomes": [
      "blueprint_created",
      "creation_workflow_created",
      "agent_registered"
    ]
  }
}
```

### Stage 5. Rules

- This workflow is not the future business workflow of the agent
- This workflow is the creation workflow for the new capability
- Every task must be traceable and validatable

---

## Stage 6. Tool resolution

### Stage 6. Goal

Resolve every tool required by the blueprint.

### Stage 6. Resolution order

For each required tool:

1. check prebuilt tool registry
2. if not found, check external adapter registry
3. if still not found, trigger runtime tool generation via `tool_builder`

### Stage 6. Resolution result example

```json
{
  "resolved_tools": [
    {
      "tool_name": "calendar_tool",
      "resolution_result": "generated_code",
      "artifact_id": "tool_artifact_001"
    },
    {
      "tool_name": "reminder_tool",
      "resolution_result": "prebuilt",
      "artifact_id": "tool_artifact_002"
    }
  ]
}
```

### Stage 6. Rules

- Blueprint may reference tools that do not yet exist
- Tool existence must be resolved before final registration
- Tool generation must itself be governed workflow execution

---

## Stage 7. Artifact validation

### Stage 7. Goal

Validate all generated artifacts before registration.

### Stage 7. Required validations

- blueprint schema validation
- workflow schema validation
- tool schema validation
- tool code validation
- artifact manifest validation
- dependency validation
- runtime safety validation

### Stage 7. Output example

```json
{
  "validation_id": "val_001",
  "blueprint_valid": true,
  "workflow_valid": true,
  "tool_validations": [
    {
      "tool_name": "calendar_tool",
      "schema_valid": true,
      "build_valid": true,
      "runtime_valid": true
    }
  ],
  "status": "passed"
}
```

### Stage 7. Rules

- No artifact may be registered before validation succeeds
- Failed artifact must be retained in `generated/failed/`
- Validation results must be recorded in trace

---

## Stage 8. Artifact registration

### Stage 8. Goal

Register validated blueprint, workflow, and tool artifacts.

### Stage 8. Artifact lifecycle

All artifacts must use lifecycle state:

```text
drafts -> registered -> active
drafts -> failed
registered -> archive
active -> archive
failed -> archive
```

### Stage 8. Minimal artifact manifest

```json
{
  "id": "artifact_001",
  "type": "tool",
  "source_intent": "create_schedule_agent",
  "source_task": "task_003",
  "version": "1.0.0",
  "status": "registered",
  "runnable": true,
  "registered_at": "2026-04-23T10:30:00Z"
}
```

### Stage 8. Recommended extra fields

- created_at
- updated_at
- workflow_id
- blueprint_id
- session_id
- trace_id
- error_reason
- checksum

---

## Stage 9. Runtime agent instantiation

### Stage 9. Goal

Create runtime agent instance if requested.

### Stage 9. Input

- registered blueprint
- resolved tools
- activation mode

### Stage 9. Output example

```json
{
  "agent_id": "agent_schedule_001",
  "agent_type": "schedule_manager",
  "display_name": "Schedule Assistant",
  "blueprint_id": "bp_schedule_manager_v1",
  "workflow_id": "wf_create_schedule_agent_001",
  "state": "active",
  "capability_snapshot": [
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "create_reminder"
  ],
  "resolved_tools": [
    "calendar_tool",
    "reminder_tool"
  ],
  "runtime_context_ref": {
    "session_id": "session_001"
  }
}
```

### Stage 9. Rules

- Agent must reference exactly one blueprint
- Agent must not exist without blueprint binding
- Agent activation must be explicit
- Registration and activation are not the same event

---

## Stage 10. Response assembly

### Stage 10. Goal

Return clear result to the user and to runtime integrations such as TVBox.

### Stage 10. Response should include

- whether creation succeeded
- created blueprint id
- created workflow id
- created tool ids
- registered artifact ids
- runtime agent id if activated
- clarification requests if incomplete

### Stage 10. Example response

```json
{
  "status": "success",
  "reply": "The Schedule Assistant has been created and activated.",
  "created_blueprint_id": "bp_schedule_manager_v1",
  "created_workflow_id": "wf_create_schedule_agent_001",
  "created_tool_ids": [
    "tool_artifact_001"
  ],
  "registered_artifact_ids": [
    "artifact_bp_001",
    "artifact_wf_001",
    "tool_artifact_001"
  ],
  "runtime_agent_id": "agent_schedule_001"
}
```

---

## 6. Structured Trace Requirements

Every important task in the creation pipeline must generate trace.

### Minimal trace example

```json
{
  "trace_id": "trace_010",
  "intent_id": "intent_1001",
  "workflow_id": "wf_create_schedule_agent_001",
  "task_id": "task_003",
  "step_index": 3,
  "agent_id": "agent_tool_manager_001",
  "agent_type": "tool_manager_agent",
  "blueprint_id": "bp_tool_manager_v1",
  "task_input": {
    "required_tools": [
      "calendar_tool",
      "reminder_tool"
    ]
  },
  "task_output": {
    "resolved_tools": [
      {
        "tool_name": "calendar_tool",
        "resolution_result": "generated_code"
      },
      {
        "tool_name": "reminder_tool",
        "resolution_result": "prebuilt"
      }
    ]
  },
  "validation_result": {
    "step_goal_met": true,
    "schema_valid": true
  },
  "retry_count": 0,
  "fallback_used": false,
  "status": "success",
  "error_reason": null
}
```

### Mandatory trace fields

- intent_id
- workflow_id
- task_id
- agent_id
- agent_type
- task_input
- task_output
- validation_result
- retry_count
- fallback_used
- status
- error_reason

### Rules

- trace is not optional
- trace is not plain text log only
- trace must be machine-readable
- trace must support replay, debugging, and audit

---

## 7. Validation Model

Validation must happen at two levels.

### 7.1 Step-level validation

Check:

- schema correctness
- required fields
- build success
- tool availability
- task objective completion

### 7.2 Intent-level validation

Check:

- blueprint_created
- creation_workflow_created
- agent_registered
- tool_registered if required
- agent_activated if requested

### 7.2 Rules

- Step success does not mean intent success
- Final result must be checked against `expected_outcome`

---

## 8. Tool Builder Full Design

## 8.1 Purpose

`tool_builder` is the subsystem responsible for creating new tools at runtime when a blueprint or workflow requires a tool that is not available as:

- prebuilt
- external adapter

### 8.2 Position in architecture

Recommended location:

```text
nethub_runtime/core_brain/brain/tools/
├── registry/
├── resolver/
├── builder/
├── validator/
└── sandbox/
```

### 8.3 Roles of submodules

#### registry/

- store tool metadata
- load known tools
- search existing tools by name, domain, capability

#### resolver/

- choose between:
  - prebuilt
  - external_adapter
  - generated_code
- trigger `tool_builder` when generation is required

#### builder/

- collect tool requirements
- generate tool specification
- generate tool schema
- generate tool code
- generate test stub or validation stub
- generate registration manifest

#### validator/

- validate tool schema
- validate tool build result
- validate execution safety
- validate runtime dependencies

#### sandbox/

- execute generated tool in safe runtime
- run smoke test
- capture runtime errors before registration

---

## 8.4 Tool Builder pipeline

```text
Tool Request
-> Requirement Collection
-> Tool Spec Generation
-> Tool Contract Generation
-> Tool Code Generation
-> Tool Local Validation
-> Sandbox Execution
-> Tool Registration
-> Tool Activation
```

### 8.4 Rules

- tool builder is itself a governed workflow
- every stage must emit trace
- generated tool must not be registered without validation

---

## 8.5 Tool Requirement Collection

### Goal

Collect all information needed to generate a usable tool.

### Required fields

At minimum:

- tool_name
- tool_domain
- purpose
- operations supported
- input contract
- output contract
- dependencies
- execution mode
- storage requirements
- external API requirements if any

### Example

```json
{
  "tool_request_id": "tool_req_001",
  "tool_name": "calendar_tool",
  "tool_domain": "calendar_management",
  "purpose": "Manage events and reminders for family schedules.",
  "operations": [
    "create_event",
    "update_event",
    "delete_event",
    "query_event"
  ],
  "input_contract_expectations": {
    "required_fields": [
      "title",
      "date",
      "participants"
    ]
  },
  "output_contract_expectations": {
    "required_fields": [
      "event_id",
      "status"
    ]
  },
  "execution_mode": "local_runtime",
  "dependencies": [
    "python"
  ],
  "missing_fields": [
    "calendar_backend"
  ]
}
```

---

## 8.6 Tool Spec Generation

### 8.6 Goal

Generate the structured metadata definition for the new tool.

### Example tool spec

```json
{
  "tool_name": "calendar_tool",
  "tool_type": "runtime_tool",
  "description": "Create, update, delete, and query calendar events.",
  "input_contract": {
    "schema_name": "calendar_tool_input"
  },
  "output_contract": {
    "schema_name": "calendar_tool_output"
  },
  "implementation_type": "generated_code",
  "execution_mode": "local_runtime",
  "dependencies": [
    "python",
    "calendar_backend"
  ],
  "status": "draft",
  "version": "1.0.0"
}
```

### 8.6 Rules

- spec must be schema-valid
- spec must explicitly declare implementation type
- spec must explicitly declare execution mode

Allowed values:

`implementation_type`

- prebuilt
- external_adapter
- generated_code

`execution_mode`

- local_runtime
- remote_api
- sandbox_runtime

---

## 8.7 Tool Contract Generation

### 8.7 Goal

Generate input and output schema definitions for the tool.

### Example contracts

```json
{
  "input_schema": {
    "schema_name": "calendar_tool_input",
    "type": "object",
    "properties": {
      "operation": { "type": "string" },
      "title": { "type": "string" },
      "date": { "type": "string" },
      "participants": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["operation"]
  },
  "output_schema": {
    "schema_name": "calendar_tool_output",
    "type": "object",
    "properties": {
      "status": { "type": "string" },
      "event_id": { "type": "string" },
      "message": { "type": "string" }
    },
    "required": ["status"]
  }
}
```

### 8.7 Rules

- contracts must be generated before code generation
- code generation must target the contracts
- validation must use the same contracts

---

## 8.8 Tool Code Generation

### 8.8 Goal

Generate runnable tool code from the tool spec and contracts.

### Generated outputs

At minimum:

- tool implementation file
- tool registration metadata
- contract files
- smoke test stub

### Example codegen output metadata

```json
{
  "tool_name": "calendar_tool",
  "generated_files": [
    "generated/drafts/tools/calendar_tool.py",
    "generated/drafts/tools/calendar_tool.input.schema.json",
    "generated/drafts/tools/calendar_tool.output.schema.json",
    "generated/drafts/tools/calendar_tool.test.py",
    "generated/drafts/tools/calendar_tool.manifest.json"
  ],
  "entrypoint": "calendar_tool.execute"
}
```

### 8.8 Rules

- code comments must be in English
- generated code must not contain hidden hardcoded business data
- generated code must conform to tool contract
- generated code must be runnable in controlled runtime

---

## 8.9 Tool Validation

### 8.9 Goal

Verify that the generated tool is usable and safe enough to register.

### Validation categories

- schema validation
- static structure validation
- dependency validation
- runtime smoke test
- output contract validation
- sandbox safety validation

### Example validation result

```json
{
  "tool_name": "calendar_tool",
  "schema_valid": true,
  "files_present": true,
  "dependency_check_passed": true,
  "smoke_test_passed": true,
  "output_contract_passed": true,
  "sandbox_safe": true,
  "status": "passed"
}
```

### 8.9 Rules

- failed tool must go to `generated/failed/`
- successful tool may move to `generated/registered/`
- activation requires validation success

---

## 8.10 Tool Registration

### 8.10 Goal

Register validated tool into tool registry.

### Registration result example

```json
{
  "tool_name": "calendar_tool",
  "artifact_id": "tool_artifact_001",
  "status": "registered",
  "runnable": true,
  "registered_at": "2026-04-23T10:40:00Z"
}
```

### 8.10 Rules

- registration must create artifact manifest
- registration must update tool registry
- registration must be traceable

---

## 8.11 Tool Activation

### 8.11 Goal

Allow the registered tool to be used by future blueprints and runtime agents.

### 8.11 Rules

- registration and activation are not the same event
- some tools may remain registered but inactive
- activation should update tool availability snapshot

---

## 8.12 Tool Builder trace requirements

Every stage of tool builder must generate trace.

Recommended task list:

1. collect_tool_requirements
2. generate_tool_spec
3. generate_tool_contracts
4. generate_tool_code
5. validate_tool
6. register_tool
7. activate_tool

Each task must generate:

- trace
- validation result
- artifact references if produced

---

## 9. Recommended Codex Implementation Plan

### Phase 1

- implement `agent_creation_intent` routing
- implement requirement collection structures
- implement blueprint generation JSON
- implement creation workflow JSON

### Phase 2

- implement tool resolver
- implement tool registry
- implement `tool_builder` interfaces
- implement artifact manifest

### Phase 3

- implement tool spec generation
- implement tool contract generation
- implement tool code generation
- implement tool validation

### Phase 4

- implement registration and activation
- implement runtime agent instantiation
- bind trace + validation + memory writeback

---

## 10. Mandatory Coding Rules for Codex

Codex must follow these rules:

1. Do not treat agent creation as direct code generation only
2. Do not skip requirement collection
3. Do not generate blueprint without schema validation
4. Do not register workflow without validation
5. Do not assume tools always already exist
6. Do not generate tools without contracts
7. Do not activate agents without successful registration
8. Do not use plain text logs as replacement for structured trace
9. Do not use step success as replacement for final intent success
10. Do not mix user-facing assistant language with runtime agent identity internally

---

## 11. Final Summary

The complete governed chain is:

```text
agent_creation_intent
-> requirement collection
-> blueprint generation
-> creation workflow generation
-> tool resolution
   -> prebuilt
   -> external_adapter
   -> generated_code via tool_builder
-> artifact validation
-> artifact registration
-> optional agent instantiation
-> trace + validation
-> usable assistant
```

The complete `tool_builder` chain is:

```text
tool_request
-> requirement collection
-> tool spec generation
-> tool contract generation
-> tool code generation
-> validation
-> sandbox execution
-> registration
-> activation
```

Any implementation that violates this execution discipline must be considered incorrect.
