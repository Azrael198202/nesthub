from __future__ import annotations

from typing import Any


class WorkflowStateStore:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def put(self, workflow_id: str, state: dict[str, Any]) -> None:
        self._states[workflow_id] = dict(state)

    def get(self, workflow_id: str) -> dict[str, Any]:
        return dict(self._states.get(workflow_id) or {})

    def mark_step(self, workflow_id: str, task_id: str, status: str) -> None:
        state = self._states.setdefault(workflow_id, {"steps": {}})
        steps = state.setdefault("steps", {})
        steps[task_id] = status
