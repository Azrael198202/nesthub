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

    def _infer_executor_type(self, step_name: str) -> str:
        if step_name in {"manage_information_agent"}:
            return "agent"
        if step_name in {"query_information_knowledge"}:
            return "knowledge_retrieval"
        if step_name in {"extract_records", "parse_query", "aggregate_query", "persist_records"}:
            return "tool"
        if step_name in {"ocr_extract", "stt_transcribe", "tts_synthesize", "image_generate", "video_generate", "file_generate", "web_retrieve", "web_summarize"}:
            return "tool"
        return "llm"

    def _infer_io_contract(self, step_name: str) -> tuple[list[str], list[str]]:
        contracts = {
            "extract_records": (["input_text"], ["records", "count"]),
            "persist_records": (["records", "session_state"], ["saved", "total_records"]),
            "parse_query": (["input_text", "session_state"], ["query"]),
            "aggregate_query": (["query", "session_state"], ["aggregation"]),
            "manage_information_agent": (["input_text", "session_state"], ["message", "dialog_state", "agent", "knowledge"]),
            "query_information_knowledge": (["input_text", "session_state", "knowledge_store"], ["message", "answer", "knowledge_hits"]),
            "ocr_extract": (["input_text"], ["artifact_type", "status", "message"]),
            "stt_transcribe": (["input_text"], ["artifact_type", "status", "message"]),
            "tts_synthesize": (["input_text"], ["artifact_type", "status", "message"]),
            "image_generate": (["input_text"], ["artifact_type", "status"]),
            "video_generate": (["input_text"], ["artifact_type", "status"]),
            "file_generate": (["input_text"], ["artifact_type", "status"]),
            "web_retrieve": (["input_text"], ["artifact_type", "status"]),
            "web_summarize": (["web_content"], ["artifact_type", "status"]),
            "single_step": (["input_text"], ["message"]),
        }
        return contracts.get(step_name, (["input_text"], ["message"]))

    def match(self, _task: TaskSchema, _subtasks: list[SubTask]) -> bool:
        return True

    def run(self, task: TaskSchema, subtasks: list[SubTask]) -> WorkflowSchema:
        steps: list[WorkflowStepSchema] = []
        prev_step_id: str | None = None
        for item in subtasks:
            step_id = generate_id("step")
            depends_on = [prev_step_id] if prev_step_id else []
            inputs, outputs = self._infer_io_contract(item.name)
            steps.append(
                WorkflowStepSchema(
                    step_id=step_id,
                    name=item.name,
                    task_type=task.intent,
                    executor_type=self._infer_executor_type(item.name),
                    inputs=inputs,
                    outputs=outputs,
                    depends_on=depends_on,
                    retry=1,
                    metadata={
                        "goal": item.goal,
                        "selection_basis": "task_decomposition",
                        "subtask_name": item.name,
                    },
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
