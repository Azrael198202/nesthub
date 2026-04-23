from __future__ import annotations

import json
import os
import re
import logging
import asyncio
import threading
import shlex
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module-level live execution progress store.
# Keyed by session_id.  Updated by execute() as each step starts/completes.
# The tvbox status endpoint reads this to give the frontend real-time progress.
# ---------------------------------------------------------------------------
_session_step_progress: dict[str, list[dict[str, Any]]] = {}
_session_step_progress_lock = threading.Lock()


def get_session_step_progress(session_id: str) -> list[dict[str, Any]]:
    """Return a shallow copy of the step progress list for *session_id*."""
    with _session_step_progress_lock:
        return list(_session_step_progress.get(session_id, []))


def clear_session_step_progress(session_id: str) -> None:
    with _session_step_progress_lock:
        _session_step_progress.pop(session_id, None)

import httpx

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, PLUGIN_CONFIG_PATH, SEMANTIC_POLICY_PATH
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.dependency_manager import DependencyManager
from nethub_runtime.core.services.security_guard import SecurityGuard
from nethub_runtime.core.services.execution_handler_registry import build_execution_handler_registry
from nethub_runtime.core.services.execution_repair_loop import ExecutionRepairLoop
from nethub_runtime.core.services.information_agent_service import InformationAgentService
from nethub_runtime.core.hooks.registry import HookContext, HookRegistry


LOGGER = logging.getLogger("nethub_runtime.core.execution_coordinator")


class ExecutionCoordinator:
    """Executes workflow nodes with semantic filtering and model-routed fallback aggregation."""

    @staticmethod
    def default_semantic_policy() -> dict[str, Any]:
        return {
            "tokenizer": {"preferred": "regex", "fallback": "regex", "min_token_length": 2},
            "semantic_matching": {
                "method": "embedding_or_token",
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "similarity_threshold": 0.62,
                "fallback_to_external_threshold": 0.35,
            },
            "normalization": {"text_replace": {}, "synonyms": {}},
            "intent_detection": {"group_query_markers": []},
            "aggregation_query": {"generic_action_terms": []},
            "information_collection": {
                "completion_phrases": [],
                "default_completion_phrase": "",
                "creation_followup_prompt": "",
                "messages": {},
                "defaults": {},
                "default_fields": [],
                "activation_keyword_templates": [],
                "include_query_aliases_in_activation_keywords": False,
                "creation_parsing": {
                    "field_markers": [],
                    "trigger_markers": [],
                    "completion_markers": [],
                },
                "field_capture_markers": [],
                "field_aliases": {},
                "field_query_keywords": {},
                "list_query_markers": [],
                "record_name_suffixes": [],
                "record_name_split_separators": [],
            },
            "entity_aliases": {"actor": {}},
            "label_taxonomy": {},
            "semantic_label_threshold": 0.32,
            "semantic_label_margin": 0.08,
            "ignored_query_tokens": [],
            "record_type_rules": {"generic": {"default": True, "default_label": "other"}},
            "query_metric_rules": {},
            "segment_split_patterns": ["[。；;\\n]", "\\band\\b"],
            "location_markers": [],
            "location_keyword_patterns": [],
            "participant_pattern": "(\\d+)",
            "participant_aliases": {},
            "content_cleanup_patterns": ["\\d+(?:\\.\\d+)?\\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\\$)?"],
            "content_strip_chars": " ，,.。",
            "group_by_aliases": {},
            "actor_extract_patterns": [],
            "explicit_date_patterns": [],
            "relative_week_rules": [],
            "boolean_aliases": {"truthy": ["yes", "true", "y", "1"], "falsy": ["no", "false", "n", "0"]},
            "model_semantic_parser": {
                "enabled": True,
                "prefer_model_for_query_parsing": True,
                "prefer_model_for_record_extraction": True,
                "strict_schema_validation": True,
                "router": "litellm",
                "task_types": {
                    "record_extraction": "semantic_parsing",
                    "query_parsing": "semantic_parsing",
                    "aggregation": "semantic_aggregation",
                    "policy_learning": "semantic_learning",
                    "labeling": "semantic_labeling",
                },
            },
            "time_marker_rules": {},
            "policy_memory": {
                "enabled": True,
                "backend": "sqlite",
                "read_only_main_policy": True,
                "auto_candidate_zone": True,
                "auto_activate": {
                    "enabled": True,
                    "min_hits": 2,
                    "min_confidence": 0.75,
                },
                "learning": {
                    "enabled": True,
                    "extractor": "model",
                    "max_updates_per_text": 8,
                    "default_confidence": 0.82,
                    "allowed_policy_keys": [
                        "location_markers",
                        "ignored_query_tokens",
                        "time_markers",
                        "segment_split_patterns",
                        "location_keyword_patterns",
                        "participant_aliases",
                        "group_by_aliases",
                        "entity_aliases.actor",
                        "record_type_rules",
                        "query_metric_rules",
                    ],
                    "min_candidate_text_length": 2,
                    "blocked_terms": [],
                    "reject_existing_conflicts": True,
                },
                "self_heal": {
                    "enabled": True,
                    "max_failures": 2,
                    "rollback_batch_size": 3,
                },
            },
            "external_semantic_router": {
                "enabled": False,
                "provider_priority": ["openai", "claude"],
                "openai": {"model": "gpt-4o", "api_env": "OPENAI_API_KEY"},
                "claude": {"model": "claude-3-5-sonnet-latest", "api_env": "ANTHROPIC_API_KEY"},
                "generic_endpoint_env": "NETHUB_LLM_ROUTER_ENDPOINT",
            },
        }

    def __init__(
        self,
        session_store: SessionStore | None = None,
        vector_store: VectorStore | None = None,
        generated_artifact_store: Any | None = None,
        model_router: Any | None = None,
        intent_policy_path: Path | None = None,
        semantic_policy_path: Path | None = None,
        hook_registry: HookRegistry | None = None,
    ) -> None:
        self.session_store = session_store or SessionStore()
        self.vector_store = vector_store or VectorStore()
        self.generated_artifact_store = generated_artifact_store
        self.model_router = model_router
        self.intent_policy_path = intent_policy_path or INTENT_POLICY_PATH
        self.semantic_policy_path = semantic_policy_path or SEMANTIC_POLICY_PATH
        self.semantic_policy_store = SemanticPolicyStore(policy_path=self.semantic_policy_path)
        self.dependency_manager = DependencyManager()
        self.security_guard = SecurityGuard()
        self.intent_policy = self._load_intent_policy()
        self.semantic_policy = self._load_semantic_policy()
        self._embedding_model = self._init_embedding_model()
        self.information_agent_service = InformationAgentService(
            session_store=self.session_store,
            vector_store=self.vector_store,
            model_router=model_router,
            semantic_policy_store=self.semantic_policy_store,
        )
        self._handler_registry = build_execution_handler_registry(self)
        self._executor_handlers = self._handler_registry.get_executor_handlers()
        self._step_handlers = self._handler_registry.get_step_handlers()
        self._repair_loop = ExecutionRepairLoop.from_policy(coordinator=self)
        self.hook_registry = hook_registry

    def _load_intent_policy(self) -> dict[str, Any]:
        if self.intent_policy_path.exists():
            return json.loads(self.intent_policy_path.read_text(encoding="utf-8"))
        return {"numeric_value_patterns": []}

    def _load_semantic_policy(self) -> dict[str, Any]:
        policy = self.default_semantic_policy()
        runtime_policy = self.semantic_policy_store.load_runtime_policy()
        if runtime_policy:
            policy = self._deep_merge_dicts(policy, runtime_policy)
        try:
            self._validate_semantic_policy(policy)
            return policy
        except ValueError as exc:
            rolled_back = self.semantic_policy_store.record_runtime_failure(reason=str(exc))
            if rolled_back:
                refreshed = self.semantic_policy_store.load_runtime_policy()
                self._validate_semantic_policy(refreshed)
                return refreshed
            raise

    def _validate_semantic_policy(self, policy: dict[str, Any]) -> None:
        required_top_level = (
            "location_markers",
            "participant_pattern",
            "participant_aliases",
            "group_by_aliases",
            "location_keyword_patterns",
            "segment_split_patterns",
            "content_cleanup_patterns",
            "time_marker_rules",
        )
        missing = [key for key in required_top_level if key not in policy]
        if missing:
            raise ValueError(f"semantic policy missing required keys: {', '.join(missing)}")
        if not isinstance(policy.get("location_markers"), list):
            raise ValueError("semantic policy location_markers must be a list")
        if not isinstance(policy.get("participant_aliases"), dict):
            raise ValueError("semantic policy participant_aliases must be a dict")
        if not isinstance(policy.get("group_by_aliases"), dict):
            raise ValueError("semantic policy group_by_aliases must be a dict")
        if not isinstance(policy.get("location_keyword_patterns"), list):
            raise ValueError("semantic policy location_keyword_patterns must be a list")
        if not isinstance(policy.get("segment_split_patterns"), list):
            raise ValueError("semantic policy segment_split_patterns must be a list")
        if not isinstance(policy.get("content_cleanup_patterns"), list):
            raise ValueError("semantic policy content_cleanup_patterns must be a list")
        if not isinstance(policy.get("time_marker_rules"), dict):
            raise ValueError("semantic policy time_marker_rules must be a dict")

    def _refresh_semantic_policy(self) -> None:
        self.semantic_policy = self._deep_merge_dicts(
            self.default_semantic_policy(),
            self.semantic_policy_store.load_runtime_policy(),
        )
        self._validate_semantic_policy(self.semantic_policy)

    def _deep_merge_dicts(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = json.loads(json.dumps(left, ensure_ascii=False))
        for key, value in right.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
                continue
            if isinstance(value, list) and isinstance(merged.get(key), list):
                items = list(merged[key])
                for item in value:
                    if item not in items:
                        items.append(item)
                merged[key] = items
                continue
            merged[key] = value
        return merged

    def _require_semantic_value(self, key: str, expected_type: type[Any]) -> Any:
        value = self.semantic_policy.get(key)
        if not isinstance(value, expected_type):
            raise ValueError(f"semantic policy key '{key}' must be {expected_type.__name__}")
        return value

    def _init_embedding_model(self) -> Any | None:
        model_name = self.semantic_policy.get("semantic_matching", {}).get("embedding_model")
        if not model_name:
            return None
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(model_name)
        except Exception:
            return None

    def execute(self, plan: list[dict[str, Any]], task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
        results: dict[str, Any] = {"steps": [], "task_intent": task.intent}
        step_outputs: dict[str, Any] = {}

        # Initialise progress store: all steps sleeping before any runs.
        session_id = context.session_id
        with _session_step_progress_lock:
            _session_step_progress[session_id] = [
                {
                    "name": s["name"],
                    "label": (s.get("workflow_step_metadata") or {}).get("display_label") or s["name"],
                    "status": "sleeping",
                    "preview": "",
                }
                for s in plan
            ]

        for step in plan:
            retries = step.get("retry", 0)
            attempt = 0

            # Mark this step as "working" in the live progress store.
            with _session_step_progress_lock:
                progress = _session_step_progress.get(session_id, [])
                for p in progress:
                    if p["name"] == step["name"]:
                        p["status"] = "working"
                        break
            last_error: str | None = None
            while attempt <= retries:
                try:
                    # pre_step hook — returning {"deny": True} skips the step
                    if self.hook_registry is not None:
                        pre_ctx = HookContext(
                            event="pre_step",
                            step_name=step["name"],
                            step=step,
                            task_intent=task.intent,
                            session_id=context.session_id,
                        )
                        pre_result = self.hook_registry.run("pre_step", pre_ctx)
                        if pre_result and pre_result.get("deny"):
                            output = {"status": "skipped", "reason": pre_result.get("reason", "hook_denied")}
                            step_outputs[step["name"]] = output
                            results["steps"].append({
                                "step_id": step["step_id"],
                                "name": step["name"],
                                "executor_type": step.get("executor_type", "unknown"),
                                "status": "skipped",
                                "inputs": step.get("inputs", []),
                                "outputs": step.get("outputs", []),
                                "selector": step.get("selector", {}),
                                "output": output,
                            })
                            break

                    output = self._repair_loop.run(
                        step=step,
                        task=task,
                        context=context,
                        step_outputs=step_outputs,
                        run_step_fn=self._run_step,
                    )

                    # post_step hook — receives step output for logging/auditing
                    if self.hook_registry is not None:
                        post_ctx = HookContext(
                            event="post_step",
                            step_name=step["name"],
                            step=step,
                            task_intent=task.intent,
                            session_id=context.session_id,
                            output=output,
                        )
                        self.hook_registry.run("post_step", post_ctx)

                    step_outputs[step["name"]] = output
                    results["steps"].append(
                        {
                            "step_id": step["step_id"],
                            "name": step["name"],
                            "executor_type": step.get("executor_type", "unknown"),
                            "status": "completed",
                            "inputs": step.get("inputs", []),
                            "outputs": step.get("outputs", []),
                            "selector": step.get("selector", {}),
                            "capability": step.get("capability", {}),
                            "runtime_capabilities": step.get("runtime_capabilities", {}),
                            "output": output,
                        }
                    )
                    # Mark step completed in live progress.
                    _preview = ""
                    if isinstance(output, dict):
                        _preview = str(
                            output.get("message") or output.get("summary") or
                            output.get("translation") or output.get("content") or ""
                        )[:120]
                    with _session_step_progress_lock:
                        for _p in _session_step_progress.get(session_id, []):
                            if _p["name"] == step["name"]:
                                _p["status"] = "packed"
                                _p["preview"] = _preview
                                break
                    break
                except Exception as exc:  # pragma: no cover
                    last_error = str(exc)
                    attempt += 1
                    if attempt > retries:
                        results["steps"].append(
                            {
                                "step_id": step["step_id"],
                                "name": step["name"],
                                "executor_type": step.get("executor_type", "unknown"),
                                "status": "failed",
                                "inputs": step.get("inputs", []),
                                "outputs": step.get("outputs", []),
                                "selector": step.get("selector", {}),
                                "error": last_error,
                            }
                        )
                        # Mark step failed in live progress.
                        with _session_step_progress_lock:
                            for _p in _session_step_progress.get(session_id, []):
                                if _p["name"] == step["name"]:
                                    _p["status"] = "error"
                                    break
        results["final_output"] = step_outputs

        # --- Task 1: auto-close task session when policy requests it ---
        if self.session_store.is_task_session(context.session_id):
            auto_close = (
                self.semantic_policy
                .get("runtime_behavior", {})
                .get("session", {})
                .get("context_window", {})
                .get("task_session_auto_close", True)
            )
            if auto_close:
                summary_parts = []
                for step_result in results["steps"]:
                    name = step_result.get("name", "")
                    status = step_result.get("status", "")
                    out = step_result.get("output") or {}
                    if isinstance(out, dict):
                        msg = out.get("message") or out.get("summary") or out.get("content") or ""
                    else:
                        msg = str(out)[:120]
                    if msg:
                        summary_parts.append(f"[{name}:{status}] {str(msg)[:120]}")
                summary = "; ".join(summary_parts) or f"task {task.intent} completed"
                self.session_store.close_task_session(
                    context.session_id,
                    summary=summary,
                    merge_to_main=True,
                )

        return results

    def _run_step(self, step: dict[str, Any], task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]) -> dict[str, Any]:
        executor_type = step.get("executor_type", "tool")
        executor_handler = self._executor_handlers.get(executor_type)
        if not executor_handler:
            return {"message": f"unsupported executor type: {executor_type}"}
        return executor_handler(step, task, context, step_outputs)

    def _dispatch_agent_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("agent", {}).get(step["name"])
        if not handler:
            return {"message": f"unsupported agent step: {step['name']}"}
        return handler(step, task, context, _step_outputs)

    def _dispatch_knowledge_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("knowledge_retrieval", {}).get(step["name"])
        if not handler:
            return {"message": f"unsupported knowledge step: {step['name']}"}
        return handler(step, task, context, _step_outputs)

    def _dispatch_tool_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("tool", {}).get(step["name"])
        if not handler:
            scaffold = self._maybe_scaffold_runtime_plugin_for_missing_step(step["name"])
            if scaffold.get("status") == "scaffolded":
                rebound = self._step_handlers.get("tool", {}).get(step["name"])
                if callable(rebound):
                    result = rebound(step, task, context, step_outputs)
                    if isinstance(result, dict):
                        result.setdefault("runtime_plugin_scaffold", scaffold)
                    return result
                return {
                    "status": "scaffolded",
                    "message": f"runtime plugin scaffolded for step: {step['name']}",
                    "runtime_plugin_scaffold": scaffold,
                }
            return {"message": f"unsupported tool step: {step['name']}", "runtime_plugin_scaffold": scaffold}
        return handler(step, task, context, step_outputs)

    def _runtime_plugin_scaffold_enabled(self) -> bool:
        policy = self._autonomous_implementation_policy()
        return bool(policy.get("enabled", False) and policy.get("auto_scaffold_missing_step_plugin", True))

    def _runtime_plugin_stem(self, step_name: str) -> str:
        tokens = [item for item in re.split(r"[^a-zA-Z0-9]+", str(step_name or "").strip().lower()) if item]
        if not tokens:
            return "dynamic"
        stem = "_".join(tokens[:2])
        return stem or "dynamic"

    def _render_runtime_handlers_source(self, step_names: list[str]) -> str:
        lines: list[str] = [
            "from __future__ import annotations",
            "",
            "from typing import Any",
            "",
            "from nethub_runtime.core.schemas.context_schema import CoreContextSchema",
            "from nethub_runtime.core.schemas.task_schema import TaskSchema",
            "",
            "# Generated by NestHub runtime plugin scaffold.",
            "",
        ]
        for step_name in step_names:
            fn = f"handle_{step_name}_step"
            lines.extend(
                [
                    f"def {fn}(",
                    "    coordinator: Any,",
                    "    _step: dict[str, Any],",
                    "    task: TaskSchema,",
                    "    context: CoreContextSchema,",
                    "    step_outputs: dict[str, Any],",
                    ") -> dict[str, Any]:",
                    f"    return coordinator._run_llm_step({step_name!r}, task, context, step_outputs)",
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def _render_runtime_plugin_source(self, *, stem: str, step_names: list[str], handlers_module: str) -> str:
        import_lines = ",\n    ".join(f"handle_{item}_step" for item in step_names)
        manifest_steps = ",\n".join(
            [
                (
                    "                ExecutionHandlerPluginStepSpec(\n"
                    "                    executor_type=\"tool\",\n"
                    f"                    step_name={step_name!r},\n"
                    f"                    handler=lambda step, task, context, step_outputs: handle_{step_name}_step(\n"
                    "                        coordinator, step, task, context, step_outputs\n"
                    "                    ),\n"
                    f"                    description=\"Runtime scaffolded handler for {step_name}.\",\n"
                    "                )"
                )
                for step_name in step_names
            ]
        )
        class_name = "".join(part.capitalize() for part in stem.split("_")) + "RuntimePlugin"
        factory_name = f"{stem}_execution_handler_plugin"
        return (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from nethub_runtime.core.services.execution_handler_registry import (\n"
            "    ExecutionHandlerPluginManifest,\n"
            "    ExecutionHandlerPluginStepSpec,\n"
            ")\n"
            f"from {handlers_module} import (\n"
            f"    {import_lines}\n"
            ")\n\n"
            "# Generated by NestHub runtime plugin scaffold.\n\n"
            f"class {class_name}:\n"
            "    def build_manifest(self, coordinator: Any) -> ExecutionHandlerPluginManifest:\n"
            "        return ExecutionHandlerPluginManifest(\n"
            f"            name={stem!r},\n"
            "            version=\"1.0\",\n"
            "            steps=[\n"
            f"{manifest_steps}\n"
            "            ],\n"
            "        )\n\n"
            f"def {factory_name}() -> {class_name}:\n"
            f"    return {class_name}()\n"
        )

    def _ensure_execution_plugin_config(self, plugin_entry: str) -> None:
        payload: dict[str, Any]
        if PLUGIN_CONFIG_PATH.exists():
            try:
                payload = json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        else:
            payload = {}
        entries = [str(item) for item in list(payload.get("execution_handler_registry_plugins") or []) if str(item).strip()]
        if plugin_entry not in entries:
            entries.append(plugin_entry)
        payload["execution_handler_registry_plugins"] = entries
        payload.setdefault("intent_analyzer_plugins", [])
        payload.setdefault("task_decomposer_plugins", [])
        payload.setdefault("workflow_planner_plugins", [])
        PLUGIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLUGIN_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _maybe_scaffold_runtime_plugin_for_missing_step(self, step_name: str) -> dict[str, Any]:
        if not self._runtime_plugin_scaffold_enabled():
            return {"status": "disabled", "step_name": step_name}
        safe_step = str(step_name or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]+", safe_step):
            return {"status": "invalid_step_name", "step_name": step_name}

        if safe_step in self._step_handlers.get("tool", {}):
            return {"status": "already_registered", "step_name": safe_step}

        root = self._runtime_workspace_root()
        services_dir = (root / "nethub_runtime" / "core" / "services").resolve()
        services_dir.mkdir(parents=True, exist_ok=True)
        stem = self._runtime_plugin_stem(safe_step)
        handlers_file = services_dir / f"{stem}_runtime_handlers.py"
        plugin_file = services_dir / f"{stem}_runtime_plugin.py"
        handlers_module = f"nethub_runtime.core.services.{stem}_runtime_handlers"
        plugin_module = f"nethub_runtime.core.services.{stem}_runtime_plugin"
        factory_name = f"{stem}_execution_handler_plugin"
        plugin_entry = f"{plugin_module}:{factory_name}"

        handlers_source = self._render_runtime_handlers_source([safe_step])
        plugin_source = self._render_runtime_plugin_source(
            stem=stem,
            step_names=[safe_step],
            handlers_module=handlers_module,
        )
        handlers_file.write_text(handlers_source, encoding="utf-8")
        plugin_file.write_text(plugin_source, encoding="utf-8")
        self._ensure_execution_plugin_config(plugin_entry)

        # Register the step immediately for the current process.
        self._step_handlers.setdefault("tool", {})
        self._step_handlers["tool"][safe_step] = (
            lambda step, task, context, step_outputs, _name=safe_step: self._run_llm_step(_name, task, context, step_outputs)
        )
        return {
            "status": "scaffolded",
            "step_name": safe_step,
            "plugin_entry": plugin_entry,
            "handlers_file": str(handlers_file),
            "plugin_file": str(plugin_file),
        }

    def _dispatch_llm_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run_llm_step(step["name"], task, context, step_outputs)

    def _dispatch_code_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run_code_step(step["name"], task, context, step_outputs)

    def _run_llm_step(self, step_name: str, task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]) -> dict[str, Any]:
        if self.model_router is None:
            return {"message": f"llm step placeholder for {step_name}", "input_text": task.input_text, "session_id": context.session_id}

        # Pass all prior step outputs so LLM-planned steps can chain naturally.
        # Truncate each value to keep the prompt manageable.
        summarized_outputs = {
            key: (json.dumps(value, ensure_ascii=False)[:400] if not isinstance(value, str) else value[:400])
            for key, value in step_outputs.items()
        }
        prompt = (
            "Execute the requested workflow step and return a concise plain-text result.\n"
            f"step_name: {step_name}\n"
            f"task_intent: {task.intent}\n"
            f"input_text: {task.input_text}\n"
            f"session_id: {context.session_id}\n"
            f"step_outputs: {json.dumps(summarized_outputs, ensure_ascii=False)[:2000]}"
        )
        response = self._invoke_model_text(
            task_type="llm_execution",
            prompt=prompt,
            system_prompt="You are the NestHub runtime execution model. Follow the step request and return plain text only.",
        )
        if not response:
            return {"message": f"llm step placeholder for {step_name}", "input_text": task.input_text, "session_id": context.session_id}
        if step_name == "analyze_workflow_context":
            return {
                "status": "completed",
                "analysis": response,
                "summary": response,
                "input_text": task.input_text,
                "session_id": context.session_id,
                "model_routed": True,
            }
        return {
            "status": "completed",
            "message": response,
            "input_text": task.input_text,
            "session_id": context.session_id,
            "model_routed": True,
        }

    def _run_code_step(
        self,
        step_name: str,
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "message": f"code step placeholder for {step_name}",
            "input_text": task.input_text,
            "session_id": context.session_id,
            "available_step_outputs": list(step_outputs.keys()),
        }

    def _normalize_yes_no(self, text: str) -> bool:
        lowered = self._normalize_text(text)
        boolean_aliases = self.semantic_policy.get("boolean_aliases", {})
        truthy_aliases = boolean_aliases.get("truthy", ["yes", "true", "y", "1"])
        normalized_aliases = {self._normalize_text(str(item)) for item in truthy_aliases if str(item).strip()}
        return lowered in normalized_aliases or any(token and token in lowered for token in normalized_aliases)

    def _sanitize_member_value(self, key: str, text: str) -> Any:
        value = text.strip()
        if key == "details":
            for phrase in self._information_collection_phrases():
                value = value.replace(phrase, "").strip()
            return value
        return value

    def _information_collection_phrases(self) -> list[str]:
        payload = self.semantic_policy.get("information_collection", {})
        phrases = payload.get("completion_phrases", []) if isinstance(payload, dict) else []
        if not phrases:
            store_policy = self.semantic_policy_store.load_runtime_policy()
            store_payload = store_policy.get("information_collection", {}) if isinstance(store_policy, dict) else {}
            phrases = store_payload.get("completion_phrases", []) if isinstance(store_payload, dict) else []
        return [str(item).strip() for item in phrases if str(item).strip()]

    def _manage_information_agent(self, text: str, task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
        return self.information_agent_service.manage_information_agent(
            text=text,
            task=task,
            context=context,
            normalize_yes_no=self._normalize_yes_no,
            sanitize_member_value=self._sanitize_member_value,
            extract_records=self._extract_records,
        )

    def _query_information_knowledge(self, text: str, context: CoreContextSchema) -> dict[str, Any]:
        return self.information_agent_service.query_information_knowledge(text=text, context=context)

    def _build_runtime_install_plan(self, missing_items: list[str]) -> dict[str, Any]:
        return self.dependency_manager.build_install_plan(missing_items)

    def _execute_runtime_install_plan(self, install_plan: dict[str, Any]) -> dict[str, Any]:
        return self.dependency_manager.execute_install_plan(
            install_plan,
            allowed_installers=self.security_guard.allowed_runtime_installers(),
        )

    def _allow_runtime_auto_install(self) -> bool:
        return self.security_guard.allow_runtime_auto_install()

    def _autonomous_implementation_policy(self) -> dict[str, Any]:
        runtime_behavior = self.semantic_policy_store.load_runtime_policy().get("runtime_behavior", {})
        payload = runtime_behavior.get("autonomous_implementation", {}) if isinstance(runtime_behavior, dict) else {}
        return payload if isinstance(payload, dict) else {}

    def _runtime_workspace_root(self) -> Path:
        policy = self._autonomous_implementation_policy()
        env_name = str(policy.get("workspace_root_env") or "NETHUB_RUNTIME_WORKSPACE_ROOT").strip() or "NETHUB_RUNTIME_WORKSPACE_ROOT"
        env_root = os.getenv(env_name, "").strip()
        root = Path(env_root).expanduser() if env_root else Path.cwd()
        return root.resolve()

    def _normalize_runtime_patch_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        summary = str(plan.get("summary") or "runtime patch generated")
        validation_commands = plan.get("validation_commands") if isinstance(plan.get("validation_commands"), list) else []

        if isinstance(plan.get("file_patches"), list):
            file_patches: list[dict[str, Any]] = []
            for item in plan.get("file_patches", []):
                if not isinstance(item, dict):
                    continue
                target_file = str(item.get("target_file") or "").strip()
                operations = item.get("operations") if isinstance(item.get("operations"), list) else []
                updated_content = item.get("updated_content") if isinstance(item.get("updated_content"), str) else None
                if not target_file:
                    continue
                file_patches.append(
                    {
                        "target_file": target_file,
                        "operations": operations,
                        "updated_content": updated_content,
                    }
                )
            return {
                "summary": summary,
                "validation_commands": [str(item) for item in validation_commands if str(item).strip()],
                "file_patches": file_patches,
            }

        target_file = str(plan.get("target_file") or "").strip()
        updated_content = plan.get("updated_content") if isinstance(plan.get("updated_content"), str) else None
        if not target_file or updated_content is None:
            return {
                "summary": summary,
                "validation_commands": [str(item) for item in validation_commands if str(item).strip()],
                "file_patches": [],
            }
        return {
            "summary": summary,
            "validation_commands": [str(item) for item in validation_commands if str(item).strip()],
            "file_patches": [
                {
                    "target_file": target_file,
                    "operations": [],
                    "updated_content": updated_content,
                }
            ],
        }

    def _apply_runtime_patch_operations(self, current_content: str, operations: list[Any]) -> str:
        updated_content = current_content
        for item in operations:
            if not isinstance(item, dict):
                raise ValueError("patch operation must be an object")
            op_name = str(item.get("op") or item.get("type") or "").strip()
            if op_name == "replace_text":
                old_text = item.get("old_text")
                new_text = item.get("new_text")
                if not isinstance(old_text, str) or not isinstance(new_text, str):
                    raise ValueError("replace_text requires string old_text and new_text")
                occurrences = updated_content.count(old_text)
                if occurrences != 1:
                    raise ValueError(f"replace_text expects exactly one match, found {occurrences}")
                updated_content = updated_content.replace(old_text, new_text, 1)
                continue
            if op_name in {"insert_after", "insert_before"}:
                anchor_text = item.get("anchor_text")
                text = item.get("text")
                if not isinstance(anchor_text, str) or not isinstance(text, str):
                    raise ValueError(f"{op_name} requires string anchor_text and text")
                occurrences = updated_content.count(anchor_text)
                if occurrences != 1:
                    raise ValueError(f"{op_name} expects exactly one anchor match, found {occurrences}")
                index = updated_content.index(anchor_text)
                insert_at = index + len(anchor_text) if op_name == "insert_after" else index
                updated_content = updated_content[:insert_at] + text + updated_content[insert_at:]
                continue
            if op_name == "append_text":
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError("append_text requires string text")
                updated_content = updated_content + text
                continue
            raise ValueError(f"unsupported patch operation: {op_name}")
        return updated_content

    def _generate_runtime_patch(self, *, task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]) -> dict[str, Any]:
        policy = self._autonomous_implementation_policy()
        if not bool(policy.get("enabled", False)):
            return {"status": "failed", "message": "autonomous implementation disabled"}
        if self.model_router is None:
            return {"status": "failed", "message": "model router unavailable for runtime patch generation"}

        workspace_root = self._runtime_workspace_root()
        analysis_output = step_outputs.get("analyze_workflow_context", {})
        analysis_text = analysis_output.get("summary") or analysis_output.get("analysis") or task.input_text
        prompt = (
            "Return valid JSON only. Build a minimal runtime repair patch plan.\n"
            "Preferred schema: {\"summary\": string, \"file_patches\": [{\"target_file\": string, \"operations\": [{\"op\": \"replace_text\", \"old_text\": string, \"new_text\": string} | {\"op\": \"insert_after\", \"anchor_text\": string, \"text\": string} | {\"op\": \"insert_before\", \"anchor_text\": string, \"text\": string}] }], \"validation_commands\": [string]}.\n"
            "Fallback legacy schema: {\"summary\": string, \"target_file\": string, \"updated_content\": string, \"validation_commands\": [string]}.\n"
            "Rules: target_file must be workspace-relative. Prefer precise replace_text or anchored insert operations over full-file rewrites. Any anchor_text must match exactly once. Use append_text only when necessary. validation_commands must be minimal.\n"
            f"workspace_root: {workspace_root}\n"
            f"task_intent: {task.intent}\n"
            f"input_text: {task.input_text}\n"
            f"analysis: {analysis_text}\n"
            f"step_outputs: {json.dumps(step_outputs, ensure_ascii=False)[:4000]}"
        )
        raw = self._invoke_model_text(
            task_type="llm_execution",
            prompt=prompt,
            system_prompt="You are the NestHub autonomous repair planner. Return JSON only.",
            temperature=0,
        )
        if not raw:
            return {"status": "failed", "message": "empty runtime patch plan"}

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()
        try:
            plan = json.loads(cleaned)
        except Exception:
            artifact_path = self.generated_artifact_store.persist("code", f"runtime_patch_{context.trace_id}", raw, extension=".txt")
            return {"status": "failed", "message": "invalid runtime patch plan", "patch_artifact_path": str(artifact_path)}

        if not isinstance(plan, dict):
            return {"status": "failed", "message": "runtime patch plan is not an object"}

        root = workspace_root
        allowed_extensions = {str(item) for item in policy.get("allowed_file_extensions", [])}
        if not bool(policy.get("allow_workspace_file_modification", False)):
            return {"status": "failed", "message": "workspace file modification disabled", "patch_plan": plan}

        normalized_plan = self._normalize_runtime_patch_plan(plan)
        file_patches = normalized_plan.get("file_patches", [])
        if not file_patches:
            return {"status": "failed", "message": "runtime patch plan missing file patches", "patch_plan": plan}
        max_files_per_patch = int(policy.get("max_files_per_patch", 3) or 3)
        if len(file_patches) > max_files_per_patch:
            return {
                "status": "failed",
                "message": f"runtime patch plan exceeds max files per patch: {len(file_patches)} > {max_files_per_patch}",
                "patch_plan": normalized_plan,
            }

        patched_files: list[str] = []
        backups: list[dict[str, str]] = []
        total_written_bytes = 0
        for file_patch in file_patches:
            target_file = str(file_patch.get("target_file") or "").strip()
            target_path = (root / target_file).resolve()
            try:
                target_path.relative_to(root)
            except ValueError:
                return {"status": "failed", "message": "target file escapes workspace root", "patch_plan": normalized_plan}
            if allowed_extensions and target_path.suffix not in allowed_extensions:
                return {"status": "failed", "message": f"target file extension not allowed: {target_path.suffix}", "patch_plan": normalized_plan}

            previous_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            operations = file_patch.get("operations") if isinstance(file_patch.get("operations"), list) else []
            if operations:
                try:
                    next_content = self._apply_runtime_patch_operations(previous_content, operations)
                except ValueError as exc:
                    return {"status": "failed", "message": str(exc), "patch_plan": normalized_plan}
            else:
                next_content = file_patch.get("updated_content")
                if not isinstance(next_content, str):
                    return {"status": "failed", "message": "runtime patch plan missing updated content", "patch_plan": normalized_plan}

            total_written_bytes += len(next_content.encode("utf-8"))
            max_total_written_bytes = int(policy.get("max_total_written_bytes", 20000) or 20000)
            if total_written_bytes > max_total_written_bytes:
                return {
                    "status": "failed",
                    "message": f"runtime patch plan exceeds max written bytes: {total_written_bytes} > {max_total_written_bytes}",
                    "patch_plan": normalized_plan,
                }

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(next_content, encoding="utf-8")
            backup_path = self.generated_artifact_store.persist("code", f"runtime_patch_backup_{context.trace_id}_{len(backups)}", previous_content, extension=target_path.suffix or ".txt")
            backups.append({"target_file": target_file, "backup_path": str(backup_path)})
            patched_files.append(str(target_path))

        artifact_payload = {
            "summary": normalized_plan.get("summary") or "runtime patch generated",
            "file_patches": normalized_plan.get("file_patches", []),
            "validation_commands": normalized_plan.get("validation_commands", []),
            "trace_id": context.trace_id,
            "backups": backups,
            "total_written_bytes": total_written_bytes,
        }
        artifact_path = self.generated_artifact_store.persist("code", f"runtime_patch_{context.trace_id}", artifact_payload)
        return {
            "status": "patched",
            "patch_plan": artifact_payload,
            "patch_artifact_path": str(artifact_path),
            "patched_files": patched_files,
            "message": str(normalized_plan.get("summary") or f"patched {len(patched_files)} file(s)"),
        }

    def _run_runtime_validation(self, *, context: CoreContextSchema, patch_payload: dict[str, Any]) -> dict[str, Any]:
        policy = self._autonomous_implementation_policy()
        commands = [str(item).strip() for item in list(patch_payload.get("patch_plan", {}).get("validation_commands", [])) if str(item).strip()]
        if not commands:
            return {"status": "failed", "validation_results": [], "executed_commands": [], "message": "no validation commands provided"}

        allowed_prefixes = {str(item).strip() for item in policy.get("validation_command_prefixes", []) if str(item).strip()}
        timeout_sec = int(policy.get("validation_timeout_sec", 120) or 120)
        workspace_root = self._runtime_workspace_root()
        results: list[dict[str, Any]] = []
        executed_commands: list[str] = []
        overall_ok = True
        for command in commands:
            parts = shlex.split(command)
            if not parts:
                continue
            if allowed_prefixes and parts[0] not in allowed_prefixes:
                results.append({"command": command, "status": "blocked", "reason": "prefix_not_allowed"})
                overall_ok = False
                continue
            started_at = time.time()
            try:
                proc = subprocess.run(parts, cwd=str(workspace_root), capture_output=True, text=True, timeout=timeout_sec)
                executed_commands.append(command)
                result = {
                    "command": command,
                    "exit_code": int(proc.returncode),
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-4000:],
                    "duration_sec": round(time.time() - started_at, 3),
                    "status": "passed" if proc.returncode == 0 else "failed",
                }
                if proc.returncode != 0:
                    overall_ok = False
                results.append(result)
            except Exception as exc:
                overall_ok = False
                results.append({"command": command, "status": "error", "error": str(exc)})

        return {
            "status": "validated" if overall_ok else "failed",
            "validation_results": results,
            "executed_commands": executed_commands,
            "message": "runtime validation completed" if overall_ok else "runtime validation failed",
        }

    def _verify_runtime_patch(self, *, context: CoreContextSchema, patch_payload: dict[str, Any], validation_payload: dict[str, Any]) -> dict[str, Any]:
        results = validation_payload.get("validation_results", []) if isinstance(validation_payload, dict) else []
        passed = bool(results) and all(item.get("status") == "passed" for item in results if isinstance(item, dict))
        if passed:
            return {
                "status": "verified",
                "verified": True,
                "patched_files": patch_payload.get("patched_files", []),
                "message": "runtime patch verified successfully",
            }
        return {
            "status": "verification_failed",
            "verified": False,
            "patched_files": patch_payload.get("patched_files", []),
            "validation_results": results,
            "message": "runtime patch verification failed",
        }

    def _extract_records(self, text: str) -> list[dict[str, Any]]:
        model_records = self._model_parse_records(text)
        if model_records is not None:
            return model_records

        split_patterns = self._require_semantic_value("segment_split_patterns", list)
        split_regex = "|".join(f"(?:{pattern})" for pattern in split_patterns)
        segments = [segment.strip() for segment in re.split(split_regex, text) if segment.strip()]
        records: list[dict[str, Any]] = []
        for segment in segments:
            record_type = self._infer_record_type(segment)
            records.append(
                {
                    "record_type": record_type,
                    "time": self._extract_time(segment),
                    "location": self._extract_location(segment),
                    "content": self._extract_content(segment),
                    "amount": self._extract_amount(segment) or 0,
                    "participants": self._extract_participants(segment),
                    "actor": self._extract_actor(segment),
                    "label": self._infer_label(segment),
                    "raw_text": segment,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        self._learn_semantic_candidates(text, stage="record_extraction")
        return records

    def _extract_amount(self, text: str) -> int | None:
        for pattern in self.intent_policy.get("numeric_value_patterns", []):
            matched = re.search(pattern, text, flags=re.IGNORECASE)
            if matched:
                value = matched.group(1)
                if value:
                    return int(float(value))
        fallback = re.search(r"(\d+(?:\.\d+)?)", text)
        if fallback:
            return int(float(fallback.group(1)))
        return None

    def _extract_time(self, text: str) -> str:
        explicit_date = self._extract_explicit_date(text)
        if explicit_date:
            return explicit_date
        relative_week_date = self._extract_relative_week_date(text)
        if relative_week_date:
            return relative_week_date
        for marker in self._time_markers():
            if marker and marker in text:
                return marker
        return "unspecified"

    def _extract_location(self, text: str) -> str | None:
        markers = self._require_semantic_value("location_markers", list)
        for marker in markers:
            if marker in text:
                candidate = text.split(marker, 1)[-1].strip()
                return re.split(r"[，,。 ]", candidate)[0] or None
        return None

    def _extract_content(self, text: str) -> str:
        cleaned = text
        for pattern in self._require_semantic_value("content_cleanup_patterns", list):
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(str(self.semantic_policy.get("content_strip_chars", " ")))
        return cleaned or "entry"

    def _extract_participants(self, text: str) -> int | None:
        participant_pattern = self._require_semantic_value("participant_pattern", str)
        match = re.search(participant_pattern, text)
        if match:
            return int(match.group(1))
        participant_aliases = self._require_semantic_value("participant_aliases", dict)
        for alias, count in participant_aliases.items():
            if alias in text:
                return int(count)
        return None

    def _extract_actor(self, text: str) -> str:
        named_actor = self._extract_named_actor(text)
        if named_actor:
            return named_actor
        alias = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
        normalized = self._normalize_text(text)
        for canonical, aliases in alias.items():
            if any(self._normalize_text(a) in normalized for a in aliases):
                return canonical
        return "self"

    def _extract_named_actor(self, text: str) -> str | None:
        patterns = self.semantic_policy.get("actor_extract_patterns", [])
        if not isinstance(patterns, list):
            return None
        for pattern in patterns:
            try:
                match = re.match(str(pattern), text.strip())
            except re.error:
                continue
            if match:
                return match.group(1)
        return None

    def _extract_explicit_date(self, text: str) -> str | None:
        rules = self.semantic_policy.get("explicit_date_patterns", [])
        if not isinstance(rules, list):
            return None
        now = datetime.now(UTC)
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("pattern") or "").strip()
            if not pattern:
                continue
            try:
                match = re.search(pattern, text)
            except re.error:
                continue
            if not match:
                continue
            month_group = int(rule.get("month_group", 1))
            day_group = int(rule.get("day_group", 2))
            year_group = rule.get("year_group")
            try:
                month = int(match.group(month_group))
                day = int(match.group(day_group))
                year = int(match.group(int(year_group))) if year_group is not None else now.year
            except (IndexError, TypeError, ValueError):
                continue
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    def _extract_relative_week_date(self, text: str) -> str | None:
        rules = self.semantic_policy.get("relative_week_rules", [])
        if not isinstance(rules, list):
            return None
        now = datetime.now(UTC)
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("pattern") or "").strip()
            weekday_map = rule.get("weekday_map", {})
            if not pattern or not isinstance(weekday_map, dict):
                continue
            try:
                match = re.search(pattern, text)
            except re.error:
                continue
            if not match:
                continue
            weekday_token = str(match.group(int(rule.get("weekday_group", 1))))
            if weekday_token not in weekday_map:
                continue
            target_weekday = int(weekday_map[weekday_token])
            week_start = str(rule.get("week_start") or "monday").lower()
            base_offset = now.weekday() if week_start == "monday" else (now.weekday() + 1) % 7
            period_start = now - timedelta(days=base_offset)
            target = period_start + timedelta(days=target_weekday)
            return target.date().isoformat()
        return None

    def _infer_record_type(self, text: str) -> str:
        record_type_rules = self.semantic_policy.get("record_type_rules", {})
        if isinstance(record_type_rules, dict):
            for record_type, rule in record_type_rules.items():
                if not isinstance(rule, dict) or rule.get("default"):
                    continue
                if self._rule_matches_text(text, rule):
                    return str(record_type)
        return "generic"

    def _rule_matches_text(self, text: str, rule: dict[str, Any]) -> bool:
        if rule.get("require_time") and self._extract_time(text) == "unspecified":
            return False
        required_any = [str(item) for item in rule.get("required_any", []) if str(item).strip()]
        reject_any = [str(item) for item in rule.get("reject_any", []) if str(item).strip()]
        if required_any and not any(marker in text for marker in required_any):
            return False
        if reject_any and any(marker in text for marker in reject_any):
            return False
        return True

    def _infer_label(self, text: str) -> str:
        semantic_label = self._semantic_label_from_text(text)
        if semantic_label:
            return semantic_label
        return "other"

    def _parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any]:
        model_query = self._model_parse_query(text, existing_records)
        if model_query is not None:
            return model_query

        stopwords = self._query_stopwords()
        ignored_tokens = set(self.semantic_policy.get("ignored_query_tokens", []))
        generic_action_terms = self._generic_query_action_terms()
        normalized = text
        for stopword in stopwords:
            normalized = normalized.replace(stopword, " ")
        tokens = self._tokenize(normalized)
        terms = [
            tok
            for tok in tokens
            if tok not in stopwords
            and tok not in ignored_tokens
            and self._normalize_text(tok) not in generic_action_terms
        ]

        filters = self._infer_alias_filters(text)
        semantic_label = self._semantic_label_from_text(text)
        if semantic_label and self._query_has_explicit_label_signal(text, semantic_label):
            filters["label"] = semantic_label
        for pattern in self._require_semantic_value("location_keyword_patterns", list):
            matched = re.search(pattern, text)
            if matched:
                filters["location_keyword"] = matched.group(1)
                break

        record_matched_terms = self._find_terms_from_records(text, existing_records)
        dynamic_terms = record_matched_terms or self._extract_dynamic_terms(terms, existing_records)
        group_by = self._extract_group_by(text)
        query = {
            "metric": self._infer_query_metric(text, existing_records),
            "terms": dynamic_terms,
            "group_by": group_by,
            "time_marker": self._extract_time(text),
            "filters": filters,
            "query_text": text,
        }
        self._learn_semantic_candidates(text, stage="query_parsing")
        return query

    def _infer_query_metric(self, text: str, existing_records: list[dict[str, Any]]) -> str:
        metric_rules = self.semantic_policy.get("query_metric_rules", {})
        if isinstance(metric_rules, dict):
            for metric, rule in metric_rules.items():
                if not isinstance(rule, dict):
                    continue
                required_type = rule.get("requires_record_type")
                if required_type and not any(item.get("record_type") == required_type for item in existing_records):
                    continue
                if self._rule_matches_text(text, rule):
                    return str(metric)
        return "list"

    def _query_has_explicit_label_signal(self, text: str, label: str) -> bool:
        normalized_text = self._normalize_text(text)
        synonym_map = self.semantic_policy.get("normalization", {}).get("synonyms", {})
        taxonomy = self.semantic_policy.get("label_taxonomy", {})
        label_config = taxonomy.get(label, {}) if isinstance(taxonomy, dict) else {}
        examples = label_config.get("examples", []) if isinstance(label_config, dict) else []
        lexical_hints = {
            self._normalize_text(str(item))
            for item in [*synonym_map.get(label, []), *examples]
            if len(self._normalize_text(str(item))) >= 2
        }
        return any(hint in normalized_text for hint in lexical_hints)

    def _find_terms_from_records(self, query_text: str, existing_records: list[dict[str, Any]]) -> list[str]:
        terms: list[str] = []
        query_tokens = self._tokenize(query_text)
        ignored_tokens = {
            self._normalize_text(token)
            for token in self.semantic_policy.get("ignored_query_tokens", [])
        }
        ignored_tokens.update(self._generic_query_action_terms())
        norm_query = self._normalize_text(query_text)
        for item in existing_records:
            for field in ("content", "location", "label", "actor"):
                value = self._normalize_text(str(item.get(field, "")).strip())
                if len(value) < 2:
                    continue
                if value in norm_query and value not in terms:
                    if value in ignored_tokens:
                        continue
                    terms.append(value)
                    continue
                for token in query_tokens:
                    normalized_token = self._normalize_text(token)
                    if normalized_token in ignored_tokens:
                        continue
                    if token in value and token not in terms:
                        terms.append(token)
        return terms

    def _generic_query_action_terms(self) -> set[str]:
        configured_terms = self.semantic_policy.get("aggregation_query", {}).get("generic_action_terms", [])
        if not configured_terms:
            store_policy = self.semantic_policy_store.load_runtime_policy()
            store_payload = store_policy.get("aggregation_query", {}) if isinstance(store_policy, dict) else {}
            configured_terms = store_payload.get("generic_action_terms", []) if isinstance(store_payload, dict) else []
        return {
            self._normalize_text(term)
            for term in configured_terms
            if str(term).strip()
        }

    def _extract_dynamic_terms(self, terms: list[str], existing_records: list[dict[str, Any]]) -> list[str]:
        if not existing_records:
            return terms
        corpus = " ".join(
            self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            for item in existing_records
        )
        ignored_tokens = self._generic_query_action_terms()
        return [
            self._normalize_text(term)
            for term in terms
            if self._normalize_text(term) in corpus and self._normalize_text(term) not in ignored_tokens
        ]

    def _extract_group_by(self, text: str) -> list[str]:
        results: list[str] = []
        marker_map = self._require_semantic_value("group_by_aliases", dict)
        markers = list(marker_map.keys())
        for marker in markers:
            if marker in text and marker in marker_map:
                results.append(marker_map[marker])
        return results

    def _time_markers(self) -> list[str]:
        markers: list[str] = []
        explicit_markers = self.semantic_policy.get("time_markers", [])
        if isinstance(explicit_markers, list):
            for marker in explicit_markers:
                marker_text = str(marker).strip()
                if marker_text and marker_text not in markers:
                    markers.append(marker_text)
        rules = self.semantic_policy.get("time_marker_rules", {})
        if isinstance(rules, dict):
            for rule in rules.values():
                if not isinstance(rule, dict):
                    continue
                for alias in rule.get("aliases", []):
                    alias_text = str(alias).strip()
                    if alias_text and alias_text not in markers:
                        markers.append(alias_text)
                for alias in rule.get("record_aliases", []):
                    alias_text = str(alias).strip()
                    if alias_text and alias_text not in markers:
                        markers.append(alias_text)
                for prefix in rule.get("prefixes", []):
                    prefix_text = str(prefix).strip()
                    if prefix_text and prefix_text not in markers:
                        markers.append(prefix_text)
        return markers

    def _query_stopwords(self) -> set[str]:
        stopwords: set[str] = set()
        semantic_stopwords = self.semantic_policy.get("ignored_query_tokens", [])
        if isinstance(semantic_stopwords, list):
            stopwords.update(str(item) for item in semantic_stopwords if str(item).strip())
        legacy_stopwords = self.intent_policy.get("stopwords", [])
        if isinstance(legacy_stopwords, list):
            stopwords.update(str(item) for item in legacy_stopwords if str(item).strip())
        return stopwords

    def _model_parse_records(self, text: str) -> list[dict[str, Any]] | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True) or not parser_cfg.get("prefer_model_for_record_extraction", True):
            return None

        payload = {
            "instruction": "Extract structured records from input_text and return a records array with time, location, content, amount, participants, actor, label, and raw_text.",
            "input_text": text,
            "schema": {
                "records": [
                    {
                        "time": "string",
                        "location": "string|null",
                        "content": "string",
                        "amount": "number",
                        "participants": "number|null",
                        "actor": "string",
                        "label": "string",
                        "raw_text": "string",
                    }
                ]
            },
        }
        data = self._call_semantic_parser(payload, task_type="semantic_parsing")
        if not data:
            return None

        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            return None

        normalized_records: list[dict[str, Any]] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            try:
                amount = int(float(item.get("amount", 0)))
            except Exception:
                continue
            normalized_records.append(
                {
                    "time": str(item.get("time") or "unspecified"),
                    "location": item.get("location"),
                    "content": str(item.get("content") or "entry"),
                    "amount": amount,
                    "participants": item.get("participants"),
                    "actor": str(item.get("actor") or "self"),
                    "label": str(item.get("label") or "other"),
                    "raw_text": str(item.get("raw_text") or text),
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        return normalized_records or None

    def _model_parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any] | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True) or not parser_cfg.get("prefer_model_for_query_parsing", True):
            return None

        payload = {
            "instruction": "Parse query_text into an aggregate query and return metric, terms, group_by, time_marker, filters, and query_text.",
            "query_text": text,
            "existing_records": existing_records,
            "schema": {
                "metric": "sum",
                "terms": ["string"],
                "group_by": ["time|label|location|actor"],
                "time_marker": "string",
                "filters": {"actor": "string", "label": "string", "location_keyword": "string"},
                "query_text": "string",
            },
        }
        data = self._call_semantic_parser(payload, task_type="semantic_parsing")
        if not data:
            return None

        required = ("metric", "terms", "group_by", "time_marker", "filters", "query_text")
        if not all(key in data for key in required):
            return None
        if not isinstance(data.get("terms"), list) or not isinstance(data.get("group_by"), list):
            return None
        if not isinstance(data.get("filters"), dict):
            return None
        return {
            "metric": data.get("metric") or "sum",
            "terms": [self._normalize_text(str(t)) for t in data.get("terms", []) if str(t).strip()],
            "group_by": [str(dim) for dim in data.get("group_by", []) if str(dim).strip()],
            "time_marker": str(data.get("time_marker") or "unspecified"),
            "filters": {str(k): v for k, v in data.get("filters", {}).items() if v not in (None, "")},
            "query_text": str(data.get("query_text") or text),
        }

    def _call_semantic_parser(self, payload: dict[str, Any], *, task_type: str) -> dict[str, Any] | None:
        model_result = self._call_model_semantic_parser(payload, task_type=task_type)
        if model_result is not None:
            return model_result
        return self._call_external_semantic_parser(payload)

    def _call_model_semantic_parser(self, payload: dict[str, Any], *, task_type: str) -> dict[str, Any] | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True) or self.model_router is None:
            return None

        prompt = (
            "Return valid JSON only.\n"
            "Follow the provided instruction and output exactly the requested schema.\n"
            f"payload: {json.dumps(payload, ensure_ascii=False)}"
        )
        response = self._invoke_model_text(
            task_type=task_type,
            prompt=prompt,
            system_prompt="You are the semantic parser for NestHub runtime. Return JSON only and do not add markdown fences.",
            temperature=0,
        )
        if not response:
            return None
        try:
            return json.loads(response)
        except Exception:
            return None

    def _call_external_semantic_parser(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        router = self.semantic_policy.get("external_semantic_router", {})
        if not router.get("enabled", False):
            return None

        endpoint = os.getenv(router.get("generic_endpoint_env", "NETHUB_LLM_ROUTER_ENDPOINT"), "").strip()
        if not endpoint:
            return None

        request_body = {
            "task": "semantic_parse",
            "provider_priority": router.get("provider_priority", []),
            "payload": payload,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(endpoint, json=request_body)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            LOGGER.debug("External semantic parse failed: %s", exc)
            return None
        return None

    def _invoke_model_text(
        self,
        *,
        task_type: str,
        prompt: str,
        system_prompt: str,
        **kwargs: Any,
    ) -> str | None:
        if self.model_router is None:
            return None

        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                holder["response"] = asyncio.run(
                    self.model_router.invoke(
                        task_type=task_type,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        **kwargs,
                    )
                )
            except Exception as exc:
                holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=20)
        raw = holder.get("response")
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()
        return cleaned or None

    def _aggregate_records(self, records: list[dict[str, Any]], query: dict[str, Any], model_choice: dict[str, Any]) -> dict[str, Any]:
        filters = query.get("filters", {})
        group_by = query.get("group_by", [])
        time_marker = query.get("time_marker")
        metric = str(query.get("metric", "sum"))
        belonging_keys = ["actor", "label", "location_keyword"]
        has_belonging = False
        for k in belonging_keys:
            if k in filters and filters[k]:
                has_belonging = True
        if group_by:
            has_belonging = True
        if time_marker and time_marker != "unspecified":
            has_belonging = True
        if has_belonging:
            LOGGER.debug("Semantic aggregate fallback triggered: filters=%s group_by=%s time_marker=%s", filters, group_by, time_marker)
            prompt_query = dict(query)
            prompt_query["_aggregation_belonging"] = True
            external = self._external_semantic_aggregate(prompt_query, records, model_choice)
            if external is not None:
                return external
        filtered = list(records)
        time_marker = query.get("time_marker")
        if time_marker and time_marker != "unspecified":
            filtered = [item for item in filtered if self._record_matches_time_marker(item, str(time_marker))]
        if "actor" in filters:
            filtered = [item for item in filtered if str(item.get("actor", "")) == str(filters["actor"])]
        if "label" in filters:
            filtered = [item for item in filtered if str(item.get("label", "")) == str(filters["label"])]
        if "location_keyword" in filters:
            keyword = self._normalize_text(str(filters["location_keyword"]))
            filtered = [item for item in filtered if keyword in self._normalize_text(str(item.get("location", "")))]
        terms = query.get("terms", [])
        confidence = 1.0
        if terms:
            strict_filtered = self._strict_term_filter(filtered, terms)
            if strict_filtered:
                filtered = strict_filtered
                confidence = 1.0
            else:
                semantic_filtered, confidence = self._semantic_filter_records(filtered, terms)
                filtered = semantic_filtered
                fallback_threshold = float(self.semantic_policy.get("semantic_matching", {}).get("fallback_to_external_threshold", 0.35))
                if confidence < fallback_threshold:
                    external = self._external_semantic_aggregate(query, records, model_choice)
                    if external is not None:
                        return external
        total_amount = sum(int(item.get("amount", 0)) for item in filtered)
        grouped: dict[str, dict[str, int]] = {}
        for dim in query.get("group_by", []):
            grouped[dim] = {}
            for item in filtered:
                key = str(item.get(dim, "unknown"))
                grouped[dim][key] = grouped[dim].get(key, 0) + int(item.get("amount", 0))
        response = {
            "total_amount": total_amount,
            "count": len(filtered),
            "grouped": grouped,
            "semantic_mode": "local",
            "semantic_confidence": round(confidence, 4),
        }
        if metric == "list":
            response["matched_records"] = [
                {
                    "record_type": item.get("record_type", "generic"),
                    "actor": item.get("actor"),
                    "time": item.get("time"),
                    "location": item.get("location"),
                    "content": item.get("content"),
                    "label": item.get("label"),
                }
                for item in filtered
            ]
        return response

    def _strict_term_filter(self, records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
        normalized_terms = [self._normalize_text(term) for term in terms if self._normalize_text(term)]
        if not normalized_terms:
            return []
        strict: list[dict[str, Any]] = []
        for item in records:
            blob = self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            if all(term in blob for term in normalized_terms):
                strict.append(item)
        return strict

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower().strip()
        replace_map = self.semantic_policy.get("normalization", {}).get("text_replace", {})
        for src, target in replace_map.items():
            normalized = normalized.replace(src.lower(), target.lower())
        return normalized

    def _tokenize(self, text: str) -> list[str]:
        text = self._normalize_text(text)
        preferred = self.semantic_policy.get("tokenizer", {}).get("preferred", "regex")
        min_len = int(self.semantic_policy.get("tokenizer", {}).get("min_token_length", 2))
        if preferred == "jieba":
            try:
                import jieba

                tokens = [tok.strip() for tok in jieba.lcut(text) if tok.strip()]
                return [tok for tok in tokens if len(tok) >= min_len]
            except Exception:
                pass
        tokens = [tok for tok in re.split(r"[\s，,。；;！？!?]+", text) if tok]
        return [tok for tok in tokens if len(tok) >= min_len]

    def _infer_alias_filters(self, query_text: str) -> dict[str, str]:
        filters: dict[str, str] = {}
        aliases = self.semantic_policy.get("entity_aliases", {})
        normalized_query = self._normalize_text(query_text)
        for field, mapping in aliases.items():
            if field == "label":
                continue
            for canonical, alias_list in mapping.items():
                if any(self._normalize_text(alias) in normalized_query for alias in alias_list):
                    filters[field] = canonical
                    break
        return filters

    def _semantic_label_from_text(self, text: str) -> str | None:
        model_label = self._model_infer_label(text)
        if model_label:
            return model_label

        taxonomy = self.semantic_policy.get("label_taxonomy", {})
        if not isinstance(taxonomy, dict) or not taxonomy:
            return None

        normalized_text = self._normalize_text(text)
        scored_labels: list[tuple[float, str]] = []
        threshold = float(self.semantic_policy.get("semantic_label_threshold", 0.32))
        margin_threshold = float(self.semantic_policy.get("semantic_label_margin", 0.08))
        synonym_map = self.semantic_policy.get("normalization", {}).get("synonyms", {})

        for label, config in taxonomy.items():
            if not isinstance(config, dict):
                continue
            description = str(config.get("description", "")).strip()
            examples = config.get("examples", [])
            synonyms = synonym_map.get(str(label), [])
            profile_text = " ".join([description, *[str(item) for item in examples], *[str(item) for item in synonyms]])
            if not profile_text.strip():
                continue
            score = self._embedding_similarity(normalized_text, self._normalize_text(profile_text))
            lexical_hints = {
                self._normalize_text(str(item))
                for item in [*examples, *synonyms]
                if len(self._normalize_text(str(item))) >= 2
            }
            synonym_hints = {
                self._normalize_text(str(item))
                for item in synonyms
                if len(self._normalize_text(str(item))) >= 2
            }
            synonym_hits = sum(1 for hint in synonym_hints if hint and hint in normalized_text)
            lexical_hits = sum(1 for hint in lexical_hints if hint and hint in normalized_text)
            if lexical_hits or synonym_hits:
                score = min(1.0, score + min(0.5, 0.28 * synonym_hits + 0.08 * max(0, lexical_hits - synonym_hits)))
            if lexical_hits > 0:
                score = max(score, min(0.95, 0.45 + 0.1 * lexical_hits))
            scored_labels.append((score, str(label)))

        if not scored_labels:
            return None

        scored_labels.sort(reverse=True)
        best_score, best_label = scored_labels[0]
        second_score = scored_labels[1][0] if len(scored_labels) > 1 else 0.0
        if best_score >= threshold and (best_score - second_score) >= margin_threshold:
            return best_label
        return None

    def _record_matches_time_marker(self, item: dict[str, Any], time_marker: str) -> bool:
        normalized_marker = self._normalize_text(time_marker)
        record_time = self._normalize_text(str(item.get("time", "")))

        if not normalized_marker or normalized_marker == "unspecified":
            return True
        if normalized_marker in record_time:
            return True

        created_at_raw = str(item.get("created_at", "")).strip()
        created_at = None
        if created_at_raw:
            try:
                created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            except Exception:
                created_at = None

        now = datetime.now(UTC)
        for rule in self._require_semantic_value("time_marker_rules", dict).values():
            aliases = {self._normalize_text(alias) for alias in rule.get("aliases", [])}
            if normalized_marker not in aliases:
                continue
            record_aliases = {self._normalize_text(alias) for alias in rule.get("record_aliases", [])}
            if record_time in record_aliases:
                return True
            match_mode = str(rule.get("match_mode", "exact"))
            if match_mode == "same_day":
                return created_at.date() == now.date() if created_at else False
            if match_mode == "same_month":
                return bool(created_at and created_at.year == now.year and created_at.month == now.month)
            if match_mode == "prefix":
                prefixes = [self._normalize_text(prefix) for prefix in rule.get("prefixes", [])]
                return any(record_time.startswith(prefix) for prefix in prefixes)
            return record_time == normalized_marker
        return False

    def _token_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._tokenize(left))
        right_tokens = set(self._tokenize(right))
        if not left_tokens or not right_tokens:
            return 0.0
        inter = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return inter / union if union else 0.0

    def _embedding_similarity(self, left: str, right: str) -> float:
        if self._embedding_model is None:
            return self._token_similarity(left, right)
        try:
            vectors = self._embedding_model.encode([left, right], normalize_embeddings=True)
            dot = float(sum(a * b for a, b in zip(vectors[0], vectors[1])))
            return max(0.0, min(1.0, dot))
        except Exception:
            return self._token_similarity(left, right)

    def _semantic_filter_records(self, records: list[dict[str, Any]], terms: list[str]) -> tuple[list[dict[str, Any]], float]:
        if not records or not terms:
            return records, 1.0
        threshold = float(self.semantic_policy.get("semantic_matching", {}).get("similarity_threshold", 0.62))
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in records:
            text_blob = self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            similarities = [self._embedding_similarity(self._normalize_text(term), text_blob) for term in terms]
            score = max(similarities) if similarities else 0.0
            scored.append((score, item))
        filtered = [item for score, item in scored if score >= threshold]
        confidence = max([score for score, _ in scored], default=0.0)
        # If no semantic hit, keep current filtered set; fallback logic handles low confidence.
        return (filtered if filtered else records, confidence)

    def _external_semantic_aggregate(
        self,
        query: dict[str, Any],
        records: list[dict[str, Any]],
        model_choice: dict[str, Any],
    ) -> dict[str, Any] | None:
        model_payload = {
            "instruction": "Aggregate records according to query relationships and return JSON with total_amount, count, grouped, and optionally matched_records.",
            "query": query,
            "records": records,
            "model_choice": model_choice,
        }
        model_data = self._call_model_semantic_parser(model_payload, task_type="semantic_aggregation")
        if isinstance(model_data, dict) and all(k in model_data for k in ("total_amount", "count", "grouped")):
            model_data["semantic_mode"] = "model_router"
            return model_data

        router = self.semantic_policy.get("external_semantic_router", {})
        if not router.get("enabled", False):
            return None
        endpoint = os.getenv(router.get("generic_endpoint_env", "NETHUB_LLM_ROUTER_ENDPOINT"), "").strip()
        if not endpoint:
            return None
        prompt = {
            "instruction": "Aggregate records according to query relationships and return total_amount, count, and grouped.",
            "query": query,
            "records": records,
            "model_choice": model_choice,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=prompt)
                resp.raise_for_status()
                data = resp.json()
                if all(k in data for k in ("total_amount", "count", "grouped")):
                    data["semantic_mode"] = "external_fallback"
                    return data
        except Exception:
            return None
        return None

    def _learn_semantic_candidates(self, text: str, *, stage: str) -> None:
        policy_memory = self.semantic_policy.get("policy_memory", {})
        learning_cfg = policy_memory.get("learning", {})
        if not policy_memory.get("enabled", False) or not learning_cfg.get("enabled", False):
            return

        payload = {
            "instruction": "Analyze input_text and propose semantic policy candidate deltas for the current runtime. Return only additions for supported keys and skip anything already present.",
            "stage": stage,
            "input_text": text,
            "runtime_policy": {
                "location_markers": self.semantic_policy.get("location_markers", []),
                "participant_aliases": self.semantic_policy.get("participant_aliases", {}),
                "group_by_aliases": self.semantic_policy.get("group_by_aliases", {}),
                "entity_aliases": self.semantic_policy.get("entity_aliases", {}),
                "ignored_query_tokens": self.semantic_policy.get("ignored_query_tokens", []),
                "time_marker_rules": self.semantic_policy.get("time_marker_rules", {}),
                "actor_extract_patterns": self.semantic_policy.get("actor_extract_patterns", []),
                "explicit_date_patterns": self.semantic_policy.get("explicit_date_patterns", []),
                "relative_week_rules": self.semantic_policy.get("relative_week_rules", []),
                "boolean_aliases": self.semantic_policy.get("boolean_aliases", {}),
                "record_type_rules": self.semantic_policy.get("record_type_rules", {}),
                "query_metric_rules": self.semantic_policy.get("query_metric_rules", {}),
            },
            "schema": {
                "candidates": [
                    {
                        "policy_key": "string",
                        "value": "json",
                        "confidence": "number",
                    }
                ]
            },
        }
        data = self._call_semantic_parser(payload, task_type="semantic_learning")
        if not isinstance(data, dict):
            return

        candidates = data.get("candidates", [])
        if not isinstance(candidates, list):
            return

        max_updates = int(learning_cfg.get("max_updates_per_text", 8))
        default_confidence = float(learning_cfg.get("default_confidence", 0.82))
        applied = 0
        for item in candidates:
            if applied >= max_updates or not isinstance(item, dict):
                break
            policy_key = str(item.get("policy_key") or "").strip()
            value = item.get("value")
            confidence = float(item.get("confidence", default_confidence))
            if not policy_key:
                continue
            if not self._should_accept_learning_candidate(policy_key, value, learning_cfg):
                continue
            self.semantic_policy_store.record_candidate(
                policy_key,
                value,
                confidence=confidence,
                source=stage,
                evidence=text,
                metadata={"stage": stage},
            )
            applied += 1

        if applied:
            try:
                self._refresh_semantic_policy()
            except ValueError as exc:
                self.semantic_policy_store.record_runtime_failure(reason=str(exc))
                self._refresh_semantic_policy()

    def _should_accept_learning_candidate(self, policy_key: str, value: Any, learning_cfg: dict[str, Any]) -> bool:
        allowed_keys = set(learning_cfg.get("allowed_policy_keys", []))
        if allowed_keys and policy_key not in allowed_keys:
            return False

        flattened_values = self._flatten_learning_candidate_values(value)
        min_length = int(learning_cfg.get("min_candidate_text_length", 2))
        blocked_terms = {self._normalize_text(term) for term in learning_cfg.get("blocked_terms", [])}
        reject_existing_conflicts = bool(learning_cfg.get("reject_existing_conflicts", True))
        existing_values = self._existing_learning_values(policy_key) if reject_existing_conflicts else set()

        if not flattened_values:
            return False
        for item in flattened_values:
            normalized_item = self._normalize_text(item)
            if len(normalized_item) < min_length:
                return False
            if normalized_item in blocked_terms:
                return False
            if reject_existing_conflicts and normalized_item in existing_values:
                return False
        return True

    def _flatten_learning_candidate_values(self, value: Any) -> list[str]:
        flattened: list[str] = []

        def _collect(item: Any) -> None:
            if isinstance(item, str):
                if item.strip():
                    flattened.append(item)
                return
            if isinstance(item, list):
                for nested in item:
                    _collect(nested)
                return
            if isinstance(item, dict):
                for key, nested_value in item.items():
                    if str(key).strip():
                        flattened.append(str(key))
                    _collect(nested_value)
                return
            if item not in (None, ""):
                flattened.append(str(item))

        _collect(value)
        return flattened

    def _existing_learning_values(self, policy_key: str) -> set[str]:
        existing: set[str] = set()

        def _collect(item: Any) -> None:
            if isinstance(item, str):
                existing.add(self._normalize_text(item))
                return
            if isinstance(item, list):
                for nested in item:
                    _collect(nested)
                return
            if isinstance(item, dict):
                for key, nested_value in item.items():
                    existing.add(self._normalize_text(str(key)))
                    _collect(nested_value)
                return
            if item not in (None, ""):
                existing.add(self._normalize_text(str(item)))

        if policy_key == "entity_aliases.actor":
            actor_aliases = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
            _collect(actor_aliases)
            return existing

        current_value = self.semantic_policy.get(policy_key)
        _collect(current_value)
        return existing

    def _model_infer_label(self, text: str) -> str | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True):
            return None
        payload = {
            "instruction": "Infer the best semantic label for input_text and return JSON only with key label.",
            "input_text": text,
            "available_labels": list(self.semantic_policy.get("label_taxonomy", {}).keys()),
            "schema": {"label": "string|null"},
        }
        data = self._call_model_semantic_parser(payload, task_type="semantic_labeling")
        if not isinstance(data, dict):
            return None
        label = str(data.get("label") or "").strip()
        if not label:
            return None
        taxonomy = self.semantic_policy.get("label_taxonomy", {})
        return label if label in taxonomy else None
