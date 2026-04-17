from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from nethub_runtime.core.config.settings import PLUGIN_CONFIG_PATH
from nethub_runtime.core.services.plugin_loader import load_plugin
from nethub_runtime.core.services.execution_agent_handlers import (
    handle_manage_information_agent_step,
    handle_query_information_knowledge_step,
)
from nethub_runtime.core.services.execution_step_handlers import (
    handle_aggregate_query_step,
    handle_extract_records_step,
    handle_file_generate_step,
    handle_image_generate_step,
    handle_ocr_extract_step,
    handle_parse_query_step,
    handle_persist_records_step,
    handle_stt_transcribe_step,
    handle_tts_synthesize_step,
    handle_video_generate_step,
    handle_web_retrieve_step,
    handle_web_summarize_step,
)


@dataclass(frozen=True)
class ExecutionHandlerPluginExecutorSpec:
    executor_type: str
    handler: Any
    description: str = ""


@dataclass(frozen=True)
class ExecutionHandlerPluginStepSpec:
    executor_type: str
    step_name: str
    handler: Any
    description: str = ""


@dataclass(frozen=True)
class ExecutionHandlerPluginRequirement:
    requirement_type: str
    name: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class ExecutionHandlerPluginManifest:
    name: str
    executors: list[ExecutionHandlerPluginExecutorSpec] = field(default_factory=list)
    steps: list[ExecutionHandlerPluginStepSpec] = field(default_factory=list)
    requirements: list[ExecutionHandlerPluginRequirement] = field(default_factory=list)
    version: str = "1.0"


class ExecutionHandlerRegistry:
    def __init__(self) -> None:
        self._executor_handlers: dict[str, Any] = {}
        self._step_handlers: dict[str, dict[str, Any]] = {}
        self._plugin_manifests: list[dict[str, Any]] = []

    def register_executor(self, executor_type: str, handler: Any) -> None:
        if not executor_type:
            raise ValueError("executor_type is required")
        if not callable(handler):
            raise TypeError(f"executor handler for '{executor_type}' must be callable")
        self._executor_handlers[executor_type] = handler

    def register_step(self, executor_type: str, step_name: str, handler: Any) -> None:
        if not executor_type:
            raise ValueError("executor_type is required")
        if not step_name:
            raise ValueError("step_name is required")
        if not callable(handler):
            raise TypeError(f"step handler for '{executor_type}.{step_name}' must be callable")
        self._step_handlers.setdefault(executor_type, {})
        self._step_handlers[executor_type][step_name] = handler

    def get_executor_handlers(self) -> dict[str, Any]:
        return dict(self._executor_handlers)

    def get_step_handlers(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._step_handlers.items()}

    def get_plugin_manifests(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._plugin_manifests]

    def _assess_requirement(self, requirement: ExecutionHandlerPluginRequirement, coordinator: Any) -> dict[str, Any]:
        requirement_type = requirement.requirement_type.strip()
        name = requirement.name.strip()
        if not requirement_type:
            raise ValueError("execution handler plugin requirement_type is required")
        if not name:
            raise ValueError("execution handler plugin requirement name is required")

        satisfied = False
        if requirement_type == "dispatcher":
            satisfied = callable(getattr(coordinator, f"_dispatch_{name}_step", None))
        elif requirement_type == "store":
            satisfied = getattr(coordinator, name, None) is not None
        elif requirement_type == "service":
            satisfied = getattr(coordinator, name, None) is not None
        elif requirement_type == "executor":
            satisfied = name in self._executor_handlers
        elif requirement_type == "embedding_model":
            satisfied = getattr(coordinator, "_embedding_model", None) is not None

        return {
            "type": requirement_type,
            "name": name,
            "description": requirement.description,
            "required": requirement.required,
            "satisfied": satisfied,
        }

    def _register_manifest(self, manifest: ExecutionHandlerPluginManifest, coordinator: Any) -> None:
        if not manifest.name:
            raise ValueError("execution handler plugin manifest name is required")
        for executor in manifest.executors:
            self.register_executor(executor.executor_type, executor.handler)
        for step in manifest.steps:
            self.register_step(step.executor_type, step.step_name, step.handler)
        assessed_requirements = [self._assess_requirement(item, coordinator) for item in manifest.requirements]
        self._plugin_manifests.append(
            {
                "name": manifest.name,
                "version": manifest.version,
                "requirements": assessed_requirements,
                "requirements_satisfied": all(item["satisfied"] or not item["required"] for item in assessed_requirements),
                "executors": [item.executor_type for item in manifest.executors],
                "steps": [f"{item.executor_type}.{item.step_name}" for item in manifest.steps],
            }
        )

    def register_plugin(self, plugin: Any, coordinator: Any) -> None:
        if hasattr(plugin, "build_manifest"):
            manifest = plugin.build_manifest(coordinator)
            if not isinstance(manifest, ExecutionHandlerPluginManifest):
                raise TypeError("execution handler plugin build_manifest must return ExecutionHandlerPluginManifest")
            self._register_manifest(manifest, coordinator)
            return
        if hasattr(plugin, "register"):
            plugin.register(self, coordinator)
            return
        if callable(plugin):
            plugin(self, coordinator)
            return
        raise TypeError("execution handler plugin must be callable or expose a register method")


def _load_execution_handler_plugins() -> list[Any]:
    if not PLUGIN_CONFIG_PATH.exists():
        return []
    payload = json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
    plugins: list[Any] = []
    for plugin_path in payload.get("execution_handler_registry_plugins", []):
        plugins.append(load_plugin(plugin_path))
    return plugins


def build_execution_handler_registry(coordinator: Any) -> ExecutionHandlerRegistry:
    registry = ExecutionHandlerRegistry()

    registry.register_executor("agent", coordinator._dispatch_agent_step)
    registry.register_executor("knowledge_retrieval", coordinator._dispatch_knowledge_step)
    registry.register_executor("tool", coordinator._dispatch_tool_step)
    registry.register_executor("llm", coordinator._dispatch_llm_step)
    registry.register_executor("code", coordinator._dispatch_code_step)

    registry.register_step(
        "agent",
        "manage_information_agent",
        lambda step, task, context, step_outputs: handle_manage_information_agent_step(coordinator, step, task, context, step_outputs),
    )
    registry.register_step(
        "knowledge_retrieval",
        "query_information_knowledge",
        lambda step, task, context, step_outputs: handle_query_information_knowledge_step(coordinator, step, task, context, step_outputs),
    )

    registry.register_step("tool", "extract_records", lambda step, task, context, step_outputs: handle_extract_records_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "persist_records", lambda step, task, context, step_outputs: handle_persist_records_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "parse_query", lambda step, task, context, step_outputs: handle_parse_query_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "aggregate_query", lambda step, task, context, step_outputs: handle_aggregate_query_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "ocr_extract", lambda step, task, context, step_outputs: handle_ocr_extract_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "stt_transcribe", lambda step, task, context, step_outputs: handle_stt_transcribe_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "tts_synthesize", lambda step, task, context, step_outputs: handle_tts_synthesize_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "image_generate", lambda step, task, context, step_outputs: handle_image_generate_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "video_generate", lambda step, task, context, step_outputs: handle_video_generate_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "file_generate", lambda step, task, context, step_outputs: handle_file_generate_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "web_retrieve", lambda step, task, context, step_outputs: handle_web_retrieve_step(coordinator, step, task, context, step_outputs))
    registry.register_step("tool", "web_summarize", lambda step, task, context, step_outputs: handle_web_summarize_step(coordinator, step, task, context, step_outputs))

    for plugin in _load_execution_handler_plugins():
        registry.register_plugin(plugin, coordinator)

    return registry