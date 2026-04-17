from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema


class RuntimeFailureClassifier:
    def classify(
        self,
        *,
        workflow: WorkflowSchema,
        evaluation: dict[str, Any],
        dependency_status: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dependency_status = dependency_status or {}
        execution_result = execution_result or {}
        unmet_requirements = list(evaluation.get("unmet_requirements", []))
        failed_steps = list(evaluation.get("failed_steps", []))
        workflow_outputs = {output for step in workflow.steps for output in step.outputs}

        missing_steps = [req for req in unmet_requirements if req not in workflow_outputs]
        missing_outputs = [req for req in unmet_requirements if req in workflow_outputs]

        missing_tools = list(dependency_status.get("missing_tools", [])) + list(dependency_status.get("missing_packages", []))
        for step in execution_result.get("steps", []):
            capability = step.get("capability") or {}
            availability = capability.get("model_choice", {})
            tool_name = capability.get("tool")
            if step.get("status") == "failed" and tool_name and tool_name not in {"none", "session_store", "vector_store"}:
                if tool_name not in missing_tools:
                    missing_tools.append(str(tool_name))
            if isinstance(availability, dict) and availability.get("available") is False:
                model_name = availability.get("model") or availability.get("provider")
                if model_name and model_name not in missing_tools:
                    missing_tools.append(str(model_name))

        return {
            "missing_steps": sorted(set(missing_steps)),
            "missing_tools": sorted(set(missing_tools)),
            "missing_outputs": sorted(set(missing_outputs)),
            "execution_failures": failed_steps,
            "should_repair": bool(missing_steps or missing_tools or missing_outputs or failed_steps),
        }
