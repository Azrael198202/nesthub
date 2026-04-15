from __future__ import annotations

from typing import Any


class ModelRegistry:
    def __init__(self) -> None:
        self.models: dict[str, dict[str, Any]] = {}

    def register(self, name: str, model_meta: dict[str, Any]) -> None:
        self.models[name] = model_meta

    def unregister(self, name: str) -> None:
        self.models.pop(name, None)

    def list(self) -> list[str]:
        return list(self.models.keys())

    def select(self, task_type: str, fallback: str = "rule-based") -> str:
        if task_type in self.models:
            return task_type
        return fallback
