from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.memory.repositories.task_repo import TaskRepo


class TaskMemoryService:
    def __init__(self, repo: TaskRepo) -> None:
        self.repo = repo

    def write(self, task_id: str, payload: dict[str, Any]) -> None:
        self.repo.write(task_id, payload)

    def load(self, task_id: str) -> dict[str, Any]:
        return self.repo.read(task_id)
