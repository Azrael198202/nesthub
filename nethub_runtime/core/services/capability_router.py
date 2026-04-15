from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import MODEL_ROUTES_PATH, ensure_core_config_dir
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema


class CapabilityRouter:
    """Routes workflow steps to models/tools/services via JSON-configurable rules."""

    def __init__(self, route_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.route_path = route_path or MODEL_ROUTES_PATH
        self._route_config: dict[str, Any] = {}
        self._last_mtime: float | None = None
        self._load_routes()

    def _default_routes(self) -> dict[str, Any]:
        return {
            "expense_record": {
                "extract_records": {"model": "rule-parser", "tool": "parser", "service": "nlp"},
                "persist_records": {"model": "state-store", "tool": "session_store", "service": "memory"},
            },
            "expense_query": {
                "parse_query": {"model": "rule-parser", "tool": "query_parser", "service": "nlp"},
                "aggregate_query": {"model": "aggregation-engine", "tool": "query_engine", "service": "analytics"},
            },
            "default": {"model": "general-llm", "tool": "none", "service": "generic"},
        }

    def _load_routes(self) -> None:
        if not self.route_path.exists():
            self._route_config = self._default_routes()
            self.route_path.write_text(json.dumps(self._route_config, indent=2), encoding="utf-8")
            self._last_mtime = self.route_path.stat().st_mtime
            return
        self._route_config = json.loads(self.route_path.read_text(encoding="utf-8"))
        self._last_mtime = self.route_path.stat().st_mtime

    def _maybe_reload(self) -> None:
        if not self.route_path.exists():
            return
        current_mtime = self.route_path.stat().st_mtime
        if self._last_mtime is None or current_mtime > self._last_mtime:
            self._load_routes()

    def route_workflow(self, task: TaskSchema, workflow: WorkflowSchema) -> list[dict[str, Any]]:
        self._maybe_reload()
        intent_routes = self._route_config.get(task.intent, {})
        default_route = self._route_config.get("default", {})
        plan: list[dict[str, Any]] = []
        for step in workflow.steps:
            route = intent_routes.get(step.name, default_route)
            plan.append(
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "task_type": step.task_type,
                    "depends_on": step.depends_on,
                    "retry": step.retry,
                    "capability": route,
                }
            )
        return plan
