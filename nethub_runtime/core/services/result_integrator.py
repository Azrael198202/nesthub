from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Callable

from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema


class ResultIntegrator:
    """Integrates and formats execution results with post hooks."""

    def __init__(self) -> None:
        self.hooks: list[Callable[[dict[str, Any]], dict[str, Any]]] = []

    def register_hook(self, hook: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.hooks.append(hook)

    def _to_csv(self, result: dict[str, Any]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["field", "value"])
        for key, value in result.items():
            writer.writerow([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
        return buffer.getvalue()

    def _artifact_record(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        path: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_path = Path(path)
        return {
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "path": path,
            "name": artifact_path.name,
            "source": source,
            "metadata": metadata or {},
        }

    def _collect_artifacts(
        self,
        *,
        blueprints: list[dict[str, Any]],
        agent: dict[str, Any] | None,
        execution_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []

        for blueprint in blueprints:
            metadata = blueprint.get("metadata") or {}
            artifact_path = metadata.get("generated_artifact_path")
            blueprint_id = str(blueprint.get("blueprint_id") or blueprint.get("name") or "")
            if artifact_path and blueprint_id:
                artifacts.append(
                    self._artifact_record(
                        artifact_type="blueprint",
                        artifact_id=blueprint_id,
                        path=str(artifact_path),
                        source="runtime_blueprint_generation",
                        metadata={"name": blueprint.get("name", "")},
                    )
                )

        if agent:
            artifact_path = agent.get("generated_artifact_path")
            agent_id = str(agent.get("agent_id") or agent.get("name") or "")
            if artifact_path and agent_id:
                artifacts.append(
                    self._artifact_record(
                        artifact_type="agent",
                        artifact_id=agent_id,
                        path=str(artifact_path),
                        source="runtime_agent_generation",
                        metadata={"name": agent.get("name", ""), "role": agent.get("role", "")},
                    )
                )

        trace_path = execution_result.get("generated_trace_path")
        trace_id = execution_result.get("trace_id")
        if trace_path and trace_id:
            artifacts.append(
                self._artifact_record(
                    artifact_type="trace",
                    artifact_id=str(trace_id),
                    path=str(trace_path),
                    source="runtime_execution_trace",
                    metadata={"execution_type": execution_result.get("execution_type", "")},
                )
            )

        final_output = execution_result.get("final_output") or {}
        artifact_output = final_output.get("generate_workflow_artifact") or {}
        artifact_path = artifact_output.get("artifact_path")
        if artifact_path:
            artifact_id = str(Path(str(artifact_path)).stem)
            artifacts.append(
                self._artifact_record(
                    artifact_type=str(artifact_output.get("artifact_type") or "document"),
                    artifact_id=artifact_id,
                    path=str(artifact_path),
                    source="workflow_generated_artifact",
                    metadata={
                        "status": artifact_output.get("status", "generated"),
                        "summary": artifact_output.get("summary", ""),
                    },
                )
            )

        return artifacts

    def build_artifact_index(self, artifacts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for artifact in artifacts:
            artifact_type = str(artifact.get("artifact_type") or "unknown")
            index.setdefault(artifact_type, []).append(artifact)
        return index

    def build_response(
        self,
        *,
        task: TaskSchema,
        workflow: WorkflowSchema | None,
        execution_result: dict[str, Any],
        context: CoreContextSchema,
        blueprints: list[dict[str, Any]] | None = None,
        agent: dict[str, Any] | None = None,
        fmt: str = "dict",
    ) -> dict[str, Any] | str:
        blueprints_payload = blueprints or []
        result: dict[str, Any] = {
            "trace_id": context.trace_id,
            "session_id": context.session_id,
            "task": task.model_dump(),
            "workflow": workflow.model_dump() if workflow is not None else {},
            "blueprints": blueprints_payload,
            "agent": agent,
            "execution_result": execution_result,
        }
        result["artifacts"] = self._collect_artifacts(
            blueprints=blueprints_payload,
            agent=agent,
            execution_result={**execution_result, "trace_id": context.trace_id},
        )
        result["artifact_index"] = self.build_artifact_index(result["artifacts"])
        for hook in self.hooks:
            result = hook(result)
        if fmt == "json":
            return json.dumps(result, ensure_ascii=False)
        if fmt == "csv":
            return self._to_csv(result)
        return result
