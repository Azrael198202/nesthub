# core-brain-implementation.md (Execution-Ready, Codex-Friendly)

## 0. Goal

Build core-brain that can:

- Run via TVBox chat interface
- Use local LLM first, fallback to external APIs
- Perform intent analysis + workflow decomposition
- Manage 5-layer context system
- Support RAG (Weaviate)
- Generate code / configs / workflows automatically
- Auto-register and run generated artifacts

---

## 1. Tech Stack (STRICT)

backend: FastAPI  
llm_router: LiteLLM  
workflow_engine: LangGraph  
vector_db: Weaviate  
relational_db: PostgreSQL + pgvector  
cache: Redis  
search: Elasticsearch  
local_llm: Ollama  
external_llm: OpenAI / Groq / Gemini / Anthropic  

---

## 2. Key Principle

NEVER hardcode logic. EVERYTHING must be config-driven.

---

## 3. Directory Structure

core-brain/
├── app/
│   ├── main.py
│   ├── tvbox_api.py
│   ├── router.py
│   ├── engine/
│   │   ├── intent_engine.py
│   │   ├── workflow_engine.py
│   │   ├── codegen_engine.py
├── configs/
├── generated/
└── scripts/

---

## 4. TVBox API

```python
from fastapi import APIRouter
from pydantic import BaseModel
from app.engine.intent_engine import run_pipeline

router = APIRouter()

class ChatRequest(BaseModel):
    text: str
    session_id: str = "default"

@router.post("/chat")
async def chat(req: ChatRequest):
    # Entry point for TVBox interaction
    result = await run_pipeline(req.text, req.session_id)
    return {"reply": result}
```

---

## 5. LLM Router (Local + Fallback)

```python
from litellm import completion

async def call_llm(model_config, messages):
    # Try local model first
    try:
        return completion(model=model_config["model"], messages=messages)

    except Exception:
        # fallback to external model
        fallback = model_config.get("fallback")
        return completion(model=fallback, messages=messages)
```

---

## 6. Intent Engine

```python
async def analyze_intent(text, model_config):
    messages = [
        {"role": "system", "content": "Extract intent in JSON."},
        {"role": "user", "content": text}
    ]
    return await call_llm(model_config, messages)
```

---

## 7. Workflow Engine (Fallback)

```python
async def generate_workflow(intent):
    try:
        workflow = call_local_model(intent)
        validate(workflow)
        return workflow
    except:
        return call_external_model(intent)
```

---

## 8. CodeGen Engine

```python
class CodeGenEngine:

    async def generate_all(self, intent):
        workflow = await self.generate_workflow(intent)
        blueprint = await self.generate_blueprint(workflow)
        code = await self.generate_code(blueprint)
        self.save_all(workflow, blueprint, code)
```

---

## 9. Model Config (Fallback Enabled)

configs/models/intent.yaml

name: intent-model  
provider: ollama  
model: qwen3:4b  
fallback: gpt-4o  

---

## 10. Context Layers

1. System Context  
2. Session Context  
3. Task Context  
4. Long-term Memory (RAG)  
5. Execution Context  

---

## 11. RAG

```python
def retrieve_memory(query):
    return weaviate.search(query)
```

---

## 12. Auto Generation Flow

User Input → Intent → RAG → Workflow → CodeGen → Register → Run

---

## 13. LoRA Support

```python
def apply_lora(model_config):
    if model_config.get("lora"):
        load_adapter(model_config["lora"])
```

---

## 14. FINAL TARGET

User: Build accounting system

→ AI generates:
- workflow
- DB schema
- API
- runnable system

---

## 15. External API Fallback Rule

For intent analysis and workflow decomposition, the system must use a strong external API as a fallback when:
- the local model fails
- the local model returns invalid JSON
- the confidence is below threshold
- the workflow structure is incomplete
- the result does not pass schema validation

Recommended fallback order:
1. OpenAI
2. Anthropic
3. Gemini
4. Groq

All code comments must be written in English.


---

## 16. Core Concept Model (ROOT PRINCIPLE FOR CODEX)

This section is a mandatory conceptual contract for all future coding.
Codex, Claude Code, and any developer must follow these definitions strictly.

### 16.1 Intent

Intent is the structured representation of the user's goal.

Rules:
- Intent describes what the user wants to achieve
- Intent does not describe execution order
- Intent must be represented in structured JSON
- Intent is the root of workflow generation
- Final success must be validated against intent, not only against intermediate outputs

Example:

```json
{
  "intent": "manage_schedule",
  "entities": {
    "person": "father",
    "date": "next Tuesday",
    "event": "go to Osaka",
    "reminder": "one day before"
  },
  "expected_outcome": [
    "calendar_event_created",
    "reminder_created"
  ]
}
```

### 16.2 Workflow

Workflow is the execution plan generated from the intent.

Rules:
- Workflow describes how the system will try to achieve the intent
- Workflow is composed of ordered or graph-based steps
- Each step has a clear objective, input, output, and validation condition
- Workflow is generated dynamically from intent and context
- Workflow is not the same as agent
- Workflow is not the same as blueprint

Example:

```json
{
  "workflow_id": "wf_001",
  "intent": "manage_schedule",
  "steps": [
    {"id": "step_1", "action": "resolve_person"},
    {"id": "step_2", "action": "parse_date"},
    {"id": "step_3", "action": "create_schedule"},
    {"id": "step_4", "action": "create_reminder"},
    {"id": "step_5", "action": "validate_result"}
  ]
}
```

### 16.3 Blueprint

Blueprint is the structured runtime definition of an agent type.

Definition:
- Blueprint defines the role, capabilities, tools, input/output contracts, execution policies, and collaboration rules of an agent type

Rules:
- Blueprint is NOT a running agent instance
- Blueprint is NOT the workflow itself
- Blueprint is NOT only a prompt
- Blueprint is the reusable definition used to create agent instances at runtime
- Blueprint must be config-driven and serializable
- Blueprint must support registration, versioning, and replacement

Example:

```json
{
  "blueprint_id": "bp_schedule_manager_v1",
  "agent_type": "schedule_manager",
  "description": "Manage calendar events and reminders.",
  "supported_intents": [
    "manage_schedule",
    "create_reminder",
    "update_schedule"
  ],
  "tools": [
    "calendar_tool",
    "reminder_tool"
  ],
  "input_schema": "schedule_task_input",
  "output_schema": "schedule_task_output",
  "policies": {
    "retry": 2,
    "fallback_agent": "planner_agent"
  }
}
```

### 16.4 Agent

Agent is a runtime execution role instantiated from a blueprint.

Rules:
- Agent is a runtime object
- Agent is created dynamically when needed
- Agent is assigned to workflow steps or tasks
- Agent must reference a blueprint
- Agent state must be persisted when necessary
- Agent is not defined by hardcoded business logic
- Agent behavior must be constrained by blueprint + workflow + tools + policies

Example:

```json
{
  "agent_id": "agent_schedule_001",
  "blueprint_id": "bp_schedule_manager_v1",
  "workflow_id": "wf_001",
  "status": "running",
  "assigned_steps": ["step_3", "step_4"]
}
```

### 16.5 Trace

Trace is the structured execution evidence of workflow steps.

Rules:
- Trace is mandatory for every important workflow step
- Trace is not plain text log only
- Trace must capture step goal, input, output, assigned agent, validation result, retry count, fallback status, and error reason
- Trace must support debugging, replay, auditing, and evaluation
- Trace must be machine-readable

Example:

```json
{
  "trace_id": "trace_001",
  "workflow_id": "wf_001",
  "step_id": "step_3",
  "agent_id": "agent_schedule_001",
  "input": {
    "person": "father",
    "date": "2026-04-28",
    "event": "go to Osaka"
  },
  "output": {
    "calendar_event_id": "evt_123"
  },
  "status": "success",
  "validation": {
    "step_goal_met": true
  }
}
```

### 16.6 Validation Model

Validation must happen at two levels.

#### Step-level validation
Check whether the current workflow step produced the expected output.

Rules:
- Validate schema
- Validate business completeness
- Validate tool execution result
- Validate whether the step objective was met
- Retry or fallback if validation fails

#### Intent-level validation
Check whether the final workflow result actually satisfies the original user intent.

Rules:
- Final success is defined by intent fulfillment
- Even if many steps succeeded, the final result can still fail
- Missing required outcomes means intent failure
- Final output must be checked against expected_outcome

### 16.7 Operational Relationship

The mandatory system relationship is:

User Input
→ Intent Analysis
→ Workflow Generation
→ Step Assignment
→ Agent Execution
→ Trace Recording
→ Step Validation
→ Final Intent Validation
→ Response / Writeback / Memory Update

The following mapping is mandatory:

- Intent = target
- Workflow = path
- Blueprint = role definition
- Agent = runtime executor
- Trace = execution evidence
- Validation = quality gate

### 16.8 Coding Rules for Codex

Codex must follow these rules:

1. Do not confuse workflow with blueprint
2. Do not treat blueprint as a running agent
3. Do not hardcode agent behavior directly in business code
4. Do not skip trace creation for workflow execution
5. Do not judge final success only by intermediate step success
6. Do not create agent instances without blueprint binding
7. Do not store long-term memory as raw chat history only
8. Do not place intent, workflow, agent, and trace in the same untyped structure
9. All major structures must have schemas
10. All major execution nodes must be observable and debuggable

### 16.9 Architecture Principle

The architecture principle is:

- Intent decides the target
- Workflow decides the execution path
- Blueprint defines the executable role contract
- Agent executes runtime tasks
- Trace makes execution observable
- Validation guarantees correctness

This principle is the root contract for all future code generation.
Any generated code violating this principle must be considered incorrect.

