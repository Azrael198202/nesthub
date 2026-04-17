from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema


class RuntimeOutcomeEvaluator:
    _OUTPUT_ALIASES = {
        "dialog": {"dialog", "dialog_state"},
        "artifact": {"artifact", "artifact_path", "artifact_type"},
    }

    def evaluate(self, *, task: TaskSchema, workflow: WorkflowSchema, execution_result: dict[str, Any]) -> dict[str, Any]:
        final_output = execution_result.get("final_output") or {}
        step_results = execution_result.get("steps") or []
        failed_steps = [step for step in step_results if step.get("status") == "failed"]

        available_outputs: set[str] = set()
        for step in workflow.steps:
            if step.name in final_output:
                available_outputs.update(step.outputs)
                payload = final_output.get(step.name)
                if isinstance(payload, dict):
                    available_outputs.update(payload.keys())

        unmet_requirements = [
            req
            for req in task.output_requirements
            if not any(alias in available_outputs for alias in self._OUTPUT_ALIASES.get(req, {req}))
        ]
        should_repair = bool(failed_steps or unmet_requirements)
        status = "needs_repair" if should_repair else "satisfied"

        return {
            "status": status,
            "failed_steps": [step.get("name", "") for step in failed_steps],
            "unmet_requirements": unmet_requirements,
            "available_outputs": sorted(available_outputs),
            "should_repair": should_repair,
        }
