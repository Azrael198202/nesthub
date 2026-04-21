from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.services.execution_handler_registry import (
    ExecutionHandlerPluginManifest,
    ExecutionHandlerPluginStepSpec,
)
from nethub_runtime.core.services.execution_step_handlers import (
    handle_reminder_create_trigger_step,
    handle_schedule_availability_query_step,
    handle_schedule_record_source_check_step,
    handle_travel_itinerary_generation_step,
)
from nethub_runtime.core.utils.id_generator import generate_id


_KNOWN_SCHEDULE_HANDLERS = {
    "schedule_record_source_check",
    "schedule_availability_query",
    "travel_itinerary_generation",
    "reminder_create_trigger",
}


def _workflow_plan_from_task(task: TaskSchema) -> list[dict[str, str]]:
    metadata = dict(task.metadata or {})
    cap = dict(metadata.get("capability_orchestration") or {})
    plan = cap.get("workflow_plan")
    if not isinstance(plan, list):
        request_plan = dict(metadata.get("request_plan") or {})
        cap = dict(request_plan.get("capability_orchestration") or {})
        plan = cap.get("workflow_plan")
    if not isinstance(plan, list):
        return []

    out: list[dict[str, str]] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        label = str(item.get("label") or "").strip() or name.replace("_", " ").title()
        preview = str(item.get("preview") or "").strip()
        kind = str(item.get("kind") or "").strip().lower()
        out.append({"name": name, "label": label, "preview": preview, "kind": kind})
    return out


def _runtime_io_contract(step_name: str) -> tuple[list[str], list[str]]:
    contracts = {
        "schedule_record_source_check": (["session_state", "knowledge_store"], ["sources", "records_count", "knowledge_hits", "message"]),
        "schedule_availability_query": (["input_text", "session_state", "sources"], ["target_date", "available", "reason", "message"]),
        "travel_itinerary_generation": (["input_text", "availability"], ["itinerary", "model_source", "summary", "message"]),
        "reminder_create_trigger": (["input_text", "session_state", "itinerary"], ["reminder", "saved", "total_records", "message"]),
    }
    return contracts.get(step_name, (["input_text", "session_state"], ["message"]))


def _runtime_executor(step_name: str) -> str:
    if step_name in _KNOWN_SCHEDULE_HANDLERS:
        return "tool"
    return "llm"


class ScheduleTaskDecomposerPlugin:
    priority = 110

    def match(self, task: TaskSchema) -> bool:
        return task.intent == "schedule_create"

    def run(self, task: TaskSchema) -> list[SubTask]:
        plan = _workflow_plan_from_task(task)
        if not plan:
            return [SubTask(subtask_id=generate_id("subtask"), name="single_step", goal="Handle schedule request via generic runtime step.")]
        return [
            SubTask(
                subtask_id=generate_id("subtask"),
                name=item["name"],
                goal=item["preview"] or item["label"] or f"Execute runtime step {item['name']}.",
            )
            for item in plan
        ]


class ScheduleWorkflowPlannerPlugin:
    priority = 110

    def match(self, task: TaskSchema, subtasks: list[SubTask]) -> bool:
        return task.intent == "schedule_create" and bool(subtasks)

    def run(self, task: TaskSchema, _subtasks: list[SubTask]) -> WorkflowSchema:
        plan = _workflow_plan_from_task(task)
        if not plan:
            plan = [{"name": item.name, "label": item.name.replace("_", " ").title(), "preview": item.goal, "kind": "local"} for item in _subtasks]
        steps: list[WorkflowStepSchema] = []
        prev_step_id: str | None = None
        for item in plan:
            name = item["name"]
            inputs, outputs = _runtime_io_contract(name)
            step_id = generate_id("step")
            steps.append(
                WorkflowStepSchema(
                    step_id=step_id,
                    name=name,
                    task_type=task.intent,
                    executor_type=_runtime_executor(name),
                    inputs=inputs,
                    outputs=outputs,
                    depends_on=[prev_step_id] if prev_step_id else [],
                    retry=0,
                    metadata={
                        "goal": item["preview"] or f"Execute runtime step {name}.",
                        "display_label": item["label"],
                        "selection_basis": "runtime_workflow_plan",
                        "runtime_step_kind": item.get("kind", ""),
                    },
                )
            )
            prev_step_id = step_id

        return WorkflowSchema(
            workflow_id=generate_id("workflow"),
            task_id=task.task_id,
            mode="normal",
            steps=steps,
            composition={
                "plugin": "schedule_runtime_plugin",
                "intent": task.intent,
                "runtime_generated": True,
                "source": "core_plus.request_plan.capability_orchestration.workflow_plan",
            },
        )


class ScheduleExecutionHandlerPlugin:
    def build_manifest(self, coordinator: Any) -> ExecutionHandlerPluginManifest:
        return ExecutionHandlerPluginManifest(
            name="schedule_runtime_plugin",
            version="1.0",
            steps=[
                ExecutionHandlerPluginStepSpec(
                    executor_type="tool",
                    step_name="schedule_record_source_check",
                    handler=lambda step, task, context, step_outputs: handle_schedule_record_source_check_step(
                        coordinator, step, task, context, step_outputs
                    ),
                    description="Check schedule/reminder record source readiness.",
                ),
                ExecutionHandlerPluginStepSpec(
                    executor_type="tool",
                    step_name="schedule_availability_query",
                    handler=lambda step, task, context, step_outputs: handle_schedule_availability_query_step(
                        coordinator, step, task, context, step_outputs
                    ),
                    description="Query whether target date is already booked.",
                ),
                ExecutionHandlerPluginStepSpec(
                    executor_type="tool",
                    step_name="travel_itinerary_generation",
                    handler=lambda step, task, context, step_outputs: handle_travel_itinerary_generation_step(
                        coordinator, step, task, context, step_outputs
                    ),
                    description="Generate Osaka day itinerary with model source trace.",
                ),
                ExecutionHandlerPluginStepSpec(
                    executor_type="tool",
                    step_name="reminder_create_trigger",
                    handler=lambda step, task, context, step_outputs: handle_reminder_create_trigger_step(
                        coordinator, step, task, context, step_outputs
                    ),
                    description="Create departure reminder entry.",
                ),
            ],
        )


def schedule_task_decomposer_plugin() -> ScheduleTaskDecomposerPlugin:
    return ScheduleTaskDecomposerPlugin()


def schedule_workflow_planner_plugin() -> ScheduleWorkflowPlannerPlugin:
    return ScheduleWorkflowPlannerPlugin()


def schedule_execution_handler_plugin() -> ScheduleExecutionHandlerPlugin:
    return ScheduleExecutionHandlerPlugin()
