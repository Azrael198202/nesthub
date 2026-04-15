from __future__ import annotations

from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.utils.id_generator import generate_id


class DataOpsTaskDecomposerPlugin:
    priority = 100

    def match(self, task: TaskSchema) -> bool:
        return task.domain == "data_ops"

    def run(self, task: TaskSchema) -> list[SubTask]:
        if task.intent == "data_record":
            return [
                SubTask(subtask_id=generate_id("subtask"), name="extract_records", goal="Extract structured records from natural language."),
                SubTask(subtask_id=generate_id("subtask"), name="persist_records", goal="Persist normalized records."),
            ]
        if task.intent == "data_query":
            return [
                SubTask(subtask_id=generate_id("subtask"), name="parse_query", goal="Parse analytical query intent and filters."),
                SubTask(subtask_id=generate_id("subtask"), name="aggregate_query", goal="Run aggregation over persisted records."),
            ]
        return [SubTask(subtask_id=generate_id("subtask"), name="single_step", goal="Execute generic data operation.")]


class MultimodalTaskDecomposerPlugin:
    priority = 90

    def match(self, task: TaskSchema) -> bool:
        return task.domain == "multimodal_ops"

    def run(self, task: TaskSchema) -> list[SubTask]:
        mapping = {
            "ocr_task": [("ocr_extract", "Extract text from image input.")],
            "stt_task": [("stt_transcribe", "Transcribe speech/audio to text.")],
            "tts_task": [("tts_synthesize", "Synthesize speech from text.")],
            "image_generation_task": [("image_generate", "Generate image artifact.")],
            "video_generation_task": [("video_generate", "Generate video/animation artifact.")],
            "file_generation_task": [("file_generate", "Generate file artifact (PDF/Word/PPT).")],
            "web_research_task": [
                ("web_retrieve", "Retrieve and parse web content."),
                ("web_summarize", "Summarize retrieved web content."),
            ],
        }
        steps = mapping.get(task.intent, [("single_step", "Execute generic multimodal operation.")])
        return [SubTask(subtask_id=generate_id("subtask"), name=name, goal=goal) for name, goal in steps]


class DefaultTaskDecomposerPlugin:
    priority = 1

    def match(self, _task: TaskSchema) -> bool:
        return True

    def run(self, _task: TaskSchema) -> list[SubTask]:
        return [SubTask(subtask_id=generate_id("subtask"), name="single_step", goal="Handle generic request.")]


class TaskDecomposer:
    """Decomposes main task into executable subtasks."""

    def __init__(self) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(DataOpsTaskDecomposerPlugin())
        self.register_plugin(MultimodalTaskDecomposerPlugin())
        self.register_plugin(DefaultTaskDecomposerPlugin())

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    async def decompose(self, task: TaskSchema) -> list[SubTask]:
        for plugin in self.plugins:
            if plugin.match(task):
                return plugin.run(task)
        raise RuntimeError("No task decomposer plugin matched.")
