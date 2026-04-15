from __future__ import annotations

import json

from nethub_runtime.core.config.settings import PLUGIN_CONFIG_PATH
from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.services.plugin_loader import load_plugin
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.utils.id_generator import generate_id


class DefaultWorkflowPlannerPlugin:
    priority = 10

    def match(self, _task: TaskSchema, _subtasks: list[SubTask]) -> bool:
        return True

    def run(self, task: TaskSchema, subtasks: list[SubTask]) -> WorkflowSchema:
        steps: list[WorkflowStepSchema] = []
        prev_step_id: str | None = None
        for item in subtasks:
            step_id = generate_id("step")
            depends_on = [prev_step_id] if prev_step_id else []
            steps.append(
                WorkflowStepSchema(
                    step_id=step_id,
                    name=item.name,
                    task_type=task.intent,
                    depends_on=depends_on,
                    retry=1,
                    metadata={"goal": item.goal},
                )
            )
            prev_step_id = step_id
        return WorkflowSchema(workflow_id=generate_id("workflow"), task_id=task.task_id, mode="normal", steps=steps)


class WorkflowPlanner:
    """Plans workflow graph from decomposed tasks."""

    def __init__(self) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(DefaultWorkflowPlannerPlugin())
        self.load_plugins_from_config()

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    def unregister_plugin(self, plugin_type: type[PluginBase]) -> None:
        self.plugins = [item for item in self.plugins if not isinstance(item, plugin_type)]

    def load_plugins_from_config(self) -> None:
        if not PLUGIN_CONFIG_PATH.exists():
            return
        payload = json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
        for plugin_path in payload.get("workflow_planner_plugins", []):
            plugin = load_plugin(plugin_path)
            self.register_plugin(plugin)

    async def plan(self, task: TaskSchema, subtasks: list[SubTask]) -> WorkflowSchema:
        for plugin in self.plugins:
            if plugin.match(task, subtasks):
                return plugin.run(task, subtasks)
        raise RuntimeError("No workflow planner plugin matched.")
