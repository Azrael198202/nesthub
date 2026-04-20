from __future__ import annotations

import re
from typing import Any

from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.utils.id_generator import generate_id


class RuntimeRepairService:
    def _guidance_preferences(self, repair_classification: dict[str, Any]) -> dict[str, bool]:
        guidance = repair_classification.get("runtime_learning_guidance") or {}
        preferences = guidance.get("repair_preferences") if isinstance(guidance, dict) else {}
        if not isinstance(preferences, dict):
            return {}
        analysis_before_retry = bool(preferences.get("analysis_before_retry"))
        return {
            "prefer_tool_prepare": bool(preferences.get("prefer_tool_prepare")),
            "prefer_analysis": bool(preferences.get("prefer_analysis")) or analysis_before_retry,
            "prefer_analysis_before_retry": analysis_before_retry,
            "prefer_patch_pipeline": bool(preferences.get("prefer_patch_pipeline")),
            "prefer_artifact_pipeline": bool(preferences.get("prefer_artifact_pipeline")),
        }

    def _guidance_text(self, repair_classification: dict[str, Any]) -> str:
        guidance = repair_classification.get("runtime_learning_guidance") or {}
        if not isinstance(guidance, dict):
            return ""
        parts = [
            str(guidance.get("solution_summary") or "").strip(),
            str(repair_classification.get("preferred_solution_summary") or "").strip(),
        ]
        return " ".join(part for part in parts if part).lower()

    def _guidance_signals(self, repair_classification: dict[str, Any]) -> dict[str, bool]:
        structured = self._guidance_preferences(repair_classification)
        text = self._guidance_text(repair_classification)
        defaults = {
                "prefer_tool_prepare": False,
                "prefer_analysis": False,
                "prefer_analysis_before_retry": False,
                "prefer_patch_pipeline": False,
                "prefer_artifact_pipeline": False,
            }
        if not text:
            return {**defaults, **structured}
        heuristic = {
            "prefer_tool_prepare": bool(re.search(r"tool|install|dependency|package|pandoc", text)),
            "prefer_analysis": bool(re.search(r"analysis|analyze|summary|context", text)),
            "prefer_analysis_before_retry": bool(re.search(r"analysis.*before retry|summary.*before retry|context.*before retry|before retry.*analysis|before retry.*summary|before retry.*context", text)),
            "prefer_patch_pipeline": bool(re.search(r"patch|validate|verification|verify|fix code", text)),
            "prefer_artifact_pipeline": bool(re.search(r"artifact|document|file|persist|delivery", text)),
        }
        return {
            key: bool(structured.get(key)) or bool(heuristic.get(key))
            for key in defaults
        }

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
        guidance_signals = self._guidance_signals(repair_classification)

        missing_tools = list(repair_classification.get("missing_tools", []))
        missing_outputs = set(repair_classification.get("missing_outputs", []))
        missing_steps = set(repair_classification.get("missing_steps", []))
        needs_analysis_step = (
            bool(missing_steps.intersection({"analysis", "summary", "insight"}) or missing_outputs.intersection({"analysis", "summary", "insight"}))
            or guidance_signals["prefer_analysis"]
        )
        needs_artifact_pipeline = (
            bool(missing_steps.intersection({"artifact", "document", "file"}) or missing_outputs.intersection({"artifact", "document", "file"}))
            or guidance_signals["prefer_artifact_pipeline"]
        )

        if missing_tools or guidance_signals["prefer_tool_prepare"]:
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
                        "runtime_learning_guided": guidance_signals["prefer_tool_prepare"],
                    },
                )
            )
            repair_actions.append("inject:prepare_runtime_tools")
            dependencies = [repaired_steps[-1].step_id]

        if needs_analysis_step and guidance_signals["prefer_analysis_before_retry"]:
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
                        "selection_basis": "runtime_learning_guided_repair",
                        "repair_reason": "guided_analysis_before_retry",
                        "runtime_learning_guided": True,
                    },
                )
            )
            repair_actions.append("inject:analyze_workflow_context")
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
                        "runtime_learning_guided": guidance_signals["prefer_analysis_before_retry"],
                    },
                )
            )
            repair_actions.append(f"retry:{step_name}")
            dependencies = [repaired_steps[-1].step_id]

        if needs_analysis_step and not guidance_signals["prefer_analysis_before_retry"]:
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_analysis"] else "runtime_repair",
                        "repair_reason": "guided_analysis" if guidance_signals["prefer_analysis"] else "missing_analysis_output",
                        "runtime_learning_guided": guidance_signals["prefer_analysis"],
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
            or guidance_signals["prefer_patch_pipeline"]
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_patch_pipeline"] else "runtime_repair",
                        "repair_reason": "guided_patch_pipeline" if guidance_signals["prefer_patch_pipeline"] else "execution_failure_or_goal_alignment",
                        "runtime_learning_guided": guidance_signals["prefer_patch_pipeline"],
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_patch_pipeline"] else "runtime_repair",
                        "repair_reason": "guided_patch_pipeline" if guidance_signals["prefer_patch_pipeline"] else "post_patch_validation",
                        "runtime_learning_guided": guidance_signals["prefer_patch_pipeline"],
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_patch_pipeline"] else "runtime_repair",
                        "repair_reason": "guided_patch_pipeline" if guidance_signals["prefer_patch_pipeline"] else "confirm_patch_effectiveness",
                        "runtime_learning_guided": guidance_signals["prefer_patch_pipeline"],
                    },
                )
            )
            repair_actions.append("inject:verify_runtime_patch")
            dependencies = [repaired_steps[-1].step_id]

        if needs_artifact_pipeline:
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_artifact_pipeline"] else "runtime_repair",
                        "repair_reason": "guided_artifact_pipeline" if guidance_signals["prefer_artifact_pipeline"] else "missing_artifact_output",
                        "runtime_learning_guided": guidance_signals["prefer_artifact_pipeline"],
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
                        "selection_basis": "runtime_learning_guided_repair" if guidance_signals["prefer_artifact_pipeline"] else "runtime_repair",
                        "repair_reason": "guided_artifact_pipeline" if guidance_signals["prefer_artifact_pipeline"] else "missing_output_persistence",
                        "runtime_learning_guided": guidance_signals["prefer_artifact_pipeline"],
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
                "runtime_learning_guidance_applied": any(guidance_signals.values()),
                "runtime_learning_guidance_signals": guidance_signals,
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
