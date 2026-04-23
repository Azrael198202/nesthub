from __future__ import annotations

from typing import Any


class WorkflowRegistryService:
    def __init__(self) -> None:
        self._workflows: dict[str, dict[str, Any]] = {}

    def register(self, workflow: dict[str, Any]) -> None:
        workflow_id = str(workflow.get("workflow_id") or "")
        if workflow_id:
            self._workflows[workflow_id] = dict(workflow)

    def get(self, workflow_id: str) -> dict[str, Any]:
        return dict(self._workflows.get(workflow_id) or {})
