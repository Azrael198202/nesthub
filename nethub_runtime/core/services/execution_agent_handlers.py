from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


def handle_manage_information_agent_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return coordinator._manage_information_agent(task.input_text, task, context)


def handle_query_information_knowledge_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return coordinator._query_information_knowledge(task.input_text, context)