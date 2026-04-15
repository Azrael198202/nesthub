from __future__ import annotations

import csv
import io
import json
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
        result: dict[str, Any] = {
            "trace_id": context.trace_id,
            "session_id": context.session_id,
            "task": task.model_dump(),
            "workflow": workflow.model_dump() if workflow is not None else {},
            "blueprints": blueprints or [],
            "agent": agent,
            "execution_result": execution_result,
        }
        for hook in self.hooks:
            result = hook(result)
        if fmt == "json":
            return json.dumps(result, ensure_ascii=False)
        if fmt == "csv":
            return self._to_csv(result)
        return result
