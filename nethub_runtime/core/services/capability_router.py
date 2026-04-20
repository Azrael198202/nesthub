from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nethub_runtime.core.adapters.model_adapter import ModelRouter
from nethub_runtime.core.config.settings import MODEL_ROUTES_PATH, RUNTIME_CAPABILITIES_PATH, ensure_core_config_dir
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.tools.registry import get_skill, list_skills


class CapabilityRouter:
    """Routes workflow steps to models/tools/services via JSON-configurable rules."""

    def __init__(self, route_path: Path | None = None, capabilities_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.route_path = route_path or MODEL_ROUTES_PATH
        self.capabilities_path = capabilities_path or RUNTIME_CAPABILITIES_PATH
        self._route_config: dict[str, Any] = {}
        self._capabilities: dict[str, Any] = {}
        self._last_mtime: float | None = None
        self._capabilities_mtime: float | None = None
        self.model_router = ModelRouter()
        self._load_routes()
        self._load_capabilities()

    def _task_kind_from_step(self, step_name: str) -> str:
        mapping = {
            "extract_records": "routing",
            "parse_query": "routing",
            "aggregate_query": "planning",
            "persist_records": "planning",
            "analyze_document": "document_analysis",
            "manage_information_agent": "planning",
            "query_information_knowledge": "planning",
            "analyze_workflow_context": "planning",
            "generate_workflow_artifact": "file_generation",
            "generate_runtime_patch": "file_generation",
            "persist_workflow_output": "planning",
            "validate_runtime_patch": "planning",
            "verify_runtime_patch": "planning",
            "ocr_extract": "ocr",
            "stt_transcribe": "stt",
            "tts_synthesize": "tts",
            "image_generate": "image_generation",
            "video_generate": "video_generation",
            "file_generate": "file_generation",
            "file_read": "file_generation",
            "web_retrieve": "web_research",
            "web_summarize": "web_summary",
            "single_step": "planning",
        }
        return mapping.get(step_name, "planning")

    def _executor_type_for_step(self, step_name: str, route: dict[str, Any]) -> str:
        tool_name = str(route.get("tool", "") or "")
        service_name = str(route.get("service", "") or "")
        if step_name == "manage_information_agent":
            return "agent"
        if step_name == "query_information_knowledge" or tool_name == "vector_store":
            return "knowledge_retrieval"
        if step_name in {"generate_workflow_artifact", "persist_workflow_output", "file_read", "analyze_document"}:
            return "tool"
        if tool_name not in {"", "none"}:
            return "tool"
        if service_name in {"generic", "knowledge_memory"}:
            return "llm"
        return "llm"

    def _selection_rationale(
        self,
        *,
        task: TaskSchema,
        step: dict[str, Any],
        route: dict[str, Any],
        model_choice: dict[str, Any],
        executor_type: str,
    ) -> dict[str, Any]:
        return {
            "intent": task.intent,
            "domain": task.domain,
            "step_name": step["name"],
            "step_task_type": step["task_type"],
            "executor_type": executor_type,
            "task_kind": self._task_kind_from_step(step["name"]),
            "selected_model": model_choice,
            "selected_tool": route.get("tool", "none"),
            "selected_service": route.get("service", "generic"),
            "reason": f"Route task '{task.intent}' step '{step['name']}' to {executor_type} based on configured intent-step capability mapping.",
        }

    def _default_routes(self) -> dict[str, Any]:
        return {
            "data_record": {
                "extract_records": {"model": "rule-parser", "tool": "parser", "service": "nlp"},
                "persist_records": {"model": "state-store", "tool": "session_store", "service": "memory"},
            },
            "data_query": {
                "parse_query": {"model": "rule-parser", "tool": "query_parser", "service": "nlp"},
                "aggregate_query": {"model": "aggregation-engine", "tool": "query_engine", "service": "analytics"},
            },
            "create_information_agent": {
                "manage_information_agent": {"model": "general-llm", "tool": "session_store", "service": "knowledge_memory"},
            },
            "refine_information_agent": {
                "manage_information_agent": {"model": "general-llm", "tool": "session_store", "service": "knowledge_memory"},
            },
            "finalize_information_agent": {
                "manage_information_agent": {"model": "general-llm", "tool": "session_store", "service": "knowledge_memory"},
            },
            "capture_agent_knowledge": {
                "manage_information_agent": {"model": "general-llm", "tool": "session_store", "service": "knowledge_memory"},
            },
            "query_agent_knowledge": {
                "query_information_knowledge": {"model": "general-llm", "tool": "vector_store", "service": "knowledge_memory"},
            },
            "file_upload_task": {
                "analyze_document": {"model": "general-llm", "tool": "document_analyzer", "service": "document_runtime"},
            },
            "default_analysis": {
                "analyze_workflow_context": {"model": "general-llm", "tool": "none", "service": "generic"},
                "generate_workflow_artifact": {"model": "general-llm", "tool": "file_builder", "service": "artifact_builder"},
                "generate_runtime_patch": {"model": "general-llm", "tool": "file_builder", "service": "artifact_builder"},
                "persist_workflow_output": {"model": "state-store", "tool": "session_store", "service": "memory"},
                "validate_runtime_patch": {"model": "state-store", "tool": "shell_runner", "service": "validation"},
                "verify_runtime_patch": {"model": "state-store", "tool": "session_store", "service": "validation"},
            },
            "default": {"model": "general-llm", "tool": "none", "service": "generic"},
        }

    def _default_capabilities(self) -> dict[str, Any]:
        return {
            "models": [{"name": "local-rule-parser", "kind": "local", "supports": ["intent_analysis", "record_extraction"]}],
            "databases": [{"name": "session_store", "kind": "in_memory", "supports": ["stateful_records"]}],
            "shell": [{"name": "bash", "available": True, "supports": ["local_commands"]}],
            "tools": [{"name": "python_parser", "available": True}],
            "autonomous_implementation": {
                "enabled": True,
                "supports": ["capability_gap_resolution", "blueprint_completion", "code_patch_generation", "test_backfill"],
                "code_generation_models": ["local-rule-parser"],
                "required_tools": ["bash"],
                "safety_rules": {
                    "respect_read_only_main_policy": True,
                    "require_tests_for_new_logic": True,
                    "prefer_patch_over_replace": True,
                    "allow_runtime_generated_code": True,
                },
            },
        }

    def _load_routes(self) -> None:
        if not self.route_path.exists():
            self._route_config = self._default_routes()
            self.route_path.write_text(json.dumps(self._route_config, indent=2), encoding="utf-8")
            self._last_mtime = self.route_path.stat().st_mtime
            return
        self._route_config = json.loads(self.route_path.read_text(encoding="utf-8"))
        self._last_mtime = self.route_path.stat().st_mtime

    def _load_capabilities(self) -> None:
        if not self.capabilities_path.exists():
            self._capabilities = self._default_capabilities()
            self.capabilities_path.write_text(json.dumps(self._capabilities, ensure_ascii=False, indent=2), encoding="utf-8")
            self._capabilities_mtime = self.capabilities_path.stat().st_mtime
            return
        self._capabilities = json.loads(self.capabilities_path.read_text(encoding="utf-8"))
        self._capabilities_mtime = self.capabilities_path.stat().st_mtime

    def _maybe_reload(self) -> None:
        if not self.route_path.exists():
            return
        current_mtime = self.route_path.stat().st_mtime
        if self._last_mtime is None or current_mtime > self._last_mtime:
            self._load_routes()
        if self.capabilities_path.exists():
            cap_mtime = self.capabilities_path.stat().st_mtime
            if self._capabilities_mtime is None or cap_mtime > self._capabilities_mtime:
                self._load_capabilities()

    def route_workflow(self, task: TaskSchema, workflow: WorkflowSchema) -> list[dict[str, Any]]:
        self._maybe_reload()
        intent_routes = self._route_config.get(task.intent, {})
        analysis_routes = self._route_config.get("default_analysis", {})
        default_route = self._route_config.get("default", {})
        plan: list[dict[str, Any]] = []
        for step in workflow.steps:
            route = intent_routes.get(step.name, analysis_routes.get(step.name, default_route))
            model_choice = self.model_router.route(self._task_kind_from_step(step.name))
            availability = self.model_router.ensure_available(model_choice["provider"], model_choice["model"])
            executor_type = self._executor_type_for_step(step.name, route)
            selector = self._selection_rationale(
                task=task,
                step=step.model_dump(),
                route=route,
                model_choice=model_choice,
                executor_type=executor_type,
            )

            # Annotate with any @skill-registered skill that matches this step name
            # or supports the task intent — makes registered skills discoverable
            # without requiring an explicit JSON route entry.
            registered_skill: dict[str, Any] | None = get_skill(step.name)
            if registered_skill is None:
                # Fall back: check if any skill lists this intent as supported
                for s in list_skills():
                    if task.intent in s.get("supported_intents", []):
                        registered_skill = s
                        break

            plan.append(
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "task_type": step.task_type,
                    "executor_type": executor_type,
                    "inputs": step.inputs,
                    "outputs": step.outputs,
                    "depends_on": step.depends_on,
                    "retry": step.retry,
                    "capability": {**route, "model_choice": model_choice, "availability": availability},
                    "selector": selector,
                    "workflow_step_metadata": step.metadata,
                    "runtime_capabilities": self._capabilities,
                    # None when no @skill matches; present when one does
                    "registered_skill": registered_skill,
                }
            )
        return plan
