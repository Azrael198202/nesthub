from __future__ import annotations

from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.utils.id_generator import generate_id


class ExpenseTaskDecomposerPlugin:
    priority = 100

    def match(self, task: TaskSchema) -> bool:
        return task.domain == "household_budget"

    def run(self, task: TaskSchema) -> list[SubTask]:
        if task.intent == "expense_record":
            return [
                SubTask(subtask_id=generate_id("subtask"), name="extract_records", goal="Split and parse natural language entries."),
                SubTask(subtask_id=generate_id("subtask"), name="persist_records", goal="Save normalized expense entries.", depends_on=[]),
            ]
        return [
            SubTask(subtask_id=generate_id("subtask"), name="parse_query", goal="Understand natural language query."),
            SubTask(subtask_id=generate_id("subtask"), name="aggregate_query", goal="Aggregate records by requested dimensions."),
        ]


class DefaultTaskDecomposerPlugin:
    priority = 1

    def match(self, _task: TaskSchema) -> bool:
        return True

    def run(self, _task: TaskSpec) -> list[SubTask]:
        return [SubTask(subtask_id=generate_id("subtask"), name="single_step", goal="Handle generic request.")]


class TaskDecomposer:
    """Decomposes main task into executable subtasks."""

    def __init__(self) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(ExpenseTaskDecomposerPlugin())
        self.register_plugin(DefaultTaskDecomposerPlugin())

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    async def decompose(self, task: TaskSchema) -> list[SubTask]:
        for plugin in self.plugins:
            if plugin.match(task):
                return plugin.run(task)
        raise RuntimeError("No task decomposer plugin matched.")
