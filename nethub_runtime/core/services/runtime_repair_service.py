from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.utils.id_generator import generate_id


class RuntimeRepairService:
    def build_repair_workflow(
        self,
        *,
        task: TaskSchema,
        workflow: WorkflowSchema,
        repair_classification: dict[str, Any],
        enable_autonomous_patch_pipeline: bool = False,
    ) -> WorkflowSchema:
        repaired_steps = list(workflow.steps)
        dependencies = [workflow.steps[-1].step_id] if workflow.steps else []
        repair_actions: list[str] = []

        missing_tools = list(repair_classification.get("missing_tools", []))
        if missing_tools:
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="prepare_runtime_tools",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["session_state"],
                    outputs=["install_plan", "status"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "prepare_missing_tools",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "missing_tools",
                        "missing_tools": missing_tools,
                    },
                )
            )
            repair_actions.append("inject:prepare_runtime_tools")
            dependencies = [repaired_steps[-1].step_id]

        for step_name in repair_classification.get("execution_failures", []):
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name=step_name,
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["input_text", "session_state", "step_outputs"],
                    outputs=["message", "status"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "retry_failed_step",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "failed_step",
                    },
                )
            )
            repair_actions.append(f"retry:{step_name}")
            dependencies = [repaired_steps[-1].step_id]

        missing_outputs = set(repair_classification.get("missing_outputs", []))
        missing_steps = set(repair_classification.get("missing_steps", []))
        if missing_steps.intersection({"analysis", "summary", "insight"}) or missing_outputs.intersection({"analysis", "summary", "insight"}):
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="analyze_workflow_context",
                    task_type=task.intent,
                    executor_type="llm",
                    inputs=["input_text", "session_state", "step_outputs"],
                    outputs=["analysis", "summary"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "inject_analysis_step",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "missing_analysis_output",
                    },
                )
            )
            repair_actions.append("inject:analyze_workflow_context")
            dependencies = [repaired_steps[-1].step_id]

        should_inject_patch_pipeline = enable_autonomous_patch_pipeline and (
            bool(repair_classification.get("execution_failures"))
            or "goal_alignment" in set(repair_classification.get("missing_outputs", []))
            or any(step.executor_type == "code" for step in workflow.steps)
            or any(req in {"artifact", "file", "document"} for req in task.output_requirements)
        )

        if should_inject_patch_pipeline:
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="generate_runtime_patch",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["input_text", "session_state", "step_outputs"],
                    outputs=["status", "patch_plan", "patch_artifact_path", "patched_files"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "inject_runtime_patch_generation",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "execution_failure_or_goal_alignment",
                    },
                )
            )
            repair_actions.append("inject:generate_runtime_patch")
            dependencies = [repaired_steps[-1].step_id]

            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="validate_runtime_patch",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["patch_plan", "session_state"],
                    outputs=["status", "validation_results", "executed_commands"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "inject_runtime_validation",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "post_patch_validation",
                    },
                )
            )
            repair_actions.append("inject:validate_runtime_patch")
            dependencies = [repaired_steps[-1].step_id]

            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="verify_runtime_patch",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["validation_results", "step_outputs"],
                    outputs=["status", "verified", "message"],
                    depends_on=dependencies,
                    retry=0,
                    metadata={
                        "repair_action": "inject_runtime_verification",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "confirm_patch_effectiveness",
                    },
                )
            )
            repair_actions.append("inject:verify_runtime_patch")
            dependencies = [repaired_steps[-1].step_id]

        if missing_steps.intersection({"artifact", "document", "file"}) or missing_outputs.intersection({"artifact", "document", "file"}):
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="generate_workflow_artifact",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["analysis", "step_outputs"],
                    outputs=["artifact", "artifact_path", "status"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "inject_artifact_step",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "missing_artifact_output",
                    },
                )
            )
            repair_actions.append("inject:generate_workflow_artifact")
            dependencies = [repaired_steps[-1].step_id]
            repaired_steps.append(
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="persist_workflow_output",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["artifact_path", "session_state"],
                    outputs=["delivery_status", "stored_output"],
                    depends_on=dependencies,
                    retry=1,
                    metadata={
                        "repair_action": "inject_io_step",
                        "selection_basis": "runtime_repair",
                        "repair_reason": "missing_output_persistence",
                    },
                )
            )
            repair_actions.append("inject:persist_workflow_output")

        repaired_composition = dict(workflow.composition or {})
        metadata = dict(repaired_composition.get("metadata") or {})
        metadata.update(
            {
                "runtime_repair_applied": True,
                "runtime_repair_actions": repair_actions,
                "repair_iteration": int(metadata.get("repair_iteration", 0)) + 1,
                "repair_classification": repair_classification,
            }
        )
        repaired_composition["metadata"] = metadata

        return WorkflowSchema(
            workflow_id=generate_id("workflow"),
            task_id=workflow.task_id,
            mode=workflow.mode,
            steps=repaired_steps,
            composition=repaired_composition,
        )
