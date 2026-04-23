# core-brain-codex-execution-checklist.md
Updated: 2026-04-23

## 0. Purpose

This document is the **Codex execution checklist** for refactoring the current `nethub_runtime` codebase.
It converts the architectural patch into **direct implementation actions**.

This document must be used together with:

- `core-brain-implementation-v2.md`
- `core-brain-refactor-patch.md`

All code comments must be written in English.

---

## 1. Execution Mode

Codex must process this refactor in the following order:

1. Create missing target directories
2. Create shared contracts
3. Consolidate entry points
4. Move and split logic
5. Remove duplicated legacy structure
6. Add missing runtime subsystems
7. Add lifecycle artifact management
8. Verify imports, routing, and execution flow
9. Run smoke tests

Do not refactor everything in one uncontrolled pass.
Use incremental commits or checkpoints.

---

## 2. Global Rules

1. Do not keep `nethub_runtime/core/` as a second formal brain
2. Do not keep `nethub_runtime/core_brain/app/`
3. Do not mix provider runtime logic into semantic LLM logic
4. Do not leave workflow orchestration hidden inside `chat/`
5. Do not keep KB as placeholder-only
6. Do not keep generated artifacts without lifecycle state
7. Do not mix blueprint mechanism and blueprint artifact storage
8. Do not leave major internal boundaries as raw untyped dicts
9. Do not skip trace and validation integration
10. All code comments must be in English

---

## 3. Directory Actions

### 3.1 Create directories

Codex must create the following directories if missing:

```text
nethub_runtime/core_brain/api/
nethub_runtime/core_brain/contracts/
nethub_runtime/core_brain/brain/orchestration/
nethub_runtime/core_brain/brain/planning/
nethub_runtime/core_brain/brain/execution/
nethub_runtime/core_brain/brain/artifacts/
nethub_runtime/core_brain/brain/agents/registry/
nethub_runtime/core_brain/brain/agents/manager/
nethub_runtime/core_brain/brain/agents/scheduler/
nethub_runtime/core_brain/brain/agents/state/
nethub_runtime/core_brain/brain/trace/recorder/
nethub_runtime/core_brain/brain/trace/store/
nethub_runtime/core_brain/brain/trace/evaluator/
nethub_runtime/core_brain/brain/trace/replay/
nethub_runtime/core_brain/brain/validation/schemas/
nethub_runtime/core_brain/brain/validation/step/
nethub_runtime/core_brain/brain/validation/intent/
nethub_runtime/core_brain/brain/validation/result/
nethub_runtime/core_brain/brain/workflows/planner/
nethub_runtime/core_brain/brain/workflows/executor/
nethub_runtime/core_brain/brain/workflows/registry/
nethub_runtime/core_brain/brain/workflows/state/
nethub_runtime/core_brain/brain/workflows/builder/
nethub_runtime/core_brain/brain/kb/intent_kb/
nethub_runtime/core_brain/brain/kb/workflow_kb/
nethub_runtime/core_brain/brain/kb/blueprint_kb/
nethub_runtime/core_brain/brain/kb/retrieval/
nethub_runtime/models/providers/
nethub_runtime/models/router/
nethub_runtime/models/runtime/
nethub_runtime/models/health/
nethub_runtime/blueprints_core/
nethub_runtime/generated/drafts/
nethub_runtime/generated/registered/
nethub_runtime/generated/active/
nethub_runtime/generated/failed/
nethub_runtime/generated/archive/
```

### 3.2 Remove directories

Codex must remove these directories after logic migration is complete:

```text
nethub_runtime/core/
nethub_runtime/core_brain/app/
```

Do not remove them before imports and routes are fully migrated.

### 3.3 Keep directories but enforce strict role boundaries

Keep these directories, but do not change their meaning casually:

```text
nethub_runtime/tools/
nethub_runtime/runtime/
nethub_runtime/capability/
nethub_runtime/environment/
nethub_runtime/tvbox/
nethub_runtime/integrations/
```

---

## 4. File-Level Actions

### 4.1 Create new core brain main entry

Create:

```text
nethub_runtime/core_brain/main.py
```

Responsibilities:
- Create the FastAPI app for core-brain
- Mount routes from `core_brain/api/`
- Expose the only formal brain-facing API entry
- Replace old `core/` and `core_brain/app/` entry logic

Do not place heavy business logic in this file.

---

### 4.2 Create contracts

Create these files:

```text
nethub_runtime/core_brain/contracts/request.py
nethub_runtime/core_brain/contracts/response.py
nethub_runtime/core_brain/contracts/intent.py
nethub_runtime/core_brain/contracts/workflow.py
nethub_runtime/core_brain/contracts/route.py
nethub_runtime/core_brain/contracts/memory.py
nethub_runtime/core_brain/contracts/artifact.py
nethub_runtime/core_brain/contracts/agent.py
nethub_runtime/core_brain/contracts/blueprint.py
nethub_runtime/core_brain/contracts/trace.py
nethub_runtime/core_brain/contracts/validation.py
```

Requirements:
- Use typed DTOs or typed models
- Minimize raw dict usage across module boundaries
- Make TVBox payload conversion terminate into typed request/response models

---

### 4.3 Create API route modules

Create:

```text
nethub_runtime/core_brain/api/chat.py
nethub_runtime/core_brain/api/health.py
```

Optional later:
```text
nethub_runtime/core_brain/api/routes.py
```

Responsibilities:
- HTTP request mapping
- DTO conversion
- Pass typed requests into brain orchestration
- Return typed response payloads

Do not place planning or execution logic here.

---

### 4.4 Refactor chat layer

Keep:
```text
nethub_runtime/core_brain/brain/chat/
```

Limit this layer to:
- request adapters
- response builders
- thin facade

Codex must move heavy logic out of chat into:
- orchestration/
- planning/
- execution/
- memory/
- artifacts/

---

### 4.5 Add orchestration layer

Create files such as:

```text
nethub_runtime/core_brain/brain/orchestration/service.py
nethub_runtime/core_brain/brain/orchestration/pipeline.py
```

Responsibilities:
- Main end-to-end coordination
- Stage ordering
- Fallback escalation coordination
- Final response assembly orchestration

---

### 4.6 Add planning layer

Create files such as:

```text
nethub_runtime/core_brain/brain/planning/intent_service.py
nethub_runtime/core_brain/brain/planning/workflow_service.py
nethub_runtime/core_brain/brain/planning/route_service.py
```

Responsibilities:
- Intent analysis
- Workflow planning
- Task-to-model-profile selection
- Planning-time decision making

---

### 4.7 Add execution layer

Create files such as:

```text
nethub_runtime/core_brain/brain/execution/step_executor.py
nethub_runtime/core_brain/brain/execution/tool_executor.py
nethub_runtime/core_brain/brain/execution/agent_executor.py
```

Responsibilities:
- Execute workflow steps
- Invoke tools
- Invoke runtime agents
- Collect execution evidence

---

### 4.8 Refactor workflows into formal subsystem

Create or move files into:

```text
nethub_runtime/core_brain/brain/workflows/planner/
nethub_runtime/core_brain/brain/workflows/executor/
nethub_runtime/core_brain/brain/workflows/registry/
nethub_runtime/core_brain/brain/workflows/state/
nethub_runtime/core_brain/brain/workflows/builder/
```

Move current lightweight workflow logic here.

Codex must ensure:
- workflow planning is explicit
- workflow execution is explicit
- workflow state is persisted
- retry / resume is supported structurally

---

### 4.9 Add agent runtime subsystem

Create files such as:

```text
nethub_runtime/core_brain/brain/agents/registry/service.py
nethub_runtime/core_brain/brain/agents/manager/service.py
nethub_runtime/core_brain/brain/agents/scheduler/service.py
nethub_runtime/core_brain/brain/agents/state/store.py
```

Responsibilities:
- Instantiate runtime agents from blueprints
- Bind agents to workflow steps
- Manage runtime state
- Track active / idle / failed agents

---

### 4.10 Add trace subsystem

Create files such as:

```text
nethub_runtime/core_brain/brain/trace/recorder/service.py
nethub_runtime/core_brain/brain/trace/store/repository.py
nethub_runtime/core_brain/brain/trace/evaluator/service.py
nethub_runtime/core_brain/brain/trace/replay/service.py
```

Responsibilities:
- Record structured traces
- Store traces
- Evaluate step-level success
- Support replay / audit

Codex must not replace this with plain text logs.

---

### 4.11 Add validation subsystem

Create files such as:

```text
nethub_runtime/core_brain/brain/validation/schemas/service.py
nethub_runtime/core_brain/brain/validation/step/service.py
nethub_runtime/core_brain/brain/validation/intent/service.py
nethub_runtime/core_brain/brain/validation/result/service.py
```

Responsibilities:
- Schema validation
- Step-level validation
- Intent-level validation
- Final result validation

---

### 4.12 Upgrade KB from placeholder

Refactor or create:

```text
nethub_runtime/core_brain/brain/kb/intent_kb/
nethub_runtime/core_brain/brain/kb/workflow_kb/
nethub_runtime/core_brain/brain/kb/blueprint_kb/
nethub_runtime/core_brain/brain/kb/retrieval/
```

Codex must provide minimum viable retrieval logic.
Do not leave KB as empty placeholders after refactor.

---

### 4.13 Refactor models layer

Move or split current model logic into:

```text
nethub_runtime/models/providers/
nethub_runtime/models/router/
nethub_runtime/models/runtime/
nethub_runtime/models/health/
```

Responsibilities:
- providers/: provider abstraction and concrete providers
- router/: fallback, cooldown, retry, timeout, route transport logic
- runtime/: low-level completion / structured completion runtime
- health/: provider availability and health checks

Important:
- Prompt registry must not remain here
- Schema registry must not remain here
- Semantic task model choice must not remain here

---

### 4.14 Keep semantic LLM layer inside core_brain

Refactor or keep:

```text
nethub_runtime/core_brain/brain/llm/
```

Limit it to:
- prompt registry
- schema registry
- task-to-model-profile mapping
- semantic route policies

Codex must remove low-level provider runtime logic from this layer.

---

### 4.15 Rename blueprint mechanism layer

Create:

```text
nethub_runtime/blueprints_core/
```

Move or refactor current blueprint mechanism code here.

Responsibilities:
- blueprint registry
- blueprint loading
- blueprint validation
- blueprint execution metadata support

Generated blueprint outputs must remain under `generated/` as artifact instances.

---

### 4.16 Refactor generated artifact storage

Codex must replace file-type-only generated storage with lifecycle storage:

```text
nethub_runtime/generated/drafts/
nethub_runtime/generated/registered/
nethub_runtime/generated/active/
nethub_runtime/generated/failed/
nethub_runtime/generated/archive/
```

Add artifact manifest support.

Each artifact manifest must contain:
- id
- type
- source_intent
- source_task
- version
- status
- runnable
- registered_at

Recommended extra fields:
- created_at
- updated_at
- blueprint_id
- workflow_id
- session_id
- trace_id
- error_reason
- checksum

---

## 5. Logic Migration Checklist

### 5.1 Entry migration
- [ ] Create `core_brain/main.py`
- [ ] Move brain-facing API app creation into `core_brain/main.py`
- [ ] Move route modules into `core_brain/api/`
- [ ] Update imports that still point to `core/`
- [ ] Remove duplicated entry responsibilities from `core_brain/app/`
- [ ] Remove `core_brain/app/` after migration
- [ ] Remove `core/` after compatibility verification

### 5.2 Chat thinning
- [ ] Identify heavy logic inside `brain/chat/`
- [ ] Move orchestration logic to `brain/orchestration/`
- [ ] Move planning logic to `brain/planning/`
- [ ] Move execution logic to `brain/execution/`
- [ ] Keep `chat/` thin

### 5.3 Workflow promotion
- [ ] Move current workflow helper logic into formal workflow modules
- [ ] Add workflow planning objects
- [ ] Add workflow state persistence
- [ ] Add retry / resume support
- [ ] Add workflow builder logic

### 5.4 LLM separation
- [ ] Move provider runtime logic into `models/`
- [ ] Keep prompt/schema registries in `brain/llm/`
- [ ] Remove provider transport logic from semantic layer
- [ ] Add structured completion boundary

### 5.5 KB implementation
- [ ] Create intent KB retrieval
- [ ] Create workflow KB retrieval
- [ ] Create blueprint KB retrieval
- [ ] Add unified retrieval facade
- [ ] Connect retrieval to planning/context injection

### 5.6 Agent runtime
- [ ] Add blueprint-to-agent instantiation flow
- [ ] Add agent scheduler
- [ ] Add runtime state management
- [ ] Bind agents to workflow steps

### 5.7 Trace and validation
- [ ] Add structured trace recording
- [ ] Add step-level validation
- [ ] Add intent-level validation
- [ ] Bind trace to workflow execution
- [ ] Bind validation to final response correctness

### 5.8 Generated artifacts
- [ ] Add lifecycle directories
- [ ] Add artifact manifest model
- [ ] Add status transitions
- [ ] Preserve failure artifacts for debugging
- [ ] Separate mechanism layer from generated artifact layer

### 5.9 Contracts
- [ ] Create typed DTOs
- [ ] Replace raw dict boundaries gradually
- [ ] Map TVBox request to typed request model
- [ ] Map brain result to typed response model
- [ ] Add workflow / route / trace / validation DTOs

---

## 6. TVBox Compatibility Checklist

Codex must preserve the TVBox main interaction path.

### Must continue working:
- TVBox sends `/api/voice/chat`
- Request reaches core-brain
- Core-brain returns typed result
- TVBox can still update dashboard conversation
- TVBox can still render workflow progress
- TVBox can still extract reply text

### Codex actions:
- [ ] Keep compatibility payload fields if currently used by TVBox
- [ ] Internally map them to typed contracts
- [ ] Avoid breaking the existing dashboard update flow
- [ ] Update compatibility extractors only after response contracts stabilize

---

## 7. Import Rewrite Checklist

Codex must search and update imports referencing:

- `nethub_runtime.core`
- `nethub_runtime.core.main`
- `nethub_runtime.core.services`
- `nethub_runtime.core_brain.app`
- old blueprint mechanism paths
- old generated store assumptions
- old workflow helper locations

Do not leave dead imports after the migration.

---

## 8. Validation and Smoke Tests

Codex must verify the following after refactor:

### 8.1 Import validation
- [ ] No import still depends on removed `core/`
- [ ] No import still depends on removed `core_brain/app/`

### 8.2 App startup validation
- [ ] `nethub_runtime/core_brain/main.py` can create app successfully
- [ ] Routes mount successfully
- [ ] No circular import blocks startup

### 8.3 TVBox smoke test
- [ ] TVBox `/api/voice/chat` still works
- [ ] Core-brain returns a valid response
- [ ] Reply can be extracted
- [ ] Workflow steps can still be displayed

### 8.4 Workflow smoke test
- [ ] Intent can be analyzed
- [ ] Workflow can be built
- [ ] At least one step can be executed
- [ ] Trace is recorded
- [ ] Validation result is produced

### 8.5 Artifact smoke test
- [ ] A generated artifact can enter `drafts/`
- [ ] It can be registered
- [ ] It can be marked `active`
- [ ] Failure path can be recorded

---

## 9. Recommended Commit / Patch Order

Recommended implementation order:

1. contracts
2. core_brain/main.py + api/
3. chat thinning
4. planning / orchestration / execution
5. workflows formal split
6. models split
7. KB minimum implementation
8. agents / trace / validation
9. generated lifecycle
10. remove legacy core and core_brain/app

---

## 10. Final Rule

Codex must treat this checklist as an execution contract, not a suggestion.

If any implementation detail conflicts with the root principle:

- Intent = target
- Workflow = path
- Blueprint = role definition
- Agent = runtime executor
- Trace = execution evidence
- Validation = quality gate

then the implementation must be corrected to follow the root principle.
