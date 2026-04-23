# core-brain-json-rules.md
Updated: 2026-04-23

## 0. Purpose

This document defines the mandatory JSON rules for:

- intent
- workflow
- workflow task
- blueprint
- agent
- trace
- tool

It also defines:

- the difference between normal intent and agent-creation intent
- the execution order of `core_brain`
- the runtime policy for tool creation
- the relationship between dynamically created agents, blueprints, workflows, and traces

All future code generation must follow this document.
All code comments must be written in English.

---

## 1. Core Execution Order

`core_brain` should be organized according to execution order so that the runtime can be traced clearly.

Mandatory runtime order:

1. Request normalization
2. Context loading
3. Intent classification
4. Intent parsing
5. Route selection
6. Planning
7. Workflow generation
8. Agent / blueprint resolution
9. Tool resolution
10. Step execution
11. Trace recording
12. Step validation
13. Final intent validation
14. State writeback
15. Response assembly

Recommended package order inside `core_brain/brain/`:

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

This ordering is preferred because it matches the actual runtime flow.

---

## 2. Intent Types

Intent must be divided into two major categories.

### 2.1 Normal Intent

Normal intent means the user wants the system to complete a business or operational objective.

Examples:
- manage_schedule
- create_reminder
- record_expense
- summarize_document
- search_knowledge

Normal intent does NOT mean the user is trying to create a new runtime capability definition.

### 2.2 Agent-Creation Intent

Agent-creation intent means the user wants the system to create a new agent capability at runtime.

Examples:
- create_agent
- create_schedule_agent
- create_tool_agent
- define_new_business_agent

This kind of intent must trigger:

1. requirement collection
2. capability analysis
3. blueprint generation
4. workflow generation for creation
5. optional tool generation
6. artifact registration
7. agent instantiation or deferred activation

Important rule:
- agent-creation intent is NOT the same as normal business execution intent
- it is a meta-intent
- it creates future execution capability

---

## 3. Mandatory JSON Rule: Intent

Intent must always be structured.

### 3.1 Base Intent Schema

```json
{
  "intent_id": "intent_001",
  "intent_type": "normal_intent",
  "name": "manage_schedule",
  "description": "Create or update calendar events and reminders.",
  "confidence": 0.95,
  "entities": {
    "person": "father",
    "date": "next Tuesday",
    "event": "go to Osaka",
    "reminder": "one day before"
  },
  "constraints": {},
  "expected_outcome": [
    "calendar_event_created",
    "reminder_created"
  ],
  "requires_clarification": false,
  "clarification_questions": [],
  "source_text": "Help me arrange a trip to Osaka for my father next Tuesday and remind me one day before."
}
```

### 3.2 Agent-Creation Intent Schema

```json
{
  "intent_id": "intent_002",
  "intent_type": "agent_creation_intent",
  "name": "create_schedule_agent",
  "description": "Create a new agent for schedule management.",
  "confidence": 0.93,
  "entities": {
    "agent_role": "schedule_manager",
    "target_domain": "calendar_management",
    "required_capabilities": [
      "create_event",
      "update_event",
      "delete_event",
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
    "Which calendar backend should be supported?",
    "Should the agent support reminders?"
  ],
  "source_text": "Create a schedule management agent for my family."
}
```

### 3.3 Intent Rules

Mandatory rules:
- `intent_type` must be one of:
  - `normal_intent`
  - `agent_creation_intent`
- `name` must be normalized and stable
- `entities` must be structured
- `expected_outcome` must be explicit
- `source_text` must preserve the user message
- `requires_clarification` must be explicit
- final success must be measured against `expected_outcome`

---

## 4. Mandatory JSON Rule: Workflow

Workflow is the execution plan derived from intent.

### 4.1 Base Workflow Schema

```json
{
  "workflow_id": "wf_001",
  "workflow_type": "business_execution",
  "source_intent_id": "intent_001",
  "name": "manage_schedule_workflow",
  "status": "draft",
  "version": "1.0.0",
  "goal": "Create calendar event and reminder for the requested schedule.",
  "steps": [
    {
      "task_id": "task_001",
      "step_index": 1,
      "name": "resolve_person",
      "task_type": "entity_resolution",
      "objective": "Resolve the person identity from user context.",
      "assigned_agent_type": "context_agent",
      "required_tools": [],
      "input_schema": "person_resolution_input",
      "output_schema": "person_resolution_output",
      "depends_on": [],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["person_id"]
      },
      "status": "pending"
    },
    {
      "task_id": "task_002",
      "step_index": 2,
      "name": "create_schedule",
      "task_type": "calendar_action",
      "objective": "Create the calendar event.",
      "assigned_agent_type": "schedule_manager",
      "required_tools": ["calendar_tool"],
      "input_schema": "create_schedule_input",
      "output_schema": "create_schedule_output",
      "depends_on": ["task_001"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["event_id"]
      },
      "status": "pending"
    }
  ],
  "final_validation_rule": {
    "type": "intent_fulfillment_validation",
    "required_outcomes": [
      "calendar_event_created",
      "reminder_created"
    ]
  }
}
```

### 4.2 Agent-Creation Workflow Schema

```json
{
  "workflow_id": "wf_002",
  "workflow_type": "agent_creation",
  "source_intent_id": "intent_002",
  "name": "create_schedule_agent_workflow",
  "status": "draft",
  "version": "1.0.0",
  "goal": "Create a new schedule manager agent.",
  "steps": [
    {
      "task_id": "task_001",
      "step_index": 1,
      "name": "collect_requirements",
      "task_type": "requirement_collection",
      "objective": "Collect missing information for agent creation.",
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
        "required_fields": ["agent_role", "required_capabilities"]
      },
      "status": "pending"
    },
    {
      "task_id": "task_002",
      "step_index": 2,
      "name": "generate_blueprint",
      "task_type": "blueprint_generation",
      "objective": "Generate blueprint for the new agent type.",
      "assigned_agent_type": "blueprint_designer_agent",
      "required_tools": [],
      "input_schema": "blueprint_generation_input",
      "output_schema": "blueprint_output",
      "depends_on": ["task_001"],
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
      "objective": "Check whether required tools exist or need to be generated.",
      "assigned_agent_type": "tool_manager_agent",
      "required_tools": [],
      "input_schema": "tool_resolution_input",
      "output_schema": "tool_resolution_output",
      "depends_on": ["task_002"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["resolved_tools"]
      },
      "status": "pending"
    },
    {
      "task_id": "task_004",
      "step_index": 4,
      "name": "register_artifacts",
      "task_type": "artifact_registration",
      "objective": "Register blueprint, workflow, and generated tools.",
      "assigned_agent_type": "artifact_manager_agent",
      "required_tools": [],
      "input_schema": "artifact_registration_input",
      "output_schema": "artifact_registration_output",
      "depends_on": ["task_003"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["registered_artifact_ids"]
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

### 4.3 Workflow Rules

Mandatory rules:
- `workflow_type` must be one of:
  - `business_execution`
  - `agent_creation`
- every step must have:
  - `task_id`
  - `step_index`
  - `task_type`
  - `objective`
  - `assigned_agent_type`
  - `input_schema`
  - `output_schema`
  - `validation_rule`
- final workflow must define `final_validation_rule`

---

## 5. Mandatory JSON Rule: Workflow Task

A workflow task is the smallest traceable execution unit.

### 5.1 Task Schema

```json
{
  "task_id": "task_001",
  "step_index": 1,
  "name": "collect_requirements",
  "task_type": "requirement_collection",
  "objective": "Collect all required information for creating the new tool.",
  "assigned_agent_type": "planner_agent",
  "assigned_agent_id": null,
  "required_tools": [],
  "input_schema": "tool_requirement_input",
  "output_schema": "tool_requirement_output",
  "depends_on": [],
  "retry_policy": {
    "max_retries": 2,
    "fallback_allowed": false
  },
  "validation_rule": {
    "type": "step_output_validation",
    "required_fields": [
      "tool_name",
      "tool_purpose",
      "input_contract",
      "output_contract"
    ]
  },
  "status": "pending"
}
```

### 5.2 Task Rules

Mandatory rules:
- task must be independently traceable
- task must be independently retryable
- task must be independently validatable
- task must record both `assigned_agent_type` and `assigned_agent_id`
- task must not be an untyped free-text step

---

## 6. Mandatory JSON Rule: Blueprint

Blueprint defines the structured runtime definition of an agent type.

### 6.1 Blueprint Schema

```json
{
  "blueprint_id": "bp_schedule_manager_v1",
  "blueprint_type": "agent_blueprint",
  "version": "1.0.0",
  "agent_role": "schedule_manager",
  "description": "Manage calendar events and reminders.",
  "supported_intents": [
    "manage_schedule",
    "create_reminder",
    "update_schedule"
  ],
  "capabilities": [
    "resolve_schedule_request",
    "create_calendar_event",
    "update_calendar_event",
    "create_reminder"
  ],
  "tool_requirements": [
    {
      "tool_name": "calendar_tool",
      "required": true,
      "creation_policy": "prebuilt_or_runtime_generated"
    },
    {
      "tool_name": "reminder_tool",
      "required": true,
      "creation_policy": "prebuilt_or_runtime_generated"
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
    "fallback_agent_role": "planner_agent",
    "trace_required": true,
    "step_validation_required": true
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

### 6.2 Blueprint Rules

Mandatory rules:
- blueprint defines an agent type, not an agent instance
- blueprint must be versioned
- blueprint must declare capabilities
- blueprint must declare tool requirements
- blueprint must define input and output contracts
- blueprint must define execution policies
- blueprint must be serializable and registrable

---

## 7. Mandatory JSON Rule: Agent

Agent is the runtime instance created from blueprint.

### 7.1 Agent Schema

```json
{
  "agent_id": "agent_schedule_001",
  "agent_type": "schedule_manager",
  "blueprint_id": "bp_schedule_manager_v1",
  "workflow_id": "wf_001",
  "current_task_id": "task_002",
  "state": "active",
  "capability_snapshot": [
    "create_calendar_event",
    "create_reminder"
  ],
  "resolved_tools": [
    "calendar_tool",
    "reminder_tool"
  ],
  "runtime_context_ref": {
    "session_id": "session_001",
    "task_session_id": "task_session_001"
  },
  "created_at": "2026-04-23T10:00:00Z",
  "updated_at": "2026-04-23T10:01:00Z"
}
```

### 7.2 Agent Rules

Mandatory rules:
- agent must reference exactly one blueprint
- agent must be a runtime object
- agent must have explicit state
- agent must track current task assignment
- agent must not exist without blueprint binding
- agent may be created dynamically during workflow execution

---

## 8. Mandatory JSON Rule: Trace

Trace is the structured execution evidence for every important task.

### 8.1 Trace Schema

```json
{
  "trace_id": "trace_001",
  "workflow_id": "wf_001",
  "task_id": "task_002",
  "step_index": 2,
  "intent_id": "intent_001",
  "agent_id": "agent_schedule_001",
  "agent_type": "schedule_manager",
  "blueprint_id": "bp_schedule_manager_v1",
  "tool_calls": [
    {
      "tool_name": "calendar_tool",
      "status": "success",
      "input_ref": "tool_input_001",
      "output_ref": "tool_output_001"
    }
  ],
  "task_input": {
    "person_id": "father_001",
    "date": "2026-04-30",
    "event": "go to Osaka"
  },
  "task_output": {
    "event_id": "evt_123"
  },
  "validation_result": {
    "step_goal_met": true,
    "schema_valid": true
  },
  "retry_count": 0,
  "fallback_used": false,
  "status": "success",
  "error_reason": null,
  "started_at": "2026-04-23T10:01:00Z",
  "finished_at": "2026-04-23T10:01:03Z"
}
```

### 8.2 Trace Rules

Mandatory rules:
- every important task must generate a trace
- trace must be machine-readable
- trace must capture:
  - intent
  - workflow
  - task
  - agent
  - blueprint
  - tool calls
  - input
  - output
  - validation
  - retry
  - fallback
  - error
- trace must not be replaced by plain logs only

---

## 9. Mandatory JSON Rule: Tool

Tool must also be explicitly structured.

### 9.1 Tool Schema

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

### 9.2 Tool Rules

Mandatory rules:
- tool must define input and output contracts
- tool must define implementation type
- tool must define execution mode
- tool must define dependency requirements
- tool may be prebuilt or runtime-generated

Allowed `implementation_type` values:
- `prebuilt`
- `generated_code`
- `external_adapter`

Allowed `execution_mode` values:
- `local_runtime`
- `remote_api`
- `sandbox_runtime`

---

## 10. Can Tool Be Created at Runtime?

Yes. NestHub should support both modes.

### 10.1 Prebuilt Tool Mode

Example:
- calendar_tool already exists
- reminder_tool already exists

In this mode:
- blueprint resolves a known tool
- workflow can execute immediately

### 10.2 Runtime Tool Generation Mode

Example:
User says:
- "Create a calendar tool"
- "Build a schedule tool for my family"
- "I need a custom calendar integration tool"

In this mode, NestHub must:

1. recognize the tool-creation intent or agent-creation intent
2. collect missing tool requirements
3. generate tool specification
4. generate tool code
5. generate tool schema
6. validate tool build result
7. register the tool
8. allow future blueprints and agents to use it

Therefore:

- tool does NOT have to be fully prebuilt
- NestHub should be able to create tools at runtime
- generated tool must still follow the same structured tool contract

---

## 11. Tool Creation Workflow

If the user says:
- "Create a calendar tool"

the runtime should follow this pattern.

### 11.1 Example Intent

```json
{
  "intent_id": "intent_010",
  "intent_type": "agent_creation_intent",
  "name": "create_tool",
  "entities": {
    "tool_name": "calendar_tool",
    "tool_domain": "calendar_management"
  },
  "expected_outcome": [
    "tool_spec_created",
    "tool_code_generated",
    "tool_registered"
  ],
  "requires_clarification": true,
  "clarification_questions": [
    "What calendar backend should be supported?",
    "Should the tool support create/update/delete/query?",
    "Should reminders be included?"
  ],
  "source_text": "Create a calendar tool for me."
}
```

### 11.2 Example Workflow

```json
{
  "workflow_id": "wf_tool_001",
  "workflow_type": "agent_creation",
  "source_intent_id": "intent_010",
  "name": "create_calendar_tool_workflow",
  "goal": "Create and register a new calendar tool.",
  "steps": [
    {
      "task_id": "task_001",
      "step_index": 1,
      "name": "collect_tool_requirements",
      "task_type": "requirement_collection",
      "objective": "Collect all required details for the new tool.",
      "assigned_agent_type": "planner_agent",
      "required_tools": [],
      "input_schema": "tool_requirement_input",
      "output_schema": "tool_requirement_output",
      "depends_on": [],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": false
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": [
          "tool_name",
          "input_contract",
          "output_contract",
          "feature_scope"
        ]
      },
      "status": "pending"
    },
    {
      "task_id": "task_002",
      "step_index": 2,
      "name": "generate_tool_spec",
      "task_type": "spec_generation",
      "objective": "Generate the structured specification for the tool.",
      "assigned_agent_type": "tool_designer_agent",
      "required_tools": [],
      "input_schema": "tool_spec_input",
      "output_schema": "tool_spec_output",
      "depends_on": ["task_001"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "schema_validation",
        "schema_name": "tool_schema"
      },
      "status": "pending"
    },
    {
      "task_id": "task_003",
      "step_index": 3,
      "name": "generate_tool_code",
      "task_type": "code_generation",
      "objective": "Generate runnable tool code.",
      "assigned_agent_type": "codegen_agent",
      "required_tools": [],
      "input_schema": "tool_codegen_input",
      "output_schema": "tool_codegen_output",
      "depends_on": ["task_002"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["file_paths", "entrypoint"]
      },
      "status": "pending"
    },
    {
      "task_id": "task_004",
      "step_index": 4,
      "name": "validate_and_register_tool",
      "task_type": "artifact_registration",
      "objective": "Validate and register the generated tool.",
      "assigned_agent_type": "artifact_manager_agent",
      "required_tools": [],
      "input_schema": "tool_registration_input",
      "output_schema": "tool_registration_output",
      "depends_on": ["task_003"],
      "retry_policy": {
        "max_retries": 2,
        "fallback_allowed": true
      },
      "validation_rule": {
        "type": "step_output_validation",
        "required_fields": ["tool_registered"]
      },
      "status": "pending"
    }
  ],
  "final_validation_rule": {
    "type": "intent_fulfillment_validation",
    "required_outcomes": [
      "tool_spec_created",
      "tool_code_generated",
      "tool_registered"
    ]
  }
}
```

---

## 12. Execution Rule for Agent-Creation Intent

When `intent_type = agent_creation_intent`, the system must execute this sequence:

1. collect missing requirements
2. create or refine blueprint
3. create workflow for building the new runtime capability
4. resolve whether tools already exist
5. generate missing tools if needed
6. validate blueprint
7. validate workflow
8. register generated artifacts
9. instantiate the runtime agent if activation is requested

Important:
- agent creation must itself follow intent → workflow → task → trace → validation
- meta-creation flow must obey the same execution discipline as normal flow

---

## 13. Final Mandatory Principles

### 13.1 Core rules

- every important object must have typed JSON structure
- every workflow must be traceable
- every task must be validatable
- every agent must be blueprint-bound
- every blueprint must declare tool requirements
- every tool must declare contracts
- every runtime-generated artifact must be registrable

### 13.2 Tool creation rule

NestHub is allowed to create tools at runtime.

This is not optional in the long-term architecture.

That means:
- NestHub may ask the user for the missing requirements of the tool
- NestHub may generate schema, code, and registration artifacts
- NestHub may then bind the new tool into future blueprints and workflows

### 13.3 Final mapping

- Intent = target
- Workflow = path
- Task = smallest traceable step
- Blueprint = role definition
- Agent = runtime executor
- Tool = executable capability unit
- Trace = execution evidence
- Validation = correctness gate

Any implementation that violates this mapping must be considered incorrect.
